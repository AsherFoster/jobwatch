"""Engine/session setup. SQLite by default, but any SQLAlchemy URL works."""

from __future__ import annotations

from pathlib import Path

from sqlalchemy import Engine, create_engine, event
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from jobwatch.models import Base


def make_engine(database_url: str) -> Engine:
    if database_url.startswith("sqlite:///"):
        db_path = Path(database_url.removeprefix("sqlite:///"))
        if db_path.parent != Path("."):
            db_path.parent.mkdir(parents=True, exist_ok=True)

    if database_url == "sqlite:///:memory:":
        # Plain :memory: hands out a fresh, empty DB per connection by
        # default — fine for one thread, but e.g. FastAPI's TestClient calls
        # sync routes from a worker thread. Pin it to a single connection
        # shared across threads, so callers (tests) see one consistent DB.
        engine = create_engine(
            database_url, poolclass=StaticPool, connect_args={"check_same_thread": False}
        )
    else:
        engine = create_engine(database_url)

    if engine.dialect.name == "sqlite":
        # WAL lets the web UI read while the pipeline writes.
        @event.listens_for(engine, "connect")
        def _set_sqlite_pragma(dbapi_connection, _record):
            cursor = dbapi_connection.cursor()
            cursor.execute("PRAGMA journal_mode=WAL")
            cursor.execute("PRAGMA foreign_keys=ON")
            cursor.close()

    # Creates any tables that don't exist yet — fine for a brand new database,
    # a no-op for one that's already up to date. Doesn't alter existing tables;
    # schema changes to a live database are applied manually with Alembic (see
    # src/jobwatch/migrations/ and the README).
    Base.metadata.create_all(engine)
    return engine


def make_session_factory(engine: Engine) -> sessionmaker[Session]:
    return sessionmaker(engine, expire_on_commit=False)
