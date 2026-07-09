"""Engine/session setup. SQLite by default, but any SQLAlchemy URL works."""

from __future__ import annotations

from pathlib import Path

from alembic import command
from alembic.config import Config as AlembicConfig
from sqlalchemy import Engine, create_engine, event, inspect
from sqlalchemy.orm import Session, sessionmaker

MIGRATIONS_DIR = Path(__file__).parent / "migrations"
BASELINE_REVISION = "0001"  # schema every pre-alembic DB already has


def run_migrations(engine: Engine) -> None:
    """Bring the schema up to date via migrations/versions/.

    Runs against `engine`'s own connection rather than opening a fresh one
    from its URL — required for `sqlite:///:memory:` (a new connection would
    be a different, empty database) and just more efficient for a real file.
    """
    cfg = AlembicConfig()
    cfg.set_main_option("script_location", str(MIGRATIONS_DIR))

    with engine.connect() as connection:
        cfg.attributes["connection"] = connection
        tables = inspect(connection).get_table_names()
        # inspect() implicitly opened a transaction on this connection (SQLAlchemy
        # 2.0 "autobegin"); end it before handing the connection to Alembic, which
        # won't commit a transaction it didn't start itself — leaving it open would
        # silently roll back everything Alembic does below on connection close.
        connection.rollback()
        if "alembic_version" not in tables and "jobs" in tables:
            # Pre-alembic DB (previously created by Base.metadata.create_all()).
            # Its schema already matches the baseline — record that instead of
            # re-running create_table() against tables that already exist.
            command.stamp(cfg, BASELINE_REVISION)
        command.upgrade(cfg, "head")


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

    run_migrations(engine)
    return engine


def make_session_factory(engine: Engine) -> sessionmaker[Session]:
    return sessionmaker(engine, expire_on_commit=False)
