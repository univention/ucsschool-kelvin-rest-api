import hashlib
import logging
import os
import time
from contextlib import contextmanager
from pathlib import Path

from sqlalchemy import engine_from_config, make_url, pool, text
from ucsschool_objects.database_models import Base

from alembic import context
from alembic.migration import MigrationContext
from alembic.script import ScriptDirectory
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


def _advisory_lock_id() -> int:
    return int(hashlib.sha256(b"alembic_lock").hexdigest()[:15], 16)


@contextmanager
def advisory_lock(connection, timeout_seconds: int = 60):
    dialect = connection.dialect.name
    lock_id = _advisory_lock_id()
    lock_acquired = False

    try:
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

            if not lock_acquired:
                raise RuntimeError(
                    f"Could not acquire lock after {timeout_seconds}s. Migration aborted."
                )

        yield
    finally:
        if dialect != "postgresql" or not lock_acquired:
            return

        result = connection.execute(text(f"SELECT pg_advisory_unlock({lock_id})")).scalar()
        if result:
            logger.debug("Postgres advisory lock released.")
        else:
            logger.warning("Postgres advisory lock was not held when release was attempted.")


def get_current_db_revision(connection) -> str | None:
    migration_context = MigrationContext.configure(connection)
    return migration_context.get_current_revision()


def get_revision_transitions(current_revision: str | None) -> list[str]:
    script_dir = ScriptDirectory.from_config(config)
    heads = script_dir.get_heads()
    if not heads:
        return []

    if len(heads) > 1:
        raise AssertionError("Multiple Alembic heads found: %s", ", ".join(heads))

    head = heads[0]
    revisions = list(script_dir.iterate_revisions(head, current_revision))
    revisions.reverse()

    transitions = []
    for revision in revisions:
        down_revision = revision.down_revision
        if isinstance(down_revision, tuple):
            source = ",".join(down_revision)
        else:
            source = down_revision or "<base>"
        if revision.revision == head:
            transitions.append(f"{source} -> {revision.revision} (head), {revision.doc}")
        else:
            transitions.append(f"{source} -> {revision.revision}, {revision.doc}")
    return transitions


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
        with advisory_lock(connection, timeout_seconds=lock_timeout_seconds):
            current_revision = get_current_db_revision(connection)
            logger.info("Migration starting point: %s", current_revision or "<base>")

            logger.info("Migration plan:")
            transitions = get_revision_transitions(current_revision)
            if transitions:
                for transition in transitions:
                    logger.info(transition)
            else:
                logger.info("No pending migrations.")

            logger.info("Migration log:")
            context.configure(connection=connection, target_metadata=target_metadata)

            with context.begin_transaction():
                context.run_migrations()

            current_revision = get_current_db_revision(connection)
    logger.info("Finished alembic database migration, current revision: %s", current_revision)


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
