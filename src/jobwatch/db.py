"""Engine/session setup. SQLite by default, but any SQLAlchemy URL works."""

from __future__ import annotations

from pathlib import Path

from sqlalchemy import Engine, create_engine, event, inspect, text
from sqlalchemy.orm import Session, sessionmaker

from jobwatch.models import Base


def _migrate_legacy_assessments_table(engine: Engine) -> None:
    """One-off fixup for sqlite DBs created before the `invalidated_at` column
    existed. There's no migration framework here, so `create_all()` alone can't
    add a column (or replace the old per-fingerprint unique constraint) on a
    table that already exists — do it by hand, once, idempotently.
    """
    if engine.dialect.name != "sqlite":
        return
    inspector = inspect(engine)
    if "assessments" not in inspector.get_table_names():
        return
    columns = {c["name"] for c in inspector.get_columns("assessments")}
    if "invalidated_at" in columns:
        return

    with engine.begin() as conn:
        conn.execute(text("ALTER TABLE assessments RENAME TO assessments_pre_invalidation"))
    Base.metadata.create_all(engine)  # recreates `assessments` with the current schema
    with engine.begin() as conn:
        # Every pre-existing row was "the" verdict for its (job, fingerprint)
        # pair under the old delete-then-insert scheme, so all map to active.
        columns = "id, job_id, criteria_fingerprint, matched, score, reasoning, model, created_at"
        conn.execute(
            text(
                f"INSERT INTO assessments ({columns}) "
                f"SELECT {columns} FROM assessments_pre_invalidation"
            )
        )
        conn.execute(text("DROP TABLE assessments_pre_invalidation"))


def make_engine(database_url: str) -> Engine:
    if database_url.startswith("sqlite:///"):
        db_path = Path(database_url.removeprefix("sqlite:///"))
        if db_path.parent != Path("."):
            db_path.parent.mkdir(parents=True, exist_ok=True)

    engine = create_engine(database_url)

    if engine.dialect.name == "sqlite":
        # WAL lets the web UI read while the pipeline writes.
        @event.listens_for(engine, "connect")
        def _set_sqlite_pragma(dbapi_connection, _record):
            cursor = dbapi_connection.cursor()
            cursor.execute("PRAGMA journal_mode=WAL")
            cursor.execute("PRAGMA foreign_keys=ON")
            cursor.close()

    _migrate_legacy_assessments_table(engine)
    Base.metadata.create_all(engine)
    return engine


def make_session_factory(engine: Engine) -> sessionmaker[Session]:
    return sessionmaker(engine, expire_on_commit=False)
