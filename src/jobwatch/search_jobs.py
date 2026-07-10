"""Source-agnostic types for searching job boards.

Each source lives in jobwatch.job_sources as a JobSource whose search
function turns a SearchConfig into ScrapedJobs.
"""

from __future__ import annotations

from collections.abc import Callable, Generator
from dataclasses import dataclass
from datetime import datetime

from pydantic import BaseModel


class SearchConfig(BaseModel):
    name: str
    search_term: str
    location: str
    results_wanted: int = 100
    hours_old: int = 24


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
    search_function: Callable[[SearchConfig], Generator[ScrapedJob]]
