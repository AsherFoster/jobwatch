import json
import re

import httpx2
import structlog

from jobwatch.llm import Verdict
from jobwatch.models import Job

log = structlog.get_logger()


def build_prompt(job: Job, criteria_text: str) -> str:
    return (
        f"## My criteria\n{criteria_text}\n\n"
        f"## Job posting\n"
        f"Title: {job.title}\n"
        f"Company: {job.company}\n"
        f"Location: {job.location}\n\n"
        f"{job.description or '(no description available)'}"
    )


class OllamaClient:
    def __init__(self, model: str, base_url: str = "http://localhost:11434") -> None:
        self.model = model
        self._client = httpx2.AsyncClient(base_url=base_url, timeout=300.0)

    async def complete(self, system: str, prompt: str) -> str:
        response = await self._client.post(
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

    SYSTEM_PROMPT = """\
You screen job postings for a job seeker. You are given their criteria and one job posting.
Decide whether the posting is worth their time to review.

Respond with ONLY a JSON object, no other text:
{"matched": true or false, "score": 1-5, "reasoning": "one or two sentences"}

score is how well the job fits the criteria:
1 - hard no, completely different role
2 - unlikely: has many drawbacks that make it unsuitable
3 - uncertain, may or may not be suitable
4 - matches some criteria and has some drawbacks
5 - matches many criteria and has very few drawbacks

Err on the side of
including: the job seeker would rather review a borderline posting than miss a real
opportunity. When in doubt, or when the posting is vague, set matched to true. Only set
matched to false when the posting clearly hits a negative criterion or is clearly
irrelevant to the criteria."""

    async def assess_job(self, job: Job, criteria_text: str) -> Verdict:
        response = await self.complete(self.SYSTEM_PROMPT, build_prompt(job, criteria_text))
        try:
            match = re.search(r"\{.*}", response, re.DOTALL)
            if not match:
                raise ValueError(f"No JSON object in LLM response: {response[:200]!r}")
            data = json.loads(match.group(0))
        except (ValueError, KeyError, json.JSONDecodeError) as e:
            log.error("Failed to parse LLM response", exc_info=e)
            return Verdict(
                matched=False, score=0, reasoning=f"LLM response unparseable: {response[:200]}"
            )

        return Verdict(
            matched=bool(data["matched"]),
            score=max(0, min(5, int(data.get("score", 0)))),
            reasoning=str(data.get("reasoning", "")),
        )
