import os
from dataclasses import dataclass
from pathlib import Path
from types import TracebackType

from sqlalchemy import make_url
from sqlalchemy.engine.url import URL
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    AsyncSessionTransaction,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.pool import StaticPool
from ucsschool_objects.core.adapters.sqlalchemy.managers import (
    SQLAlchemyGroupManager,
    SQLAlchemyRoleManager,
    SQLAlchemySchoolManager,
    SQLAlchemyUserManager,
)
from ucsschool_objects.core.domain import (
    Group,
    KelvinStorageSession,
    KelvinStorageSessionFactory,
    Manager,
    Role,
    School,
    User,
)


@dataclass(frozen=True, slots=True)
class DatabaseSettings:
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
                "UCSSCHOOL_KELVIN_DB_PASSWORD_FILE", "/etc/ucsschool/kelvin/postgresql-kelvin.secret"
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
    if settings.url.drivername.startswith("sqlite") and settings.url.database == ":memory:":
        return create_async_engine(
            settings.url,
            echo=settings.echo,
            poolclass=StaticPool,
        )

    if settings.url.drivername.startswith("sqlite"):
        return create_async_engine(
            settings.url,
            echo=settings.echo,
        )

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


def build_kelvin_storage_session_factory(
    engine: AsyncEngine,
) -> KelvinStorageSessionFactory:
    """Build a KelvinStorageSessionFactory from an engine.

    This is intended for composition roots so FastAPI and CLI callers do not
    have to construct SQLAlchemy sessions directly.
    """
    session_factory = build_session_factory(engine)
    return KelvinSqlAlchemySessionFactory(session_factory)


class KelvinSqlAlchemySession(KelvinStorageSession):
    """Storage session that binds domain managers to a single SQLAlchemy session."""

    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        *,
        transactional: bool,
    ) -> None:
        self._session_factory = session_factory
        self._transactional = transactional
        self._session: AsyncSession | None = None
        self._transaction: AsyncSessionTransaction | None = None
        self._schools: SQLAlchemySchoolManager | None = None
        self._roles: SQLAlchemyRoleManager | None = None
        self._groups: SQLAlchemyGroupManager | None = None
        self._users: SQLAlchemyUserManager | None = None

    async def __aenter__(self) -> "KelvinSqlAlchemySession":
        self._session = self._session_factory()
        if self._transactional:
            self._transaction = self._session.begin()
            await self._transaction.__aenter__()
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        session = self._require_session()
        try:
            if self._transactional:
                transaction = self._require_transaction()
                await transaction.__aexit__(exc_type, exc, tb)
            elif session.in_transaction():
                # session_scope does not auto-commit on success.
                await session.rollback()
        finally:
            await session.close()
            self._session = None
            self._transaction = None
            self._schools = None
            self._roles = None
            self._groups = None
            self._users = None

    @property
    def schools(self) -> Manager[School]:
        if self._schools is None:
            self._schools = SQLAlchemySchoolManager(self._require_session())
        return self._schools

    @property
    def roles(self) -> Manager[Role]:
        if self._roles is None:
            self._roles = SQLAlchemyRoleManager(self._require_session())
        return self._roles

    @property
    def groups(self) -> Manager[Group]:
        if self._groups is None:
            self._groups = SQLAlchemyGroupManager(self._require_session())
        return self._groups

    @property
    def users(self) -> Manager[User]:
        if self._users is None:
            self._users = SQLAlchemyUserManager(self._require_session())
        return self._users

    @property
    def session(self) -> AsyncSession:
        """Return the active SQLAlchemy session for adapter-level compatibility layers."""

        return self._require_session()

    def _require_session(self) -> AsyncSession:
        if self._session is None:
            raise RuntimeError("Storage session is not active. Use 'async with'.")
        return self._session

    def _require_transaction(self) -> AsyncSessionTransaction:
        if self._transaction is None:
            raise RuntimeError("Storage transaction is not active. Use 'async with'.")
        return self._transaction


class KelvinSqlAlchemySessionFactory(KelvinStorageSessionFactory):
    """Factory that creates SQLAlchemy-backed Kelvin storage sessions."""

    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory

    def transaction_scope(self) -> KelvinSqlAlchemySession:
        return KelvinSqlAlchemySession(self._session_factory, transactional=True)

    def session_scope(self) -> KelvinSqlAlchemySession:
        return KelvinSqlAlchemySession(self._session_factory, transactional=False)
