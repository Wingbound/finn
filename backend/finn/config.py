from datetime import date
from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    gemini_api_key: str = ""
    groq_api_key: str = ""
    # Model IDs, each overridable via env (FINN_MODEL_<TASK>). Verified against each
    # provider's list-models endpoint on 2026-11-09 (Groq has retired its Llama models).
    # gpt-oss-120b over -20b: 91.3% vs 85.6% on the classification eval (docs/EVALS.md).
    finn_model_classify: str = "openai/gpt-oss-120b"
    finn_model_oneliner: str = "openai/gpt-oss-120b"
    finn_model_extract_pdf: str = "gemini-3.8-flash"
    finn_model_extract_transcript: str = "gemini-3.5-flash-lite"
    # Pro (gemini-3.1-pro-preview) has no free tier. gemini-3.8-flash was unreliable on the
    # free tier on 2026-11-09 (503s, 45 s hangs), so reason uses Flash-Lite.
    finn_model_reason: str = "gemini-3.5-flash-lite"
    finn_model_bio: str = "openai/gpt-oss-120b"
    data_dir: Path = Path("data")
    db_path: Path | None = None
    # Committed snapshot the API copies into an empty store on startup (env SEED_PATH).
    seed_path: Path = Path(__file__).resolve().parents[1] / "seed" / "finn.sqlite"
    allowed_origins: list[str] = ["*"]

    @model_validator(mode="after")
    def _default_db_path(self) -> "Settings":
        if self.db_path is None:
            self.db_path = self.data_dir / "finn.sqlite"
        return self

    @property
    def llm_cache_path(self) -> Path:
        """Scratch store for scripts that call the LLM directly; never the serving DB."""
        return self.data_dir / "llm_cache.sqlite"


# Weekend dates on which NSE ran a full trading session, e.g. a Saturday Union Budget day.
# Every other weekend-dated bar is a token special session (Diwali Muhurat) and is dropped
# from price history; add a date here only after NSE announces a full session for it.
FULL_SPECIAL_SESSIONS: frozenset[date] = frozenset()

ROUTES: dict[str, Literal["groq", "gemini"]] = {
    "classify": "groq",
    "oneliner": "groq",
    "extract_pdf": "gemini",
    "extract_transcript": "gemini",
    "reason": "gemini",
    "bio": "groq",
}


def route_for(task: str, settings: Settings) -> tuple[str, str]:
    """Public way to get the (provider, model_id) pair for a task.

    ROUTES holds only the provider; the model ID is read from settings so it can be
    overridden per task with FINN_MODEL_<TASK>.
    """
    if task not in ROUTES:
        raise KeyError(f"unknown LLM task: {task}")
    return ROUTES[task], getattr(settings, f"finn_model_{task}")


_FLASH_LITE = ("gemini", "gemini-3.5-flash-lite")
_FLASH_LITE_31 = ("gemini", "gemini-3.1-flash-lite")
# Tried in order after the primary route, so one provider's outage doesn't stop a task.
FALLBACKS: dict[str, list[tuple[str, str]]] = {
    "classify": [_FLASH_LITE],
    "oneliner": [_FLASH_LITE],
    "bio": [_FLASH_LITE],
    "extract_pdf": [_FLASH_LITE],
    "reason": [_FLASH_LITE_31],
    # Transcript prompts (15-25k tokens) exceed Groq's 8K TPM, so Groq cannot be the fallback.
    "extract_transcript": [_FLASH_LITE_31],
}


def chain_for(task: str, settings: Settings) -> list[tuple[str, str]]:
    """The primary (provider, model) then the task's fallbacks, de-duplicated in order."""
    chain: list[tuple[str, str]] = []
    for pm in [route_for(task, settings), *FALLBACKS.get(task, [])]:
        if pm not in chain:
            chain.append(pm)
    return chain


@lru_cache
def get_settings() -> Settings:
    return Settings()
