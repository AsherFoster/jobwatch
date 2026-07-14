"""Engine/session setup. SQLite by default, but any SQLAlchemy URL works."""

from __future__ import annotations

from collections.abc import Generator

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from jobwatch.config import config

engine = create_engine(config.database_url)
session_maker = sessionmaker(engine, expire_on_commit=False)


def get_session() -> Generator[Session]:
    """Dependency for getting a sync database session."""
    with session_maker() as session:
        yield session
