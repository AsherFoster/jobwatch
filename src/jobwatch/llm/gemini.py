import re
from typing import Annotated

import structlog
from google import genai
from google.genai.interactions import Interaction
from pydantic import BaseModel, ConfigDict, Field

from jobwatch.config import config
from jobwatch.llm import Verdict
from jobwatch.models import Job

log = structlog.get_logger()

# Company descriptions are a lightweight, high-frequency task; always uses
# Gemini (with Google Search) regardless of the configured assessment LLM.
COMPANY_DESCRIPTION_MODEL = "gemini-3.1-flash-lite"


async def generate_company_description(company: str) -> str:
    """One-sentence description of a company, grounded via Google Search."""
    api_key = config.gemini.api_key if config.gemini else None
    client = genai.Client(api_key=api_key)
    interaction = await client.aio.interactions.create(
        model=COMPANY_DESCRIPTION_MODEL,
        input=(
            f"In exactly one sentence, describe what the company {company!r} does. "
            "Use Google Search to find out. Respond with only that sentence."
        ),
        tools=[{"type": "google_search"}],
        store=False,
    )

    assert isinstance(interaction, Interaction)  # stream=False never returns a stream
    if interaction.status != "completed":
        raise ValueError("gemini request was not successful")

    description = (interaction.output_text or "").strip()
    if not description:
        raise ValueError("gemini returned an empty description")
    return description


class GeminiVerdict(BaseModel):
    model_config = ConfigDict(use_attribute_docstrings=True)

    summary: str
    """
    1 line objectively summarising the job. Assume title, company, and location are already explained.
    
    Bad: Software Engineer at Example Corp in Copenhagen, a company focussed on widgets
    Good: Backend focussed role in the Operations team, focussed on integrations, with on-call responsibilities.
    """
    summary_positives: str
    """
    1 line summarising summarising why is this role a good fit for the job seeker.
    Must be very direct, brief, and to the point. Don't pad - only mention notable upsides.
    
    Bad: This role would be good for the job seeker because it matches their preferred language of Python
    Good: Python & TypeScript focussed, relocation support offered, high autonomy.
    """
    summary_negatives: str
    """
    1 line summarising why this job would NOT be a good fit for the job seeker.
    Must be very direct, brief, and to the point. Don't pad - only mention notable downsides.
    
    Bad: The role requires security clearance, which may present a significant hurdle or disqualification.
    Good: Requires NATO clearance (ineligible) and Rust experience.  
    """

    reasoning: str
    """
    2 sentences of reasoning behind how this job is scored.
    Should be direct and to the point, with no filler.
    """

    score: Annotated[int, Field(strict=True, ge=1, le=5)]
    """
    1 - 2: not a match, many downsides and no redeeming qualities
    3: uncertain, doesn't appear to suit but may be worth a second look
    4 - 5: well suited, aligns well to the job seeker, with few downsides
    """


class GeminiClient:
    def __init__(self, model: str, api_key: str) -> None:
        self._client = genai.Client(api_key=api_key)
        self.model = model

    async def assess_job(self, job: Job, criteria_text: str) -> Verdict:
        system_prompt = """
You are a job reviewer, screening job postings for a job seeker. Given their criteria and a single job posting,
explain whether this job is relevant to them or not, and worth their time reviewing further.

Responses should be directed _at_ the job seeker, and should be brief and direct.

Avoid explaining the obvious. Do not say "requires Rust experience, which you do not have", instead just say "requires Rust experience" 
        """

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
            summary=model_verdict.summary,
            summary_positives=model_verdict.summary_positives,
            summary_negatives=model_verdict.summary_negatives,
        )
