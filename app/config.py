from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    REDIS_URL: str = "redis://localhost:6379"
    APP_NAME: str = "app"

    # Heartbeat settings
    HEARTBEAT_INTERVAL: int = 20
    PRESENCE_TTL: int = 30

    class Config:
        env_file = ".env"

# Create an instance
settings = Settings()