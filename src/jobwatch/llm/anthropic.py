from anthropic import Anthropic

from jobwatch.llm import Verdict
from jobwatch.models import Job


class AnthropicClient:
    def __init__(self, model: str, api_key: str | None = None) -> None:
        self.model = model
        self._client = Anthropic(api_key=api_key) if api_key else Anthropic()

    def complete(self, system: str, prompt: str) -> str:
        response = self._client.messages.create(
            model=self.model,
            max_tokens=1024,
            system=system,
            messages=[{"role": "user", "content": prompt}],
        )
        return "".join(block.text for block in response.content if block.type == "text")

    async def assess_job(self, job: Job, criteria_text: str) -> Verdict:
        raise NotImplementedError()
