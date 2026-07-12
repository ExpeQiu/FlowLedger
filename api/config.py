import os
from pathlib import Path

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    database_url: str = "postgresql://flowledger:flowledger@localhost:5432/flowledger"
    api_url: str = "http://localhost:8000"
    log_level: str = "INFO"
    log_dir: Path = Path(__file__).resolve().parent.parent / "logs"

    class Config:
        env_file = Path(__file__).resolve().parent.parent / ".env"
        extra = "ignore"


settings = Settings()
settings.log_dir.mkdir(parents=True, exist_ok=True)
