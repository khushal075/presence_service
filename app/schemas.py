from pydantic import BaseModel
from typing import Optional
from enum import Enum

class UserStatus(str, Enum):
    ONLINE = "online"
    OFFLINE = "offline"
    AWAY = "away"
    BUSY = "busy"


class PresenceUpdate(BaseModel):
    user_id: str
    status: UserStatus
    metadata: dict = {}

