from dataclasses import dataclass
from typing import Protocol

from jobwatch.config import config
from jobwatch.models import Job


@dataclass
class Verdict:
    matched: bool
    score: int
    reasoning: str


class LLMClient(Protocol):
    model: str

    async def assess_job(self, job: Job, criteria_text: str) -> Verdict: ...


def make_llm_client() -> LLMClient:
    match config.llm.provider:
        case "ollama":
            from jobwatch.llm.ollama import OllamaClient

            return OllamaClient(model=config.llm.model, base_url=config.llm.base_url)
        case "apple_fm":
            from jobwatch.llm.apple_fm import AppleFMClient

            return AppleFMClient()
        case "anthropic":
            from jobwatch.llm.anthropic import AnthropicClient

            return AnthropicClient(model=config.llm.model, api_key=config.llm.api_key)
        case _:
            raise ValueError(f"Unknown LLM provider: {config.llm.provider!r}")
