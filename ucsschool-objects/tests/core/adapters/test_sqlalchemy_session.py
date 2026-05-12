from __future__ import annotations

import pathlib
import uuid
from typing import TYPE_CHECKING, cast

import pytest
import pytest_asyncio
from sqlalchemy import func, make_url, select
from ucsschool_objects.core.adapters.sqlalchemy.session import (
    DatabaseSettings,
    KelvinSqlAlchemySessionFactory,
    _read_env_or_file,
    build_engine,
    build_kelvin_storage_session_factory,
    build_session_factory,
)
from ucsschool_objects.database_models import Base, School

if TYPE_CHECKING:
    from collections.abc import AsyncGenerator

    from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker


def _make_school(name: str) -> School:
    return School(
        public_id=uuid.uuid4(),
        record_uid=f"record-{name}",
        source_uid=f"source-{name}",
        name=name,
        display_name=name,
        educational_servers=[f"{name}.edu.example"],
        administrative_servers=[f"{name}.adm.example"],
        class_share_file_server=f"{name}.class.example",
        home_share_file_server=f"{name}.home.example",
    )


@pytest_asyncio.fixture
async def sqlite_engine() -> AsyncGenerator[AsyncEngine, None]:
    settings = DatabaseSettings(url=make_url("sqlite+aiosqlite:///:memory:"))
    engine = build_engine(settings)
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    yield engine
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.drop_all)
    await engine.dispose()


@pytest.fixture
def wired_storage_factory(sqlite_engine: AsyncEngine) -> KelvinSqlAlchemySessionFactory:
    return cast("KelvinSqlAlchemySessionFactory", build_kelvin_storage_session_factory(sqlite_engine))


@pytest.mark.asyncio
async def test_build_session_factory_disables_autoflush(sqlite_engine: AsyncEngine) -> None:
    session_factory: async_sessionmaker[AsyncSession] = build_session_factory(sqlite_engine)
    school_name = "pending-school"

    async with session_factory() as session:
        session.add(_make_school(school_name))
        count = await session.scalar(
            select(func.count()).select_from(School).where(School.name == school_name)
        )

    assert count == 0


@pytest.mark.asyncio
async def test_transaction_scope_commits_on_success(
    sqlite_engine: AsyncEngine, wired_storage_factory: KelvinSqlAlchemySessionFactory
) -> None:
    school_name = "committed-school"

    async with wired_storage_factory.transaction_scope() as storage:
        storage.session.add(_make_school(school_name))

    session_factory = build_session_factory(sqlite_engine)
    async with session_factory() as session:
        count = await session.scalar(
            select(func.count()).select_from(School).where(School.name == school_name)
        )

    assert count == 1


@pytest.mark.asyncio
async def test_transaction_scope_rolls_back_on_exception(
    sqlite_engine: AsyncEngine, wired_storage_factory: KelvinSqlAlchemySessionFactory
) -> None:
    school_name = "rolled-back-school"

    with pytest.raises(RuntimeError, match="boom"):
        async with wired_storage_factory.transaction_scope() as storage:
            storage.session.add(_make_school(school_name))
            raise RuntimeError("boom")

    session_factory = build_session_factory(sqlite_engine)
    async with session_factory() as session:
        count = await session.scalar(
            select(func.count()).select_from(School).where(School.name == school_name)
        )

    assert count == 0


@pytest.mark.asyncio
async def test_session_scope_does_not_commit_implicitly(
    sqlite_engine: AsyncEngine, wired_storage_factory: KelvinSqlAlchemySessionFactory
) -> None:
    school_name = "not-committed-by-session-scope"

    async with wired_storage_factory.session_scope() as storage:
        storage.session.add(_make_school(school_name))

    session_factory = build_session_factory(sqlite_engine)
    async with session_factory() as session:
        count = await session.scalar(
            select(func.count()).select_from(School).where(School.name == school_name)
        )

    assert count == 0


@pytest.mark.asyncio
async def test_session_scope_allows_explicit_commit(
    sqlite_engine: AsyncEngine, wired_storage_factory: KelvinSqlAlchemySessionFactory
) -> None:
    school_name = "explicitly-committed-school"

    async with wired_storage_factory.session_scope() as storage:
        storage.session.add(_make_school(school_name))
        await storage.session.commit()

    session_factory = build_session_factory(sqlite_engine)
    async with session_factory() as session:
        count = await session.scalar(
            select(func.count()).select_from(School).where(School.name == school_name)
        )

    assert count == 1


@pytest.mark.asyncio
async def test_session_scope_rolls_back_on_exception(
    sqlite_engine: AsyncEngine, wired_storage_factory: KelvinSqlAlchemySessionFactory
) -> None:
    school_name = "uow-session-rollback"

    with pytest.raises(RuntimeError, match="boom"):
        async with wired_storage_factory.session_scope() as storage:
            storage.session.add(_make_school(school_name))
            raise RuntimeError("boom")

    session_factory = build_session_factory(sqlite_engine)
    async with session_factory() as session:
        count = await session.scalar(
            select(func.count()).select_from(School).where(School.name == school_name)
        )

    assert count == 0


@pytest.mark.asyncio
@pytest.mark.parametrize("prop_name", ["schools", "roles", "groups", "users"])
async def test_protocol_port_getter(
    wired_storage_factory: KelvinSqlAlchemySessionFactory,
    prop_name: str,
) -> None:
    async with wired_storage_factory.transaction_scope() as storage:
        first = getattr(storage, prop_name)
        second = getattr(storage, prop_name)
    assert first is second


@pytest.mark.asyncio
@pytest.mark.parametrize("prop_name", ["session", "schools", "roles", "groups", "users"])
async def test_raises_when_session_not_active(
    wired_storage_factory: KelvinSqlAlchemySessionFactory,
    prop_name: str,
) -> None:
    storage = wired_storage_factory.transaction_scope()
    with pytest.raises(RuntimeError, match="Storage session is not active"):
        getattr(storage, prop_name)


@pytest.mark.asyncio
async def test_require_transaction_raises_when_not_active(
    wired_storage_factory: KelvinSqlAlchemySessionFactory,
) -> None:
    storage = wired_storage_factory.transaction_scope()
    with pytest.raises(RuntimeError, match="Storage transaction is not active"):
        storage._require_transaction()


def test_read_env_or_file_reads_env_var(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MY_VAR", "direct-value")
    assert _read_env_or_file("MY_VAR", "MY_VAR_FILE") == "direct-value"


def test_read_env_or_file_reads_file(tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch) -> None:
    secret_file = tmp_path / "secret.txt"
    secret_file.write_text("file-value\n")
    monkeypatch.delenv("MY_VAR", raising=False)
    monkeypatch.setenv("MY_VAR_FILE", str(secret_file))
    assert _read_env_or_file("MY_VAR", "MY_VAR_FILE") == "file-value"


def test_read_env_or_file_raises_when_neither_set(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("MY_VAR", raising=False)
    monkeypatch.delenv("MY_VAR_FILE", raising=False)
    with pytest.raises(RuntimeError, match="Neither MY_VAR nor MY_VAR_FILE is set"):
        _read_env_or_file("MY_VAR", "MY_VAR_FILE")
