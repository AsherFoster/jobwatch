import re

import structlog
from ollama import AsyncClient

from jobwatch.llm import Verdict
from jobwatch.llm.gemini import GeminiVerdict
from jobwatch.models import Job

log = structlog.get_logger()


def build_prompt(job: Job, criteria_text: str) -> str:
    return (
        f"## My criteria\n{criteria_text}\n\n"
        f"## Job posting\n"
        f"Title: {job.title}\n"
        f"Company: {job.company.name}\n"
        f"Location: {job.location}\n\n"
        f"{job.description or '(no description available)'}"
    )


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
**{job.title}** at **{job.company.name}**, in **{job.location}**

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
            format=GeminiVerdict.model_json_schema(),
        )

        model_verdict = GeminiVerdict.model_validate_json(response.message.content or "")

        return Verdict(
            score=model_verdict.score,
            reasoning=model_verdict.reasoning,
            summary=model_verdict.summary,
            summary_positives=model_verdict.summary_positives,
            summary_negatives=model_verdict.summary_negatives,
        )
