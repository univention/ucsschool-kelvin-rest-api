import os
from contextlib import asynccontextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import AsyncGenerator

from sqlalchemy import make_url
from sqlalchemy.engine.url import URL
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine


@dataclass(frozen=True, slots=True)
class DatabaseSettings:  # pragma: no cover
    url: URL
    echo: bool = False
    pool_size: int = 10
    max_overflow: int = 20


def _get_url() -> URL:  # pragma: no cover
    # TODO: merge with kelvin-api/ucsschool/kelvin/database.py
    db_uri = os.getenv("UCSSCHOOL_KELVIN_DB_URI")
    if not db_uri:
        raise RuntimeError("UCSSCHOOL_KELVIN_DB_URI environment variable is not set.")
    sqlalchemy_url = make_url(db_uri).set(
        username=os.getenv("UCSSCHOOL_KELVIN_DB_USERNAME"),
        password=Path(
            os.getenv(
                "UCSSCHOOL_KELVIN_DB_PASSWORDFILE", "/etc/ucsschool/kelvin/postgresql-kelvin.secret"
            )
        )
        .read_text()
        .strip(),
    )

    if not sqlalchemy_url.drivername or sqlalchemy_url.drivername == "postgresql":
        sqlalchemy_url = sqlalchemy_url.set(drivername="postgresql+psycopg")
    return sqlalchemy_url


def _build_settings() -> DatabaseSettings:  # pragma: no cover
    return DatabaseSettings(url=_get_url())


def build_engine(settings: DatabaseSettings) -> AsyncEngine:  # pragma: no cover
    """
    Builds a SQLAlchemy AsyncEngine using the provided settings.

    An engine is a shared resource that manages database connections and should typically
    be created once per application.
    """
    return create_async_engine(
        settings.url,
        echo=settings.echo,
        pool_size=settings.pool_size,
        max_overflow=settings.max_overflow,
    )


def build_session_factory(
    engine: AsyncEngine,
) -> async_sessionmaker[AsyncSession]:
    """
    Builds a SQLAlchemy async_sessionmaker (session factory) bound to the provided engine.

    A session factory is used to create new session instances, which are the primary interface
    for interacting with the database in SQLAlchemy.
    """
    return async_sessionmaker(
        bind=engine,
        expire_on_commit=False,
        autoflush=False,
    )


@asynccontextmanager
async def transaction_scope(
    engine: AsyncEngine, session_factory: async_sessionmaker[AsyncSession]
) -> AsyncGenerator[AsyncSession, None]:
    """Async context manager that provides a database session within a transaction.

    Reads connection settings from environment variables (see _get_url).
    Commits automatically on clean exit, rolls back on exception.

    Usage::

        engine = build_engine(_build_settings())
        session_factory = build_session_factory(engine)
        async with transaction_scope(engine, session_factory) as db_session:
            result = await db_session.execute(select(User))
    """
    async with session_factory() as db_session:
        async with db_session.begin():
            yield db_session


@asynccontextmanager
async def session_scope(
    engine: AsyncEngine, session_factory: async_sessionmaker[AsyncSession]
) -> AsyncGenerator[AsyncSession, None]:
    """Async context manager that provides a database session without an automatic transaction.

    Reads connection settings from environment variables (see _get_url).
    Does not automatically commit or roll back; caller is responsible for transaction management.

    NOTE Use that session_scope is cheaper than transaction_scope, so it may be preferable for
         read-only operations or when the caller wants explicit control over transactions.

    Usage::

        engine = build_engine(_build_settings())
        session_factory = build_session_factory(engine)
        async with session_scope(engine, session_factory) as db_session:
            result = await db_session.execute(select(User))
    """
    async with session_factory() as db_session:
        yield db_session
