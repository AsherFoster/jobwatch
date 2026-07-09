from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, pool

from jobwatch.models import Base

# this is the Alembic Config object, which provides
# access to the values within the .ini file in use.
config = context.config

# Interpret the config file for Python logging.
# This line sets up loggers basically.
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def _get_url() -> str:
    """jobwatch already owns a database URL (config.toml / --config); reuse it
    instead of duplicating it in alembic.ini, unless the caller (`db.py`, or a
    `-x db_url=...` override) has already put one in place."""
    url = config.get_main_option("sqlalchemy.url")
    if url:
        return url
    from jobwatch.config import DEFAULT_CONFIG_PATH, load_config

    config_path = context.get_x_argument(as_dictionary=True).get("config", DEFAULT_CONFIG_PATH)
    return load_config(config_path).database_url


def run_migrations_offline() -> None:
    """Run migrations without a live DB connection, emitting SQL to stdout."""
    context.configure(
        url=_get_url(),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations against a live DB.

    When invoked from `jobwatch.db.run_migrations()` we're handed an existing
    Connection (config.attributes["connection"]) so we share the app's engine
    — this matters for sqlite (a fresh connection to `sqlite:///:memory:`
    would be a different, empty database) and avoids a second pool for the
    same file DB. A bare `alembic upgrade head` from the CLI has no such
    connection, so it opens its own using the URL from `_get_url()`.
    """
    connection = config.attributes.get("connection")
    if connection is not None:
        context.configure(connection=connection, target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()
        return

    section = config.get_section(config.config_ini_section, {})
    section["sqlalchemy.url"] = _get_url()
    connectable = engine_from_config(section, prefix="sqlalchemy.", poolclass=pool.NullPool)
    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
