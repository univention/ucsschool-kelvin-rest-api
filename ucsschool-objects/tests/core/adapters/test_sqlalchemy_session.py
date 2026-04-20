from __future__ import annotations

import uuid
from collections.abc import AsyncGenerator

import pytest
import pytest_asyncio
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool
from ucsschool_objects.core.adapters.sqlalchemy.session import (
    build_session_factory,
    session_scope,
    transaction_scope,
)
from ucsschool_objects.database_models import Base, School


def _make_school(name: str) -> School:
    return School(
        public_id=uuid.uuid4(),
        record_uid=f"record-{name}",
        source_uid=f"source-{name}",
        name=name,
        display_name={"de": name, "en": name},
        educational_servers=[f"{name}.edu.example"],
        administrative_servers=[f"{name}.adm.example"],
        class_share_file_server=f"{name}.class.example",
        home_share_file_server=f"{name}.home.example",
    )


@pytest_asyncio.fixture
async def sqlite_engine() -> AsyncGenerator[AsyncEngine, None]:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", poolclass=StaticPool)
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    yield engine
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.drop_all)
    await engine.dispose()


@pytest.mark.asyncio
async def test_transaction_scope_commits_on_success(sqlite_engine: AsyncEngine) -> None:
    session_factory = build_session_factory(sqlite_engine)
    school_name = "committed-school"

    async with transaction_scope(sqlite_engine, session_factory) as session:
        session.add(_make_school(school_name))

    async with session_factory() as session:
        count = await session.scalar(
            select(func.count()).select_from(School).where(School.name == school_name)
        )

    assert count == 1


@pytest.mark.asyncio
async def test_transaction_scope_rolls_back_on_exception(sqlite_engine: AsyncEngine) -> None:
    session_factory = build_session_factory(sqlite_engine)
    school_name = "rolled-back-school"

    with pytest.raises(RuntimeError, match="boom"):
        async with transaction_scope(sqlite_engine, session_factory) as session:
            session.add(_make_school(school_name))
            raise RuntimeError("boom")

    async with session_factory() as session:
        count = await session.scalar(
            select(func.count()).select_from(School).where(School.name == school_name)
        )

    assert count == 0


@pytest.mark.asyncio
async def test_session_scope_does_not_commit_implicitly(sqlite_engine: AsyncEngine) -> None:
    session_factory = build_session_factory(sqlite_engine)
    school_name = "not-committed-school"

    async with session_scope(sqlite_engine, session_factory) as session:
        session.add(_make_school(school_name))

    async with session_factory() as session:
        count = await session.scalar(
            select(func.count()).select_from(School).where(School.name == school_name)
        )

    assert count == 0


@pytest.mark.asyncio
async def test_session_scope_allows_explicit_commit(sqlite_engine: AsyncEngine) -> None:
    session_factory = build_session_factory(sqlite_engine)
    school_name = "explicitly-committed-school"

    async with session_scope(sqlite_engine, session_factory) as session:
        session.add(_make_school(school_name))
        await session.commit()

    async with session_factory() as session:
        count = await session.scalar(
            select(func.count()).select_from(School).where(School.name == school_name)
        )

    assert count == 1


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
