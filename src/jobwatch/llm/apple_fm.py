import apple_fm_sdk as fm

from jobwatch.llm import Verdict
from jobwatch.models import Job


@fm.generable("Score of how well this job suits the job seeker")
class FMVerdict:
    score: int = fm.guide(
        """
        1 - 2: not a match, many downsides and no redeeming qualities
        3: uncertain, doesn't appear to suit but may be worth a second look
        4 - 5: well suited, aligns well to the job seeker, with few downsides 
        """,
        range=(1, 5),
    )
    reasoning: str = fm.guide("1 - 2 sentences explaining the score")


class AppleFMClient:
    """Apple's on-device Foundation Models (macOS 26+, Apple Silicon).

    Uses guided generation: the verdict schema is declared with @fm.generable,
    so the model is constrained to produce it rather than asked for JSON.
    """

    model = "apple_foundation"

    async def assess_job(self, job: Job, criteria_text: str) -> Verdict:
        system_prompt = """
You screen job postings for a job seeker. You are given their criteria and one job posting.
Score whether the job posting is worth their time to review. Err on the side of including a
job: the job seeker would rather review a borderline posting than miss a real opportunity 
        """
        prompt = f"""
# My criteria

{criteria_text}

# Job posting

**{job.title}** at **{job.company}**, in **{job.location}**

--

{job.description}
"""

        session = fm.LanguageModelSession(instructions=system_prompt)
        response = await session.respond(prompt, generating=FMVerdict)

        return Verdict(
            score=response.score,
            matched=response.score >= 4,
            reasoning=response.reasoning,
        )
