"""Load and validate config.toml.

Every field has a default, so the file is optional — used mostly to point at
a real Discord webhook and LLM. Searches live in the DB (see searches.py).
"""

from __future__ import annotations

import os
import tomllib
from pathlib import Path

from pydantic import BaseModel

DEFAULT_CONFIG_PATH = Path("config.toml")


class OllamaConfig(BaseModel):
    base_url: str


class AnthropicConfig(BaseModel):
    api_key: str | None = None  # falls back to ANTHROPIC_API_KEY


class GeminiConfig(BaseModel):
    api_key: str | None = None  # falls back to GEMINI_API_KEY


class LLMConfig(BaseModel):
    provider: str = "ollama"  # "ollama", "apple_fm", "anthropic" or "gemini"
    model: str = "qwen3:8b"  # ignored by apple_fm (single on-device model)


class DiscordConfig(BaseModel):
    webhook_url: str


class NotifyConfig(BaseModel):
    discord: DiscordConfig | None = None


class ScheduleConfig(BaseModel):
    interval_minutes: int = 60


class WebConfig(BaseModel):
    # Used to build links in notifications; set to how *you* reach the UI.
    base_url: str


class Config(BaseModel):
    database_url: str
    llm: LLMConfig = LLMConfig()
    ollama: OllamaConfig = OllamaConfig()
    anthropic: AnthropicConfig = AnthropicConfig()
    gemini: GeminiConfig = GeminiConfig()
    notify: NotifyConfig = NotifyConfig()
    schedule: ScheduleConfig = ScheduleConfig()
    web: WebConfig = WebConfig()


path = os.environ.get("JOBWATCH_CONFIG") or DEFAULT_CONFIG_PATH
with open(path, "rb") as f:
    config = Config.model_validate(tomllib.load(f))
