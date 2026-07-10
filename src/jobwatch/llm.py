"""LLM abstraction: Ollama by default, Apple FM or Anthropic as optional drop-ins."""

from __future__ import annotations

import asyncio
import json
from typing import Protocol

import httpx2
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
        self._client = httpx2.Client(base_url=base_url, timeout=300.0)

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
        if not response.is_success:
            log.error(response.text)

        response.raise_for_status()
        return response.json()["message"]["content"]


class AppleFMClient:
    """Apple's on-device Foundation Models (macOS 26+, Apple Silicon).

    Uses guided generation: the verdict schema is declared with @fm.generable,
    so the model is constrained to produce it rather than asked for JSON.
    """

    def __init__(self, model: str = "apple-fm") -> None:
        try:
            import apple_fm_sdk as fm  # ty: ignore[unresolved-import]
        except ImportError as e:
            raise RuntimeError(
                "Apple FM provider requires the optional dependency: uv sync --extra apple-fm"
            ) from e
        self.model = model
        self._fm = fm

        @fm.generable("Verdict on whether a job posting matches the job seeker's criteria")
        class Verdict:
            matched: bool = fm.guide("Whether the posting is worth the job seeker's time")
            score: int = fm.guide(
                "How well the job fits the criteria, 10 = perfect fit", range=(0, 10)
            )
            reasoning: str = fm.guide("One or two sentences explaining the verdict")

        self._verdict_type = Verdict

    def complete(self, system: str, prompt: str) -> str:
        verdict = asyncio.run(self._respond(system, prompt))
        return json.dumps(
            {"matched": verdict.matched, "score": verdict.score, "reasoning": verdict.reasoning}
        )

    async def _respond(self, system: str, prompt: str):
        session = self._fm.LanguageModelSession(instructions=system)
        return await session.respond(prompt, generating=self._verdict_type)


# class AnthropicClient:
#     def __init__(self, model: str, api_key: str | None = None) -> None:
#         try:
#             import anthropic
#         except ImportError as e:
#             raise RuntimeError(
#                 "Anthropic provider requires the optional dependency: uv sync --extra anthropic"
#             ) from e
#         self.model = model
#         self._client = anthropic.Anthropic(api_key=api_key) if api_key else anthropic.Anthropic()
#
#     def complete(self, system: str, prompt: str) -> str:
#         response = self._client.messages.create(
#             model=self.model,
#             max_tokens=1024,
#             system=system,
#             messages=[{"role": "user", "content": prompt}],
#         )
#         return "".join(block.text for block in response.content if block.type == "text")
#


def make_llm_client(config: LLMConfig) -> LLMClient:
    if config.provider == "ollama":
        return OllamaClient(model=config.model, base_url=config.base_url)
    if config.provider == "apple_fm":
        # Single on-device system model; config.model does not apply.
        return AppleFMClient()
    # if config.provider == "anthropic":
    #     return AnthropicClient(model=config.model, api_key=config.api_key)
    raise ValueError(f"Unknown LLM provider: {config.provider!r}")
