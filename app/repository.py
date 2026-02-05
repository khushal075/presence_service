from redis import asyncio as aioredis
from app.schemas import UserStatus

class PresenceRepository:
    def __init__(self, redis_client):
        self.redis = redis_client
        self.HASHES_KEY = "global_presence"

    async def set_status(self, user_id: str, status: UserStatus):
        await self.redis.hset(self.HASHES_KEY, user_id, status.value)

    async def remove_status(self, user_id: str):
        await self.redis.hdel(self.HASHES_KEY, user_id)

    async def get_status(self, user_id: str) -> UserStatus:
        return await self.redis.hget(self.HASHES_KEY, user_id)

    async def get_all_status(self):
        return await self.redis.hgetall(self.HASHES_KEY)


