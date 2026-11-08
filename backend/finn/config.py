from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    gemini_api_key: str = ""
    groq_api_key: str = ""
    # Model IDs, each overridable via env (FINN_MODEL_<TASK>). UNVERIFIED (from public docs,
    # 2026-11-08) — verify via list-models when keys arrive
    finn_model_classify: str = "llama-3.1-8b-instant"
    finn_model_oneliner: str = "llama-3.1-8b-instant"
    finn_model_extract_pdf: str = "gemini-3.8-flash"
    finn_model_extract_transcript: str = "gemini-3.5-flash-lite"
    # Pro (gemini-3.1-pro-preview) has no free tier, so reason uses Flash.
    finn_model_reason: str = "gemini-3.8-flash"
    finn_model_bio: str = "gemini-3.8-flash"
    data_dir: Path = Path("data")
    db_path: Path | None = None
    allowed_origins: list[str] = ["*"]

    @model_validator(mode="after")
    def _default_db_path(self) -> "Settings":
        if self.db_path is None:
            self.db_path = self.data_dir / "finn.sqlite"
        return self


ROUTES: dict[str, tuple[Literal["groq", "gemini"], str]] = {
    "classify": "groq",
    "oneliner": "groq",
    "extract_pdf": "gemini",
    "extract_transcript": "gemini",
    "reason": "gemini",
    "bio": "gemini",
}


def route_for(task: str, settings: Settings) -> tuple[str, str]:
    """Return (provider, model_id) for a task; model IDs come from settings."""
    if task not in ROUTES:
        raise KeyError(f"unknown LLM task: {task}")
    return ROUTES[task], getattr(settings, f"finn_model_{task}")


@lru_cache
def get_settings() -> Settings:
    return Settings()
