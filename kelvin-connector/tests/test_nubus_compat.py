import uuid
from collections.abc import AsyncGenerator
from typing import Any

import pytest
import pytest_asyncio
from kelvin_connector.nubus_compat import ObjectType, SQLAlchemyDNIDMapper
from sqlalchemy import event
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool
from ucsschool_objects.database_models import Base, Group, GroupType, School, User


@pytest_asyncio.fixture(scope="session")
async def db_engine() -> AsyncGenerator[AsyncEngine, None]:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", poolclass=StaticPool)

    @event.listens_for(engine.sync_engine, "connect")
    def set_sqlite_pragma(dbapi_connection: Any, _connection_record: Any) -> None:
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield engine
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
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
async def school(db_session: AsyncSession) -> School:
    s = School(
        public_id=uuid.uuid4(),
        name="testschool",
        record_uid="r1",
        source_uid="s1",
    )
    db_session.add(s)
    await db_session.flush()
    return s


@pytest_asyncio.fixture
async def user(db_session: AsyncSession) -> User:
    u = User(
        public_id=uuid.uuid4(),
        name="testuser",
        firstname="Test",
        lastname="User",
        record_uid="r2",
        source_uid="s2",
    )
    db_session.add(u)
    await db_session.flush()
    return u


@pytest_asyncio.fixture
async def group(db_session: AsyncSession, school: School) -> Group:
    gt = GroupType(name="class", display_name={"de": "Klasse", "en": "Class"})
    db_session.add(gt)
    await db_session.flush()
    g = Group(
        public_id=uuid.uuid4(),
        name="testgroup",
        record_uid="r3",
        source_uid="s3",
        school=school,
        group_type=gt,
    )
    db_session.add(g)
    await db_session.flush()
    return g


@pytest.mark.asyncio
async def test_set_mapping_creates_new(db_session: AsyncSession, school: School) -> None:
    dn = "cn=testschool,dc=example,dc=com"
    mapper = SQLAlchemyDNIDMapper(db_session)
    await mapper.set_mapping(ObjectType.SCHOOL, dn, school.public_id)
    result = await mapper.dns_to_public_ids(ObjectType.SCHOOL, [dn])
    assert result == {dn: school.public_id}


@pytest.mark.asyncio
async def test_set_mapping_updates_existing(db_session: AsyncSession, school: School) -> None:
    dn = "cn=testschool,dc=example,dc=com"
    other_id = uuid.uuid4()
    s2 = School(public_id=other_id, name="other", record_uid="r9", source_uid="s9")
    db_session.add(s2)
    await db_session.flush()

    mapper = SQLAlchemyDNIDMapper(db_session)
    await mapper.set_mapping(ObjectType.SCHOOL, dn, school.public_id)
    await mapper.set_mapping(ObjectType.SCHOOL, dn, other_id)

    result = await mapper.dns_to_public_ids(ObjectType.SCHOOL, [dn])
    assert result == {dn: other_id}


@pytest.mark.asyncio
async def test_set_mapping_deletes_existing(db_session: AsyncSession, school: School) -> None:
    dn = "cn=testschool,dc=example,dc=com"
    mapper = SQLAlchemyDNIDMapper(db_session)
    await mapper.set_mapping(ObjectType.SCHOOL, dn, school.public_id)
    await mapper.set_mapping(ObjectType.SCHOOL, dn, None)
    result = await mapper.dns_to_public_ids(ObjectType.SCHOOL, [dn])
    assert result == {}


@pytest.mark.asyncio
async def test_set_mapping_delete_nonexistent_is_noop(db_session: AsyncSession) -> None:
    mapper = SQLAlchemyDNIDMapper(db_session)
    await mapper.set_mapping(ObjectType.SCHOOL, "cn=missing,dc=example,dc=com", None)


@pytest.mark.asyncio
async def test_dns_to_public_ids_missing_dn_excluded(db_session: AsyncSession, school: School) -> None:
    dn = "cn=testschool,dc=example,dc=com"
    mapper = SQLAlchemyDNIDMapper(db_session)
    await mapper.set_mapping(ObjectType.SCHOOL, dn, school.public_id)
    result = await mapper.dns_to_public_ids(ObjectType.SCHOOL, [dn, "cn=unknown,dc=example,dc=com"])
    assert result == {dn: school.public_id}


@pytest.mark.asyncio
async def test_public_ids_to_dns(db_session: AsyncSession, school: School) -> None:
    dn = "cn=testschool,dc=example,dc=com"
    mapper = SQLAlchemyDNIDMapper(db_session)
    await mapper.set_mapping(ObjectType.SCHOOL, dn, school.public_id)
    result = await mapper.public_ids_to_dns(ObjectType.SCHOOL, [school.public_id])
    assert result == {school.public_id: dn}


@pytest.mark.asyncio
async def test_public_ids_to_dns_missing_excluded(db_session: AsyncSession, school: School) -> None:
    dn = "cn=testschool,dc=example,dc=com"
    mapper = SQLAlchemyDNIDMapper(db_session)
    await mapper.set_mapping(ObjectType.SCHOOL, dn, school.public_id)
    result = await mapper.public_ids_to_dns(ObjectType.SCHOOL, [school.public_id, uuid.uuid4()])
    assert result == {school.public_id: dn}


@pytest.mark.asyncio
async def test_user_mapping(db_session: AsyncSession, user: User) -> None:
    dn = "uid=testuser,cn=users,dc=example,dc=com"
    mapper = SQLAlchemyDNIDMapper(db_session)
    await mapper.set_mapping(ObjectType.USER, dn, user.public_id)
    assert await mapper.dns_to_public_ids(ObjectType.USER, [dn]) == {dn: user.public_id}
    assert await mapper.public_ids_to_dns(ObjectType.USER, [user.public_id]) == {user.public_id: dn}


@pytest.mark.asyncio
async def test_group_mapping(db_session: AsyncSession, group: Group) -> None:
    dn = "cn=testgroup,cn=groups,dc=example,dc=com"
    mapper = SQLAlchemyDNIDMapper(db_session)
    await mapper.set_mapping(ObjectType.GROUP, dn, group.public_id)
    assert await mapper.dns_to_public_ids(ObjectType.GROUP, [dn]) == {dn: group.public_id}
    assert await mapper.public_ids_to_dns(ObjectType.GROUP, [group.public_id]) == {group.public_id: dn}
