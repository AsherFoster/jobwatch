import re
from typing import Annotated

import structlog
from ollama import AsyncClient
from pydantic import BaseModel, Field

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


class OllamaVerdict(BaseModel):
    reasoning: str

    score: Annotated[int, Field(strict=True, ge=1, le=5)]


class OllamaClient:
    def __init__(self, model: str, base_url: str) -> None:
        self.client = AsyncClient(base_url)
        self.model = model

    async def assess_job(self, job: Job, criteria_text: str) -> Verdict:
        system_prompt = """
You screen job postings for a job seeker. You are given their criteria and one job posting.
Decide whether the posting is worth their time to review.

1 - 2: not a match, many downsides and no redeeming qualities
3: uncertain, doesn't appear to suit but may be worth a second look
4 - 5: well suited, aligns well to the job seeker, with few downsides 
        """
        user_criteria = "# My criteria\n\n" + criteria_text

        clean_description = re.sub(r"\n+", "\n", re.sub(r" +", " ", job.description))
        job_details = f"""
**{job.title}** at **{job.company}**, in **{job.location}**

--

{clean_description}
"""
        response = await self.client.chat(
            model=self.model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_criteria},
                {"role": "user", "content": job_details},
            ],
            format=OllamaVerdict.model_json_schema(),
        )

        model_verdict = OllamaVerdict.model_validate(response.message.content)

        return Verdict(
            score=model_verdict.score,
            matched=model_verdict.score >= 4,
            reasoning=model_verdict.reasoning,
        )
