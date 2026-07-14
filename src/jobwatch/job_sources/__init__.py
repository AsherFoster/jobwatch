"""Job board sources the pipeline searches. Register new sources here."""

from __future__ import annotations

from jobwatch.job_sources.base import JobSource
from jobwatch.job_sources.linkedin import linkedin_source

JOB_SOURCES: list[JobSource] = [linkedin_source]
