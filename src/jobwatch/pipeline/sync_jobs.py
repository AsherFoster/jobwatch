from __future__ import annotations

import math
from collections.abc import Callable, Generator
from dataclasses import dataclass
from datetime import datetime
from urllib.parse import urlparse

import structlog
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from jobwatch.job_sources import JOB_SOURCES
from jobwatch.models import Job, UserSearch, utcnow
from jobwatch.pipeline.sync_companies import ensure_company_details

log = structlog.get_logger()


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


@dataclass
class JobSource:
    id: str
    name: str
    # Yields jobs for a search, restricted to postings at most hours_old hours old.
    search_function: Callable[[UserSearch, int], Generator[ScrapedJob]]


DEFAULT_HOURS_OLD = 24


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


async def store_new_jobs(session: Session, search: UserSearch, scraped: list[ScrapedJob]) -> int:
    """Insert jobs we haven't seen before; returns how many were new."""
    new = 0
    for item in scraped:
        exists = session.scalar(
            select(Job.id).where(Job.site == item.site, Job.external_id == item.external_id)
        )
        if exists:
            continue
        await ensure_company_details(session, item)
        session.add(
            Job(
                site=item.site,
                external_id=item.external_id,
                search_id=search.id,
                title=item.title,
                company=item.company,
                location=item.location,
                url=item.url,
                description=item.description,
                posted_at=item.posted_at,
                raw=item.raw,
            )
        )
        new += 1
    return new


def hours_to_search(session: Session, search: UserSearch) -> int:
    """How far back to search: since this search last found a job, or
    DEFAULT_HOURS_OLD if it never has."""
    last_scraped = session.scalar(
        select(func.max(Job.scraped_at)).where(Job.search_id == search.id)
    )
    if last_scraped is None:
        return DEFAULT_HOURS_OLD
    return math.ceil((utcnow() - last_scraped).total_seconds() / 3600)


async def sync_jobs(session: Session) -> None:
    """Run every configured search against every source and store unseen jobs;
    returns how many were new."""
    searches = session.scalars(select(UserSearch).order_by(UserSearch.id)).all()
    if not searches:
        log.warning("No searches configured; nothing to scrape. Add them at /settings.")
    for search in searches:
        hours_old = hours_to_search(session, search)
        for source in JOB_SOURCES:
            try:
                scraped = list(source.search_function(search, hours_old))
            except Exception:
                log.exception(
                    "Search %r failed on source %r; continuing", search.search_term, source.id
                )
                continue
            log.info("scraped jobs", source=source.id, count=len(scraped))
            new_count = await store_new_jobs(session, search, scraped)
            log.info("saved jobs", source=source.id, count=new_count)
            session.commit()
