"""
Integration tests for FastAPI HTTP endpoints.
Spins up the full app with a mocked Redis client.
"""
import pytest
import pytest_asyncio
from unittest.mock import AsyncMock, patch, MagicMock
from httpx import AsyncClient, ASGITransport


@pytest.fixture
def mock_redis():
    redis = AsyncMock()
    redis.hset = AsyncMock()
    redis.hdel = AsyncMock()
    redis.hget = AsyncMock(return_value=None)
    redis.hgetall = AsyncMock(return_value={})
    redis.publish = AsyncMock(return_value=1)
    redis.exists = AsyncMock(return_value=0)
    redis.set = AsyncMock()
    redis.close = AsyncMock()

    # pubsub that never yields messages (so background tasks don't block)
    pubsub = AsyncMock()
    pubsub.subscribe = AsyncMock()
    pubsub.unsubscribe = AsyncMock()

    async def _empty_listen():
        return
        yield  # make it an async generator

    pubsub.listen = _empty_listen
    redis.pubsub = MagicMock(return_value=pubsub)
    return redis


@pytest_asyncio.fixture
async def client(mock_redis):
    from app.main import app

    with patch("app.main.get_redis_client", AsyncMock(return_value=mock_redis)):
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as c:
            yield c


class TestHealthEndpoint:

    @pytest.mark.asyncio
    async def test_health_returns_200(self, client):
        response = await client.get("/health")
        assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_health_returns_running(self, client):
        response = await client.get("/health")
        assert response.json() == {"status": "running"}