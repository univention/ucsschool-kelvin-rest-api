from __future__ import annotations

import os
import random
import uuid
from collections.abc import AsyncGenerator, Generator
from typing import Any, cast

import pytest
import pytest_asyncio
from pytest import FixtureRequest
from sqlalchemy import event
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool
from testcontainers.postgres import PostgresContainer  # type: ignore[import-untyped]
from tests.test_types import (
    AsyncGroupFactory,
    AsyncGroupTypeFactory,
    AsyncRoleFactory,
    AsyncSchoolFactory,
    AsyncSchoolMembershipFactory,
    AsyncUserFactory,
    GroupDataFactory,
    ModelFactory,
    RoleDataFactory,
    SchoolDataFactory,
    UserDataFactory,
)
from ucsschool_objects.database_models import (
    Base,
    Group,
    Role,
    School,
    SchoolMembership,
    User,
)

POSTGRES_TEST_URL_ENV = "CORELIB_POSTGRES_TEST_URL"


@pytest.fixture(scope="session")
def unset_sentinel() -> object:
    return object()


def _drop_unset_values(data: dict[str, object], unset_sentinel: object) -> dict[str, object]:
    return {key: value for key, value in data.items() if value is not unset_sentinel}


@pytest_asyncio.fixture(scope="session")
async def db_engine() -> AsyncGenerator[AsyncEngine, None]:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", poolclass=StaticPool)

    @event.listens_for(engine.sync_engine, "connect")
    def set_sqlite_pragma(dbapi_connection: Any, _connection_record: Any) -> None:
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    yield engine
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.drop_all)
    await engine.dispose()


@pytest.fixture(scope="session")
def postgres_db_url() -> Generator[str | None, None, None]:
    database_url = os.getenv(POSTGRES_TEST_URL_ENV)
    is_ci = os.getenv("CI", "false") == "true"  # Avoid hitting the docker registry pull limit
    if not database_url:
        if not is_ci:
            with PostgresContainer("postgres:15", driver="psycopg") as pg:
                yield pg.get_connection_url()

        else:
            pytest.skip(f"Set {POSTGRES_TEST_URL_ENV} to run PostgreSQL corelib tests.")
    else:
        yield database_url


@pytest_asyncio.fixture(scope="session")
async def postgres_db_engine(postgres_db_url: str | None) -> AsyncGenerator[AsyncEngine | None, None]:
    if not postgres_db_url:
        yield None
        return
    if postgres_db_url.startswith("postgresql://"):
        postgres_db_url = postgres_db_url.replace("postgresql://", "postgresql+psycopg://", 1)

    engine = create_async_engine(postgres_db_url)
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    yield engine
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.drop_all)
    await engine.dispose()


@pytest_asyncio.fixture
async def db_session(db_engine: AsyncEngine) -> AsyncGenerator[AsyncSession, None]:
    async with db_engine.connect() as connection:
        transaction = await connection.begin()
        session = async_sessionmaker(bind=connection, expire_on_commit=False, class_=AsyncSession)()
        await session.begin_nested()
        try:
            yield session
        finally:
            await session.close()
            await transaction.rollback()


@pytest_asyncio.fixture
async def postgres_db_session(postgres_db_engine: AsyncEngine) -> AsyncGenerator[AsyncSession, None]:
    async with postgres_db_engine.connect() as connection:
        transaction = await connection.begin()
        session = async_sessionmaker(bind=connection, expire_on_commit=False, class_=AsyncSession)()
        await session.begin_nested()
        try:
            yield session
        finally:
            await session.close()
            await transaction.rollback()


@pytest.fixture
def model_factory(request: FixtureRequest) -> ModelFactory:
    """Generic fixture that resolves to a specific factory based on param."""
    return cast(ModelFactory, request.getfixturevalue(request.param))


@pytest.fixture
def model_factory2(request: FixtureRequest) -> ModelFactory:
    """There are tests, which need to combine two different model factories."""
    return cast(ModelFactory, request.getfixturevalue(request.param))


@pytest.fixture
def school_data_factory(faker: Any) -> SchoolDataFactory:
    def _school_data_factory() -> dict[str, object]:
        return {
            "public_id": uuid.uuid4(),
            "record_uid": faker.unique.ssn(),
            "source_uid": faker.unique.ssn(),
            "name": faker.unique.company(),
            "display_name": {"de": faker.name(), "en": faker.name()},
            "educational_servers": [faker.domain_name() for _ in range(5)],
            "administrative_servers": [faker.domain_name() for _ in range(5)],
            "class_share_file_server": faker.domain_name(),
            "home_share_file_server": faker.domain_name(),
        }

    return _school_data_factory


@pytest.fixture
def school_factory(
    db_session: AsyncSession,
    school_data_factory: SchoolDataFactory,
    unset_sentinel: object,
) -> AsyncSchoolFactory:
    async def _factory(persisted: bool = True, **overrides: object) -> School:
        target_session = cast(AsyncSession, overrides.pop("db_session", db_session))
        school_data: dict[str, object] = school_data_factory()
        school_data.update(overrides)
        school = School(**_drop_unset_values(school_data, unset_sentinel))
        if persisted:
            target_session.add(school)
            await target_session.flush()
        return school

    return _factory


@pytest.fixture
def group_type_factory(role_factory: AsyncRoleFactory) -> AsyncGroupTypeFactory:
    return role_factory


@pytest.fixture
def role_data_factory(faker: Any) -> RoleDataFactory:
    def _role_data_factory() -> dict[str, object]:
        return {
            "public_id": uuid.uuid4(),
            "name": faker.unique.name(),
            "display_name": {"de": faker.name(), "en": faker.name()},
        }

    return _role_data_factory


@pytest.fixture
def role_factory(
    db_session: AsyncSession,
    role_data_factory: RoleDataFactory,
    unset_sentinel: object,
) -> AsyncRoleFactory:
    async def _factory(persisted: bool = True, **overrides: object) -> Role:
        target_session = cast(AsyncSession, overrides.pop("db_session", db_session))
        role_data: dict[str, object] = role_data_factory()
        role_data.update(overrides)
        role = Role(**_drop_unset_values(role_data, unset_sentinel))
        if persisted:
            target_session.add(role)
            await target_session.flush()
        return role

    return _factory


@pytest.fixture
def group_data_factory(faker: Any) -> GroupDataFactory:
    def _group_data_factory() -> dict[str, object]:
        return {
            "public_id": uuid.uuid4(),
            "record_uid": faker.unique.ssn(),
            "source_uid": faker.unique.ssn(),
            "name": faker.unique.name(),
            "display_name": {"de": faker.name(), "en": faker.name()},
            "has_share": random.choice([True, False]),  # nosec
            "email": faker.email(),
            "school": None,
        }

    return _group_data_factory


@pytest.fixture
def group_factory(
    db_session: AsyncSession,
    group_data_factory: GroupDataFactory,
    role_factory: AsyncRoleFactory,
    school_factory: AsyncSchoolFactory,
    unset_sentinel: object,
) -> AsyncGroupFactory:
    async def _factory(persisted: bool = True, **overrides: object) -> Group:
        target_session = cast(AsyncSession, overrides.pop("db_session", db_session))
        group_type_override = overrides.pop("group_type", None)
        group_data: dict[str, object] = group_data_factory()
        group_data.update(overrides)
        group = Group(**_drop_unset_values(group_data, unset_sentinel))
        if group_type_override is not None:
            group.group_type = cast(
                list[Role],
                group_type_override if isinstance(group_type_override, list) else [group_type_override],
            )
        else:
            role = await role_factory(db_session=target_session)
            group.group_type = [role]
        if "school" not in overrides:
            group.school = await school_factory(persisted=False, db_session=target_session)
        if persisted:
            target_session.add(group)
            await target_session.flush()
        return group

    return _factory


@pytest.fixture
def user_data_factory(faker: Any) -> UserDataFactory:
    def _user_data_factory() -> dict[str, object]:
        return {
            "public_id": uuid.uuid4(),
            "name": faker.unique.user_name(),
            "firstname": faker.first_name(),
            "lastname": faker.last_name(),
            "email": faker.unique.email(),
            "record_uid": faker.unique.ssn(),
            "source_uid": faker.unique.ssn(),
            "birthday": faker.date_object(),
            "expiration_date": faker.date_object(),
            "active": random.choice([True, False]),  # nosec
        }

    return _user_data_factory


@pytest.fixture
def user_factory(
    db_session: AsyncSession,
    user_data_factory: UserDataFactory,
    unset_sentinel: object,
) -> AsyncUserFactory:
    async def _factory(persisted: bool = True, **overrides: object) -> User:
        target_session = cast(AsyncSession, overrides.pop("db_session", db_session))
        user_data: dict[str, object] = user_data_factory()
        user_data.update(overrides)
        user = User(**_drop_unset_values(user_data, unset_sentinel))
        if persisted:
            target_session.add(user)
            await target_session.flush()
        return user

    return _factory


@pytest.fixture(name="school_membership_factory")
def membership_factory(
    db_session: AsyncSession,
    school_factory: AsyncSchoolFactory,
    user_factory: AsyncUserFactory,
    unset_sentinel: object,
) -> AsyncSchoolMembershipFactory:
    async def _factory(persisted: bool = True, **overrides: object) -> SchoolMembership:
        target_session = cast(AsyncSession, overrides.pop("db_session", db_session))
        membership_data: dict[str, object] = {
            "user": None,
            "school": None,
            "is_primary": False,
            "primary_user_constraint": None,
        }
        membership_data.update(overrides)
        membership = SchoolMembership(**_drop_unset_values(membership_data, unset_sentinel))
        if "user" not in overrides:
            membership.user = await user_factory(persisted=False, db_session=target_session)
        if "school" not in overrides:
            membership.school = await school_factory(persisted=False, db_session=target_session)
        if persisted:
            target_session.add(membership)
            await target_session.flush()
        return membership

    return _factory
