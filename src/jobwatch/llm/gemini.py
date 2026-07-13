import re
from typing import Annotated

import structlog
from google import genai
from google.genai.interactions import Interaction
from pydantic import BaseModel, Field

from jobwatch.llm import Verdict
from jobwatch.models import Job

log = structlog.get_logger()


class GeminiVerdict(BaseModel):
    reasoning: str

    score: Annotated[int, Field(strict=True, ge=1, le=5)]


class GeminiClient:
    def __init__(self, model: str, api_key: str) -> None:
        self._client = genai.Client(api_key=api_key)
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
        interaction = await self._client.aio.interactions.create(
            model=self.model,
            system_instruction=system_prompt,
            input=f"""# Criteria:\n{criteria_text}\n\n#Job Details:\n{job_details}""",
            response_format={
                "type": "text",
                "mime_type": "application/json",
                "schema": GeminiVerdict.model_json_schema(),
            },
            store=False,
        )

        assert isinstance(interaction, Interaction)  # stream=False never returns a stream
        if interaction.status != "completed":
            raise ValueError("gemini request was not successful")

        model_verdict = GeminiVerdict.model_validate_json(interaction.output_text or "")

        return Verdict(
            score=model_verdict.score,
            reasoning=model_verdict.reasoning,
        )
