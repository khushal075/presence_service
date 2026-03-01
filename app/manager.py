import asyncio
import json
from fastapi import WebSocket
from app.utils.redis_client import get_redis_client
from app.repository import PresenceRepository
from app.broadcaster import PresenceBroadcaster
from app.schemas import UserStatus, PresenceUpdate

class PresenceManager:
    def __init__(self, repository: PresenceRepository, broadcaster: PresenceBroadcaster):
        self.repository = repository
        self.broadcaster = broadcaster

        # Local connections stays here because its instance specific memory
        self.local_connections: dict[str, set[WebSocket]] = {}



    async def handle_connection(self, user_id: str, websocket: WebSocket):
        await websocket.accept()

        if user_id not in self.local_connections:
            self.local_connections[user_id] = set()
            await self.repository.set_status(user_id, UserStatus.ONLINE)
            await self.broadcaster.publish(PresenceUpdate(user_id=user_id, status=UserStatus.ONLINE))


        self.local_connections[user_id].add(websocket)


    async def handle_disconnect(self, user_id: str, websocket: WebSocket):
        if user_id in self.local_connections:
            self.local_connections[user_id].discard(websocket)

            if not self.local_connections[user_id]:
                del self.local_connections[user_id]

                # User is completely offline
                await self.repository.remove_status(user_id)
                await self.broadcaster.publish(PresenceUpdate(user_id=user_id, status=UserStatus.OFFLINE))

    async def start_global_listener(self):
        """
        This background task ensure that updates from Server B are received and handled by server A
        :return:
        """
        pubsub = self.broadcaster.get_pubsub()
        await pubsub.subscribe(self.broadcaster.CHANNEL)

        try:
            async for message in pubsub.listen():
                if message["type"] == "message":
                    data = json.loads(message["data"])
                    user_id = data["user_id"]
                    status = data["status"]

                    # LOG the event for observability
                    print(f"Global Sync:  User {user_id} is status: {status}")

                    # Notify local connections
                    # If server has client interested in user_id,
                    # We broadcast change to them
                    await self._notify_local_subscribers(user_id, status)
        except Exception as e:
            print(f"Global Sync:  Error: {e}")
            # We can also implement the retry logic or reconnect logic here
        finally:
            await pubsub.unsubscribe(self.broadcaster.CHANNEL)

    async def _notify_local_subscribers(self, target_user_id: str, status: UserStatus):
        if not self.local_connections:
            return
        message = json.dumps({
            "user_id": target_user_id,
            "status": status,
            "type": "presence_change"
        })

        # 1. Collect all active websocket objects into a flat list
        all_ws = [
            ws for connections in self.local_connections.values() for ws in connections
        ]

        # Define a safe send helper to prevent one failure from stoping the batch
        async def safe_send(ws: WebSocket):
            try:
                await ws.send_text(message)
            except Exception as e:
                # We don't raise here, the main loop handles disconnect
                pass

        # Execute all sends concurrently (FAN - OUT)
        await asyncio.gather(*(safe_send(ws) for ws in all_ws))

    async def refresh_heartbeat(self, user_id: str):
        """
        Instead of just hash, we set a temporary key in Redis that expires if not touched
        """
        heartbeat_key = f"presence:heartbeat:{user_id}"

        # Set a key that expires in 60 seconds
        # If the client doesn't call this again within 60 seconds, the key vanishes.
        await self.redis.set(heartbeat_key, 'alive', ex=60)

        # Ensure they are marked as online in the main hash
        await self.repository.set_status(user_id, UserStatus.ONLINE)


    async def start_cleanup_monitor(self):
        """
        Periodically checks if any users in the global_presence hash have lost their
        heartbeat and marks them offline.
        """
        while True:
            all_users = await self.repository.get_all_status()
            for user_id in all_users:
                heartbeat_exists = await self.redis.exists(f"presence:heartbeat:{user_id}")
                if not heartbeat_exists:
                    # User timeout
                    await self.repository.remove_status(user_id)
                    await self.broadcaster.publish(PresenceUpdate(user_id=user_id, status=UserStatus.OFFLINE))

            # Checks every 30 seconds
            await asyncio.sleep(30)


