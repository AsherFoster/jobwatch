"""Fetch job postings via JobSpy's anonymous LinkedIn view."""

from __future__ import annotations

import contextlib
import json
from collections.abc import Generator
from datetime import UTC, datetime
from typing import Any
from urllib.parse import urlparse

import structlog

from jobwatch.job_sources.base import JobSource, ScrapedJob
from jobwatch.models import UserSearch

log = structlog.get_logger()


def linkedin_company_slug(url: str | None) -> str | None:
    """Extract the slug from a LinkedIn company URL, e.g.
    https://dk.linkedin.com/company/too-good-to-go -> too-good-to-go."""
    if not url:
        return None
    parsed = urlparse(url)
    host = parsed.hostname or ""
    if host != "linkedin.com" and not host.endswith(".linkedin.com"):
        return None
    parts = [part for part in parsed.path.split("/") if part]
    if len(parts) < 2 or parts[0] != "company":
        return None
    return parts[1].lower()


def _text(record: dict[str, Any], key: str) -> str:
    value = record.get(key)
    return "" if value is None or value != value else str(value)  # NaN check


def search_linkedin(search: UserSearch, hours_old: int) -> Generator[ScrapedJob]:
    # Imported lazily: jobspy pulls in pandas, which is slow to import and not
    # needed by the web UI or tests.
    from jobspy import scrape_jobs

    df = scrape_jobs(
        site_name=["linkedin"],
        search_term=search.search_term,
        location=search.location,
        results_wanted=1000,  # LinkedIn's anonymous view caps out at 1000 anyway
        hours_old=hours_old,
        linkedin_fetch_description=True,
    )
    log.info("Search %r returned %d jobs", search.search_term, len(df))

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

        yield ScrapedJob(
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


linkedin_source = JobSource(id="linkedin", name="LinkedIn", search_function=search_linkedin)
