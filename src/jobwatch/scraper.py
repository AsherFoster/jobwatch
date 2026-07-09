"""Fetch job postings via JobSpy's anonymous LinkedIn view."""

from __future__ import annotations

import contextlib
import json
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

import structlog

from jobwatch.config import SearchConfig

logger = structlog.getLogger(__name__)


@dataclass
class ScrapedJob:
    site: str
    external_id: str
    title: str
    company: str
    location: str
    url: str
    description: str
    posted_at: datetime | None
    raw: str  # full record as JSON, for re-analysis


def _text(record: dict[str, Any], key: str) -> str:
    value = record.get(key)
    return "" if value is None or value != value else str(value)  # NaN check


def scrape_search(search: SearchConfig) -> list[ScrapedJob]:
    # Imported lazily: jobspy pulls in pandas, which is slow to import and not
    # needed by the web UI or tests.
    from jobspy import scrape_jobs

    df = scrape_jobs(
        site_name=["linkedin"],
        search_term=search.search_term,
        location=search.location,
        results_wanted=search.results_wanted,
        hours_old=search.hours_old,
        linkedin_fetch_description=True,
    )
    logger.info("Search %r returned %d jobs", search.name, len(df))

    jobs: list[ScrapedJob] = []
    for record in df.to_dict(orient="records"):
        url = _text(record, "job_url")
        external_id = _text(record, "id") or url
        if not url or not external_id:
            continue

        posted_at = None
        date_posted = record.get("date_posted")
        if isinstance(date_posted, datetime):
            posted_at = date_posted if date_posted.tzinfo else date_posted.replace(tzinfo=UTC)
        elif date_posted is not None and date_posted == date_posted:
            with contextlib.suppress(ValueError):
                posted_at = datetime.fromisoformat(str(date_posted)).replace(tzinfo=UTC)

        jobs.append(
            ScrapedJob(
                site=_text(record, "site") or "linkedin",
                external_id=external_id,
                title=_text(record, "title"),
                company=_text(record, "company"),
                location=_text(record, "location"),
                url=url,
                description=_text(record, "description"),
                posted_at=posted_at,
                raw=json.dumps(record, default=str),
            )
        )
    return jobs
