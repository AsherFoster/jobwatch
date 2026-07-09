"""Turn a job description + user criteria into a matched/not-matched verdict."""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass

from jobwatch.llm import LLMClient
from jobwatch.models import Job

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """\
You screen job postings for a job seeker. You are given their criteria and one job posting.
Decide whether the posting is worth their time to review.

Respond with ONLY a JSON object, no other text:
{"matched": true or false, "score": 0-10, "reasoning": "one or two sentences"}

score is how well the job fits the criteria (10 = perfect fit). Err on the side of
including: the job seeker would rather review a borderline posting than miss a real
opportunity. When in doubt, or when the posting is vague, set matched to true. Only set
matched to false when the posting clearly hits a negative criterion or is clearly
irrelevant to the criteria."""


@dataclass
class Verdict:
    matched: bool
    score: int
    reasoning: str


def build_prompt(job: Job, criteria_text: str) -> str:
    return (
        f"## My criteria\n{criteria_text}\n\n"
        f"## Job posting\n"
        f"Title: {job.title}\n"
        f"Company: {job.company}\n"
        f"Location: {job.location}\n\n"
        f"{job.description or '(no description available)'}"
    )


def parse_verdict(text: str) -> Verdict:
    """Parse the LLM response, tolerating chatter around the JSON object."""
    match = re.search(r"\{.*\}", text, re.DOTALL)
    if not match:
        raise ValueError(f"No JSON object in LLM response: {text[:200]!r}")
    data = json.loads(match.group(0))
    return Verdict(
        matched=bool(data["matched"]),
        score=max(0, min(10, int(data.get("score", 0)))),
        reasoning=str(data.get("reasoning", "")),
    )


def assess_job(llm: LLMClient, job: Job, criteria_text: str) -> Verdict:
    response = llm.complete(SYSTEM_PROMPT, build_prompt(job, criteria_text))
    try:
        return parse_verdict(response)
    except ValueError, KeyError, json.JSONDecodeError:
        logger.warning("Unparseable LLM response for job %s: %r", job.id, response[:500])
        return Verdict(
            matched=False, score=0, reasoning=f"LLM response unparseable: {response[:200]}"
        )
