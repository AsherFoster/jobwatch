"""Engine/session setup. SQLite by default, but any SQLAlchemy URL works."""

from __future__ import annotations

from collections.abc import Generator

from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session, sessionmaker

from jobwatch.config import config


engine = create_engine(config.database_url)
session_maker = sessionmaker(engine, expire_on_commit=False)

if engine.dialect.name == "sqlite":
    # WAL lets the web UI read while the pipeline writes.
    @event.listens_for(engine, "connect")
    def _set_sqlite_pragma(dbapi_connection, _record):
        cursor = dbapi_connection.cursor()

        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()


def get_session() -> Generator[Session]:
    """Dependency for getting a sync database session."""
    with session_maker() as session:
        yield session
