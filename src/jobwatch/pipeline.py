"""The scrape -> store -> assess -> notify pipeline."""

from __future__ import annotations

import structlog
from sqlalchemy import select
from sqlalchemy.orm import Session

from jobwatch.assess import assess_single
from jobwatch.config import config
from jobwatch.criteria import get_criteria_text
from jobwatch.llm import LLMClient
from jobwatch.models import Assessment, Job, utcnow
from jobwatch.notify import make_notifier
from jobwatch.scraper import ScrapedJob, scrape_search
from jobwatch.searches import get_searches

logger = structlog.getLogger(__name__)


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
    session.commit()
    return new


def sync_jobs(session: Session) -> int:
    """Scrape every configured search and store unseen jobs; returns how many were new."""
    searches = get_searches(session)
    if not searches:
        logger.warning("No searches configured; nothing to scrape. See searches.py.")
    new = 0
    for search in searches:
        try:
            scraped = scrape_search(search)
        except Exception:
            logger.exception("Scrape failed for search %r; continuing", search.name)
            continue
        new += store_new_jobs(session, search.name, scraped)
    return new


def get_unassessed_job(session: Session) -> Job | None:
    return session.scalars(
        select(Job)
        .where(Job.active_assessment == None)  # noqa: E711 — relationship NOT EXISTS
        .order_by(Job.scraped_at)
    ).first()


def assess_pending(session: Session, llm: LLMClient) -> int:
    """Assess every job that has no active verdict (never assessed, or invalidated).

    Editing the criteria does NOT invalidate existing verdicts, so it does NOT
    re-trigger this for jobs that already have one — their old verdict just
    stays displayed as-is. Use assess_single (the web UI's "Reevaluate"
    button, or `assess-jobs JOB_ID`) to refresh a specific job against the
    current criteria on demand.
    """
    criteria_text = get_criteria_text(session)
    if not criteria_text.strip():
        logger.warning("Criteria text is empty; skipping assessment.")
        return 0

    job = get_unassessed_job(session)
    count = 0

    while job is not None:
        assess_single(session, llm, job, criteria_text)
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
            Assessment.matched,
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


def run_pipeline(session: Session, llm: LLMClient) -> None:
    sync_jobs(session)
    assess_pending(session, llm)
    notify_new_matches(session)
