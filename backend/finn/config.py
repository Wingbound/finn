from functools import lru_cache
from pathlib import Path

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    gemini_api_key: str = ""
    groq_api_key: str = ""
    data_dir: Path = Path("data")
    db_path: Path | None = None
    allowed_origins: list[str] = ["*"]

    @model_validator(mode="after")
    def _default_db_path(self) -> "Settings":
        if self.db_path is None:
            self.db_path = self.data_dir / "finn.sqlite"
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()
