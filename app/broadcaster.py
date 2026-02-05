import json
from app.schemas import PresenceUpdate


class PresenceBroadcaster:

    def __init__(self, redis_client):
        self.redis = redis_client
        self.CHANNEL = "presence_update"

    async def publish(self, presence: PresenceUpdate):
        await self.redis.publish(self.CHANNEL, presence.model_dump_json())

    def get_pubsub(self):
        return self.redis.pubsub()


