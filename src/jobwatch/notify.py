"""Notification abstraction. Discord webhook today; WebPush could slot in later."""

from __future__ import annotations

from typing import Protocol

import httpx
import structlog

from jobwatch.config import Config
from jobwatch.models import Job

logger = structlog.getLogger(__name__)


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
            lines.append(f"- [{job.title} — {job.company}](<{job.url}>) ({job.location})")
        if len(jobs) > self.MAX_LISTED:
            lines.append(f"…and {len(jobs) - self.MAX_LISTED} more.")
        lines.append(f"Review all: {review_url}")

        response = httpx.post(self._webhook_url, json={"content": "\n".join(lines)}, timeout=30.0)
        response.raise_for_status()
        logger.info("Sent Discord notification for %d jobs", len(jobs))


class NullNotifier:
    """Used when no notification channel is configured."""

    def send_matches(self, jobs: list[Job], review_url: str) -> None:
        logger.warning("No notifier configured; %d matches not announced", len(jobs))


def make_notifier(config: Config) -> Notifier:
    if config.notify.discord is not None:
        return DiscordNotifier(config.notify.discord.webhook_url)
    return NullNotifier()
