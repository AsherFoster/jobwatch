"""Notification abstraction. Discord webhook today; WebPush could slot in later."""

from __future__ import annotations

from typing import Protocol

import httpx2
import structlog
from sqlalchemy import select
from sqlalchemy.orm import Session

from jobwatch.config import config
from jobwatch.models import MATCHED_MIN_SCORE, Assessment, Job, utcnow

log = structlog.get_logger()


class Notifier(Protocol):
    def send_matches(self, jobs: list[Job], review_url: str) -> None:
        """Send one notification covering all newly matched jobs."""
        ...


class DiscordNotifier:
    MAX_LISTED = 10

    def __init__(self, webhook_url: str) -> None:
        self._webhook_url = webhook_url

    def send_matches(self, jobs: list[Job], review_url: str) -> None:
        lines = [f"**{len(jobs)} new job match{'es' if len(jobs) != 1 else ''}**"]
        for job in jobs[: self.MAX_LISTED]:
            company = job.company.name
            lines.append(f"- [{job.title} — {company}](<{job.url}>) ({job.location})")
        if len(jobs) > self.MAX_LISTED:
            lines.append(f"…and {len(jobs) - self.MAX_LISTED} more.")
        lines.append(f"Review all: {review_url}")

        response = httpx2.post(self._webhook_url, json={"content": "\n".join(lines)}, timeout=30.0)
        response.raise_for_status()
        log.info("Sent Discord notification for %d jobs", len(jobs))


class NullNotifier:
    """Used when no notification channel is configured."""

    def send_matches(self, jobs: list[Job], review_url: str) -> None:
        log.warning("No notifier configured; %d matches not announced", len(jobs))


def make_notifier() -> Notifier:
    if config.notify.discord is not None:
        return DiscordNotifier(config.notify.discord.webhook_url)
    return NullNotifier()


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
