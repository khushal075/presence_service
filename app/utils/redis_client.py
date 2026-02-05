import redis.asyncio as aioredis
from app.config import settings

async def get_redis_client() -> aioredis.Redis:
    return aioredis.from_url(
        settings.REDIS_URL,
        decode_responses=True,
        socket_connect_timeout=5
    )

