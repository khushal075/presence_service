import asyncio
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Depends

from contextlib import asynccontextmanager
from app.utils.redis_client import get_redis_client
from app.repository import PresenceRepository
from app.broadcaster import PresenceBroadcaster
from app.dependencies import get_presence_manager
from app.manager import PresenceManager
from fastapi.middleware.cors import CORSMiddleware


@asynccontextmanager
async def lifespan(app: FastAPI):
    # ------ Startup: Initialize the "Brain"
    redis = await get_redis_client()
    repo = PresenceRepository(redis)
    broadcaster = PresenceBroadcaster(redis)
    app.state.presence_repository = repo
    app.state.presence_broadcaster = broadcaster

    # --------- Initialize manager ----------------
    manager = PresenceManager(repo, broadcaster)

    # ---------- Store in app state so dependencies can find it ---------
    app.state.presence_manager = manager

    # Start background task
    # Task A: Listen for updates from other servers
    listener_task = asyncio.create_task(manager.start_global_listener())

    # Task B: Clean up dead users who stopped sending heartbeat
    cleanup_task = asyncio.create_task(manager.start_cleanup_monitor())

    print('Presence service Cluster node started ...')

    yield

    # ------ SHUTDOWN ----------
    listener_task.cancel()
    cleanup_task.cancel()

    await redis.close()
    print('Presence service Cluster node stopped ...')

    # ----- Shutdown: clean up ---------
    #await redis.close()

app = FastAPI(lifespan=lifespan)


app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Allows all origins
    allow_credentials=True,
    allow_methods=["*"],  # Allows all methods
    allow_headers=["*"],  # Allows all headers
)


@app.websocket("/ws/{user_id}")
async def websocket_endpoint(websocket: WebSocket, user_id: str):
    # Bypass the dependency and grab it directly from state
    presence_manager = websocket.app.state.presence_manager

    await presence_manager.handle_connection(user_id, websocket)
    try:
        while True:
            # Note: Changed this to match your logic
            data = await websocket.receive_json()
            if data.get("type") == 'ping':
                await presence_manager.refresh_heartbeat(user_id)
                await websocket.send_json({"type": "pong"})
    except WebSocketDisconnect:
        await presence_manager.handle_disconnect(user_id, websocket)
    except Exception as ex:
        print(f"Connection error for user {user_id}: {ex}")
        await presence_manager.handle_disconnect(user_id, websocket)


@app.get('/health')
async def health_check():
    return {'status': 'running'}


@app.websocket("/presence/all")
async def get_all_presences(
        manager: PresenceManager = Depends(get_presence_manager),
):
    return await manager.get_all_presences()