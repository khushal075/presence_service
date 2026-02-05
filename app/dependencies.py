from fastapi import Request
from typing import Union
from app.utils.redis_client import get_redis_client
from app.repository import PresenceRepository
from app.broadcaster import PresenceBroadcaster
from app.manager import PresenceManager
from starlette.websockets import WebSocket

# We will use single redis client for the app life span
_redis_client = None

async def get_presence_manager(request) -> PresenceManager:
    """
    Factory to inject presence manager into routes.
    It retrieved the shared services form app
    :param request:
    :return:
    """
    # Simply pull the manager we stored in app.state during lifespan
    return request.app.state.presence_manager

    # return PresenceManager(
    #     repository=request.app.state.presence_repo,
    #     broadcaster=request.app.state.presence_broadcaster,
    # )