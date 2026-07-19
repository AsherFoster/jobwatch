"""awa task-kind dataclasses.

Split out from tasks.py so pipeline modules can enqueue tasks (via
awa.bridge.insert_job_sync) without importing the worker runtime — tasks.py
imports jobwatch.pipeline.sync_jobs, so the reverse import would cycle.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class SyncJobs:
    """Run every configured search against every source and store unseen jobs."""


@dataclass
class AssessJob:
    """Assess one job against its search owner's current criteria."""

    job_id: int
