"""The contract between job sources and the pipeline that consumes them."""

from __future__ import annotations

from collections.abc import Callable, Generator
from dataclasses import dataclass
from datetime import datetime

from jobwatch.models import UserSearch


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
