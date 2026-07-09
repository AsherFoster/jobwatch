"""Load and validate config.toml."""

from __future__ import annotations

import hashlib
import tomllib
from pathlib import Path

from pydantic import BaseModel, Field

DEFAULT_CONFIG_PATH = Path("config.toml")


class SearchConfig(BaseModel):
    name: str
    search_term: str
    location: str
    results_wanted: int = 100
    hours_old: int = 24


class LLMConfig(BaseModel):
    provider: str = "ollama"  # "ollama" or "anthropic"
    model: str = "qwen3:8b"
    base_url: str = "http://localhost:11434"
    api_key: str | None = None  # anthropic only; falls back to ANTHROPIC_API_KEY


class CriteriaConfig(BaseModel):
    text: str

    def fingerprint(self, model: str) -> str:
        """Identifies a (criteria, model) combination so jobs can be re-assessed
        when either changes."""
        return hashlib.sha256(f"{model}\n{self.text}".encode()).hexdigest()[:16]


class DiscordConfig(BaseModel):
    webhook_url: str


class NotifyConfig(BaseModel):
    discord: DiscordConfig | None = None


class ScheduleConfig(BaseModel):
    interval_minutes: int = 60


class WebConfig(BaseModel):
    host: str = "0.0.0.0"
    port: int = 8000
    # Used to build links in notifications; set to how *you* reach the UI.
    base_url: str = "http://localhost:8000"


class Config(BaseModel):
    database_url: str = "sqlite:///data/jobwatch.db"
    searches: list[SearchConfig] = Field(min_length=1)
    criteria: CriteriaConfig
    llm: LLMConfig = LLMConfig()
    notify: NotifyConfig = NotifyConfig()
    schedule: ScheduleConfig = ScheduleConfig()
    web: WebConfig = WebConfig()


def load_config(path: Path | str = DEFAULT_CONFIG_PATH) -> Config:
    with open(path, "rb") as f:
        return Config.model_validate(tomllib.load(f))
