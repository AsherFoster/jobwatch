"""LLM abstraction: Ollama by default, Anthropic as an optional drop-in."""

from __future__ import annotations

from typing import Protocol

import httpx
import structlog

from jobwatch.config import LLMConfig

log = structlog.get_logger()

class LLMClient(Protocol):
    model: str

    def complete(self, system: str, prompt: str) -> str:
        """Return the model's text response. Implementations should request JSON
        output where the backend supports it."""
        ...


class OllamaClient:
    def __init__(self, model: str, base_url: str = "http://localhost:11434") -> None:
        self.model = model
        self._client = httpx.Client(base_url=base_url, timeout=300.0)

    def complete(self, system: str, prompt: str) -> str:
        response = self._client.post(
            "/api/chat",
            json={
                "model": self.model,
                "messages": [
                    {"role": "system", "content": system},
                    {"role": "user", "content": prompt},
                ],
                "format": "json",
                "stream": False,
            },
        )
        if not response.ok:
            log.error(response.text)

        response.raise_for_status()
        return response.json()["message"]["content"]


class AnthropicClient:
    def __init__(self, model: str, api_key: str | None = None) -> None:
        try:
            import anthropic
        except ImportError as e:
            raise RuntimeError(
                "Anthropic provider requires the optional dependency: uv sync --extra anthropic"
            ) from e
        self.model = model
        self._client = anthropic.Anthropic(api_key=api_key) if api_key else anthropic.Anthropic()

    def complete(self, system: str, prompt: str) -> str:
        response = self._client.messages.create(
            model=self.model,
            max_tokens=1024,
            system=system,
            messages=[{"role": "user", "content": prompt}],
        )
        return "".join(block.text for block in response.content if block.type == "text")


def make_llm_client(config: LLMConfig) -> LLMClient:
    if config.provider == "ollama":
        return OllamaClient(model=config.model, base_url=config.base_url)
    if config.provider == "anthropic":
        return AnthropicClient(model=config.model, api_key=config.api_key)
    raise ValueError(f"Unknown LLM provider: {config.provider!r}")
