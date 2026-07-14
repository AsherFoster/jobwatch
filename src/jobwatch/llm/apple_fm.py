import re

import apple_fm_sdk as fm  # ty:ignore[unresolved-import,unused-ignore-comment]

from jobwatch.llm import Verdict
from jobwatch.models import Job


@fm.generable("Score of how well this job suits the job seeker")
class FMVerdict:
    reasoning: str = fm.guide("1 - 2 sentences explaining the score")

    score: int = fm.guide(
        """
        1 - 2: not a match, many downsides and no redeeming qualities
        3: uncertain, doesn't appear to suit but may be worth a second look
        4 - 5: well suited, aligns well to the job seeker, with few downsides 
        """,
        range=(1, 5),
    )


class AppleFMClient:
    """Apple's on-device Foundation Models (macOS 26+, Apple Silicon).

    Uses guided generation: the verdict schema is declared with @fm.generable,
    so the model is constrained to produce it rather than asked for JSON.
    """

    model = "apple_foundation"

    async def assess_job(self, job: Job, criteria_text: str) -> Verdict:
        clean_description = re.sub(r"\n+", "\n", re.sub(r" +", " ", job.description))
        system_prompt = f"""
You screen job postings for a job seeker, and score if the job is a good match for their criteria. 

Their criteria:
{criteria_text}
        """

        prompt = f"""
**{job.title}** at **{job.company}**, in **{job.location}**

--

{clean_description}
"""

        session = fm.LanguageModelSession(instructions=system_prompt)
        response = await session.respond(prompt, generating=FMVerdict)

        return Verdict(
            score=response.score,
            reasoning=response.reasoning,
        )
