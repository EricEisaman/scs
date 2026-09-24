from pydantic_settings import BaseSettings
import os

class Settings(BaseSettings):
    app_env: str = os.getenv("APP_ENV", "development")
    port: int = int(os.getenv("PORT", "10000"))
    allowed_origins: str = os.getenv("ALLOWED_ORIGINS", "https://ericeisaman.github.io,http://localhost:8000")
    tick_hz: int = 20
    snapshot_hz: int = 15
    max_players_per_room: int = 8

    def get_allowed_origins_list(self):
        return [o.strip() for o in self.allowed_origins.split(",") if o.strip()]

settings = Settings()