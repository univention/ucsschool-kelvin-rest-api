import hashlib
import logging
import os
import time
from pathlib import Path

from sqlalchemy import engine_from_config, make_url, pool, text
from ucsschool_objects.database_models import Base

from alembic import context
from ucsschool.kelvin.service.log import setup_logging
from ucsschool.lib.models.utils import env_or_ucr

setup_logging()
logger = logging.getLogger()

config = context.config
target_metadata = Base.metadata

sqlalchemy_url = make_url(env_or_ucr("ucsschool/kelvin/db/uri")).set(
    username=env_or_ucr("ucsschool/kelvin/db/username"),
    password=Path(
        os.getenv("UCSSCHOOL_KELVIN_DB_PASSWORDFILE", "/etc/ucsschool/kelvin/postgresql-kelvin.secret")
    )
    .read_text()
    .strip(),
)

if sqlalchemy_url.drivername == "postgresql":
    sqlalchemy_url = sqlalchemy_url.set(drivername="postgresql+psycopg")

config.set_main_option("sqlalchemy.url", sqlalchemy_url.render_as_string(hide_password=False))


def acquire_lock(connection, timeout_seconds: int = 60) -> bool:
    dialect = connection.dialect.name
    lock_id = int(hashlib.sha256(b"alembic_lock").hexdigest()[:15], 16)
    lock_acquired = False

    if dialect == "postgresql":
        start_time = time.time()
        while time.time() - start_time < timeout_seconds:
            # pg_try_advisory_lock returns True/False immediately
            result = connection.execute(text(f"SELECT pg_try_advisory_lock({lock_id})")).scalar()
            if result:
                lock_acquired = True
                logger.debug("Postgres advisory lock acquired.")
                break
            logger.warning("Waiting for migration lock...")
            time.sleep(2)  # Wait 2 seconds before polling again
        connection.commit()
    else:
        # Don't break other dialects just because we don't support locks.
        # E.g. sqlite
        lock_acquired = True
    return lock_acquired


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode.

    This configures the context with just a URL
    and not an Engine, though an Engine is acceptable
    here as well.  By skipping the Engine creation
    we don't even need a DBAPI to be available.

    Calls to context.execute() here emit the given string to the
    script output.

    """
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations in 'online' mode.

    In this scenario we need to create an Engine
    and associate a connection with the context.

    """
    logger.info("Run alembic database migration")
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    lock_timeout_seconds = 60
    with connectable.connect() as connection:
        lock_acquired = acquire_lock(connection, timeout_seconds=lock_timeout_seconds)
        if lock_acquired:
            context.configure(connection=connection, target_metadata=target_metadata)

            with context.begin_transaction():
                context.run_migrations()
        else:
            raise RuntimeError(
                f"Could not acquire lock after {lock_timeout_seconds}s. Migration aborted."
            )
    logger.info(f"Finished alembic database migration, current revision: {context.get_head_revision()}")


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
