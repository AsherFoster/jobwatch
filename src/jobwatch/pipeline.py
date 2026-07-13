"""The scrape -> store -> assess -> notify pipeline."""

from __future__ import annotations

import math
from datetime import UTC

import structlog
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from jobwatch.assess import assess_single
from jobwatch.config import config
from jobwatch.criteria import get_criteria_text
from jobwatch.job_sources import JOB_SOURCES
from jobwatch.llm import LLMClient
from jobwatch.models import MATCHED_MIN_SCORE, Assessment, Job, UserSearch, utcnow
from jobwatch.notify import make_notifier
from jobwatch.search_jobs import ScrapedJob

log = structlog.getLogger(__name__)


DEFAULT_HOURS_OLD = 24


def store_new_jobs(session: Session, search: UserSearch, scraped: list[ScrapedJob]) -> int:
    """Insert jobs we haven't seen before; returns how many were new."""
    new = 0
    for item in scraped:
        exists = session.scalar(
            select(Job.id).where(Job.site == item.site, Job.external_id == item.external_id)
        )
        if exists:
            continue
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
    if last_scraped.tzinfo is None:  # SQLite returns naive datetimes; they're UTC
        last_scraped = last_scraped.replace(tzinfo=UTC)
    return max(1, math.ceil((utcnow() - last_scraped).total_seconds() / 3600))


def sync_jobs(session: Session) -> None:
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
            new_count = store_new_jobs(session, search, scraped)
            log.info("saved jobs", source=source.id, count=new_count)
            session.commit()


def get_unassessed_job(session: Session) -> Job | None:
    return session.scalars(
        select(Job)
        .where(Job.active_assessment == None)  # noqa: E711 — relationship NOT EXISTS
        .order_by(Job.scraped_at)
    ).first()


async def assess_pending(session: Session, llm: LLMClient) -> int:
    """Assess every job that has no active verdict (never assessed, or invalidated).

    Editing the criteria does NOT invalidate existing verdicts, so it does NOT
    re-trigger this for jobs that already have one — their old verdict just
    stays displayed as-is. Use assess_single (the web UI's "Reevaluate"
    button, or `assess-jobs JOB_ID`) to refresh a specific job against the
    current criteria on demand.
    """
    criteria_text = get_criteria_text(session)
    if not criteria_text.strip():
        log.warning("Criteria text is empty; skipping assessment.")
        return 0

    job = get_unassessed_job(session)
    count = 0

    while job is not None:
        await assess_single(session, llm, job, criteria_text)
        session.commit()

        count += 1
        job = get_unassessed_job(session)

    return count


def notify_new_matches(session: Session) -> list[Job]:
    """Send a single notification for matched jobs that were never announced."""
    notifier = make_notifier()

    matches = session.scalars(
        select(Job)
        .join(Assessment, Job.active_assessment)
        .where(
            Assessment.score >= MATCHED_MIN_SCORE,
            Job.notified_at.is_(None),
        )
        .order_by(Job.scraped_at)
    ).all()

    if not matches:
        return []

    notifier.send_matches(list(matches), review_url=config.web.base_url)
    now = utcnow()
    for job in matches:
        job.notified_at = now
    session.commit()
    return list(matches)


async def run_pipeline(session: Session, llm: LLMClient) -> None:
    sync_jobs(session)
    await assess_pending(session, llm)
    notify_new_matches(session)
