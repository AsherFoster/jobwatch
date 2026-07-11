"""The scrape -> store -> assess -> notify pipeline."""

from __future__ import annotations

import structlog
from sqlalchemy import select
from sqlalchemy.orm import Session

from jobwatch.assess import assess_single
from jobwatch.config import config
from jobwatch.criteria import get_criteria_text
from jobwatch.job_sources import JOB_SOURCES
from jobwatch.llm import LLMClient
from jobwatch.models import MATCHED_MIN_SCORE, Assessment, Job, utcnow
from jobwatch.notify import make_notifier
from jobwatch.search_jobs import ScrapedJob
from jobwatch.searches import get_searches

log = structlog.getLogger(__name__)


def store_new_jobs(session: Session, search_name: str, scraped: list[ScrapedJob]) -> int:
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
                search_name=search_name,
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


def sync_jobs(session: Session) -> None:
    """Run every configured search against every source and store unseen jobs;
    returns how many were new."""
    searches = get_searches(session)
    if not searches:
        log.warning("No searches configured; nothing to scrape. See searches.py.")
    for search in searches:
        for source in JOB_SOURCES:
            try:
                scraped = list(source.search_function(search))
            except Exception:
                log.exception("Search %r failed on source %r; continuing", search.name, source.id)
                continue
            log.info("scraped jobs", source=source.id, count=len(scraped))
            new_count = store_new_jobs(session, search.name, scraped)
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
