import uuid
from contextlib import asynccontextmanager
from unittest.mock import AsyncMock, MagicMock

import pytest
from kelvin_connector.sync import SynchronizationManager
from ucsschool_objects.core.domain.models import Group, Role, School, User


def make_school(name="testschool", uid=None) -> School:
    return School(
        public_id=uid or uuid.uuid4(),
        record_uid=name,
        source_uid="kelvin-connector",
        name=name,
        display_name=f"{name} Display",
        educational_servers={"server1"},
        administrative_servers={"server2"},
    )


def make_user(name="testuser", uid=None, school_memberships=None) -> User:
    return User(
        public_id=uid or uuid.uuid4(),
        record_uid=name,
        source_uid="src",
        name=name,
        firstname="Test",
        lastname="User",
        active=True,
        school_memberships=school_memberships if school_memberships is not None else {},
        legal_wards=set(),
        legal_guardians=set(),
    )


def make_group(name: str, school: School, uid=None) -> Group:
    return Group(
        public_id=uid or uuid.uuid4(),
        record_uid=name,
        source_uid="kelvin-connector",
        name=name,
        display_name=name,
        create_share=False,
        roles=set(),
        allowed_email_senders_users=set(),
        allowed_email_senders_groups=set(),
        members=set(),
        member_roles=set(),
        school=school,
        description=None,
    )


def make_role(name="teacher") -> Role:
    return Role(name=name, display_name=name)


@pytest.fixture
def mock_mapper():
    m = AsyncMock()
    m.dns_to_public_ids.return_value = {}
    m.set_mapping = AsyncMock()
    return m


@pytest.fixture
def mock_storage():
    s = MagicMock()
    s.session = MagicMock()
    s.users.create = AsyncMock()
    s.users.delete = AsyncMock()
    s.users.get = AsyncMock()
    s.users.modify = AsyncMock()
    s.users.search = AsyncMock(return_value=[])
    s.groups.create = AsyncMock()
    s.groups.delete = AsyncMock()
    s.groups.get = AsyncMock()
    s.groups.modify = AsyncMock()
    s.groups.search = AsyncMock(return_value=[])
    s.schools.create = AsyncMock()
    s.schools.delete = AsyncMock()
    s.schools.get = AsyncMock()
    s.schools.modify = AsyncMock()
    s.schools.search = AsyncMock(return_value=[])
    s.roles.search = AsyncMock(return_value=[])
    return s


@pytest.fixture
def storage_factory(mock_storage):
    factory = MagicMock()

    @asynccontextmanager
    async def transaction_scope():
        yield mock_storage

    factory.transaction_scope = transaction_scope
    return factory


@pytest.fixture
def manager(storage_factory, mock_mapper) -> SynchronizationManager:
    return SynchronizationManager(storage_factory, mapper_factory=lambda _: mock_mapper)
