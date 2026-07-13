from dataclasses import dataclass
from typing import Protocol

from jobwatch.config import config
from jobwatch.models import Job


@dataclass
class Verdict:
    score: int
    reasoning: str


class LLMClient(Protocol):
    model: str

    async def assess_job(self, job: Job, criteria_text: str) -> Verdict: ...


def make_llm_client() -> LLMClient:
    match config.llm.provider:
        case "ollama":
            from jobwatch.llm.ollama import OllamaClient

            ollama_config = config.ollama
            assert ollama_config is not None, "ollama config must be set to use ollama models"

            return OllamaClient(model=config.llm.model, base_url=ollama_config.base_url)
        case "apple_fm":
            from jobwatch.llm.apple_fm import AppleFMClient

            return AppleFMClient()
        case "anthropic":
            from jobwatch.llm.anthropic import AnthropicClient

            anthropic_config = config.anthropic
            assert anthropic_config is not None, (
                "anthropic config must be set to use anthropic models"
            )

            return AnthropicClient(model=config.llm.model, api_key=anthropic_config.api_key)
        case "gemini":
            from jobwatch.llm.gemini import GeminiClient

            gemini_config = config.gemini
            assert gemini_config is not None, "gemini config must be set to use gemini models"

            return GeminiClient(model=config.llm.model, api_key=gemini_config.api_key)
        case _:
            raise ValueError(f"Unknown LLM provider: {config.llm.provider!r}")
