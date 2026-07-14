"""Load and validate config.toml.

Every field has a default, so the file is optional — used mostly to point at
a real Discord webhook and LLM. Searches live in the DB (see UserSearch).
"""

from __future__ import annotations

import os
from typing import Literal

from pydantic import BaseModel
from pydantic_settings import BaseSettings, SettingsConfigDict, TomlConfigSettingsSource

environment = os.environ.get("ENVIRONMENT")
assert environment in ["production", "development", "test"]


class OllamaConfig(BaseModel):
    base_url: str


class AnthropicConfig(BaseModel):
    api_key: str


class GeminiConfig(BaseModel):
    api_key: str


class LLMConfig(BaseModel):
    provider: Literal["ollama", "apple_fm", "anthropic", "gemini"]
    model: str


class DiscordConfig(BaseModel):
    webhook_url: str


class NotifyConfig(BaseModel):
    discord: DiscordConfig | None = None


class ScheduleConfig(BaseModel):
    interval_minutes: int = 60


class WebConfig(BaseModel):
    # Used to build links in notifications; set to how *you* reach the UI.
    base_url: str


class Config(BaseSettings):
    model_config = SettingsConfigDict(
        toml_file=["config.toml", f"config.{environment}.toml", "config.local.toml"]
    )

    database_url: str
    llm: LLMConfig
    ollama: OllamaConfig | None = None
    anthropic: AnthropicConfig | None = None
    gemini: GeminiConfig | None = None
    notify: NotifyConfig = NotifyConfig()
    schedule: ScheduleConfig
    web: WebConfig

    @classmethod
    def settings_customise_sources(
        cls,
        settings_cls,
        init_settings,
        env_settings,
        dotenv_settings,
        file_secret_settings,
    ):
        # Returning only the TOML source drops env vars, dotenv, and secrets entirely.
        return (TomlConfigSettingsSource(settings_cls, deep_merge=True),)


config = Config()
