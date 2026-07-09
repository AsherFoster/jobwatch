"""The scrape -> store -> assess -> notify pipeline."""

from __future__ import annotations

from dataclasses import dataclass, field

import structlog
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from jobwatch.assess import Verdict, assess_job
from jobwatch.config import Config
from jobwatch.llm import LLMClient
from jobwatch.models import Assessment, Job, utcnow
from jobwatch.notify import Notifier
from jobwatch.scraper import ScrapedJob, scrape_search

logger = structlog.getLogger(__name__)


@dataclass
class PipelineResult:
    new_jobs: int = 0
    assessed: int = 0
    notified: list[Job] = field(default_factory=list)


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


def sync_jobs(session: Session, config: Config) -> int:
    """Scrape every configured search and store unseen jobs; returns how many were new."""
    new = 0
    for search in config.searches:
        try:
            scraped = scrape_search(search)
        except Exception:
            logger.exception("Scrape failed for search %r; continuing", search.name)
            continue
        new += store_new_jobs(session, search.name, scraped)
    return new


def assess_single(session: Session, llm: LLMClient, config: Config, job: Job) -> Verdict:
    """(Re-)assess one job, replacing any verdict for the current criteria/model."""
    fingerprint = config.criteria.fingerprint(config.llm.model)
    session.execute(
        delete(Assessment).where(
            Assessment.job_id == job.id, Assessment.criteria_fingerprint == fingerprint
        )
    )
    verdict = assess_job(llm, job, config.criteria.text)
    session.add(
        Assessment(
            job_id=job.id,
            criteria_fingerprint=fingerprint,
            matched=verdict.matched,
            score=verdict.score,
            reasoning=verdict.reasoning,
            model=config.llm.model,
        )
    )
    session.commit()  # commit per job so a crash mid-batch loses nothing
    return verdict


def assess_pending(session: Session, llm: LLMClient, config: Config) -> int:
    """Assess every job that has no assessment for the current criteria/model.

    Covers both newly scraped jobs and the full backlog after a criteria change —
    this is what makes editing config.toml trigger re-analysis.
    """
    fingerprint = config.criteria.fingerprint(config.llm.model)
    assessed_ids = select(Assessment.job_id).where(Assessment.criteria_fingerprint == fingerprint)
    pending = session.scalars(select(Job).where(Job.id.not_in(assessed_ids))).all()

    for job in pending:
        assess_single(session, llm, config, job)
    return len(pending)


def notify_new_matches(session: Session, notifier: Notifier, config: Config) -> list[Job]:
    """Send a single notification for matched jobs that were never announced."""
    fingerprint = config.criteria.fingerprint(config.llm.model)
    matches = session.scalars(
        select(Job)
        .join(Assessment)
        .where(
            Assessment.criteria_fingerprint == fingerprint,
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


def run_pipeline(
    session: Session, config: Config, llm: LLMClient, notifier: Notifier
) -> PipelineResult:
    result = PipelineResult()
    result.new_jobs = sync_jobs(session, config)
    result.assessed = assess_pending(session, llm, config)
    result.notified = notify_new_matches(session, notifier, config)
    logger.info(
        "Pipeline done: %d new jobs, %d assessed, %d notified",
        result.new_jobs,
        result.assessed,
        len(result.notified),
    )
    return result
