"""
Shared pytest fixtures for presence_service tests.
"""
import asyncio
import pytest
import pytest_asyncio
from unittest.mock import AsyncMock, MagicMock, patch
from fastapi.testclient import TestClient
from httpx import AsyncClient, ASGITransport

from app.schemas import UserStatus, PresenceUpdate


# ── Redis mock fixture ────────────────────────────────────────────────────────

@pytest.fixture
def mock_redis():
    """
    In-memory Redis mock. Covers hset/hdel/hget/hgetall/publish/exists/set.
    Use this for pure unit tests that don't need a real Redis.
    """
    redis = AsyncMock()

    # Internal store so assertions can inspect state
    _hash: dict[str, dict] = {}
    _keys: dict[str, str] = {}

    async def hset(name, key, value):
        _hash.setdefault(name, {})[key] = value

    async def hdel(name, key):
        _hash.get(name, {}).pop(key, None)

    async def hget(name, key):
        return _hash.get(name, {}).get(key)

    async def hgetall(name):
        return dict(_hash.get(name, {}))

    async def publish(channel, message):
        return 1

    async def exists(key):
        return int(key in _keys)

    async def set(key, value, ex=None):
        _keys[key] = value

    redis.hset.side_effect = hset
    redis.hdel.side_effect = hdel
    redis.hget.side_effect = hget
    redis.hgetall.side_effect = hgetall
    redis.publish.side_effect = publish
    redis.exists.side_effect = exists
    redis.set.side_effect = set

    # Expose the backing stores for assertions
    redis._hash = _hash
    redis._keys = _keys

    return redis


# ── Repository / Broadcaster fixtures ────────────────────────────────────────

@pytest.fixture
def repository(mock_redis):
    from app.repository import PresenceRepository
    return PresenceRepository(mock_redis)


@pytest.fixture
def broadcaster(mock_redis):
    from app.broadcaster import PresenceBroadcaster
    return PresenceBroadcaster(mock_redis)


@pytest.fixture
def manager(repository, broadcaster):
    from app.manager import PresenceManager
    return PresenceManager(repository, broadcaster)


# ── FastAPI app fixture (integration) ────────────────────────────────────────

@pytest_asyncio.fixture
async def app(mock_redis):
    """
    Full FastAPI app with Redis patched out.
    Suitable for HTTP + WebSocket integration tests.
    """
    from app.main import app as _app
    import app.main as main_module

    with patch("app.main.get_redis_client", return_value=mock_redis):
        async with AsyncClient(
            transport=ASGITransport(app=_app), base_url="http://test"
        ) as client:
            yield client


# ── Helpers ───────────────────────────────────────────────────────────────────

def make_presence_update(user_id: str = "1", status: UserStatus = UserStatus.ONLINE):
    return PresenceUpdate(user_id=int(user_id), status=status)