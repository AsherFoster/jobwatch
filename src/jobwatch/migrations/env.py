import os
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
    """jobwatch already owns a database URL (config.toml / $JOBWATCH_CONFIG);
    reuse it instead of duplicating it in alembic.ini. Override with
    `-x config=path/to/config.toml`, or by setting `sqlalchemy.url` directly
    in alembic.ini."""
    from jobwatch.config import DEFAULT_CONFIG_PATH, load_config

    config_path = os.environ.get("JOBWATCH_CONFIG") or DEFAULT_CONFIG_PATH
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
    """Run migrations against a live DB, using the URL from `_get_url()`."""
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
