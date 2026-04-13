# SPDX-FileCopyrightText: 2026 Univention GmbH
# SPDX-License-Identifier: AGPL-3.0-only

from __future__ import annotations

import random
import uuid
from collections.abc import Iterator
from typing import Any, cast

import pytest
from pytest import FixtureRequest
from sqlalchemy import Engine, create_engine, event
from sqlalchemy.orm import Session, sessionmaker
from tests.test_types import (
    GroupDataFactory,
    GroupFactory,
    GroupTypeDataFactory,
    GroupTypeFactory,
    ModelFactory,
    RoleDataFactory,
    RoleFactory,
    SchoolDataFactory,
    SchoolFactory,
    SchoolMembershipFactory,
    UserDataFactory,
    UserFactory,
)
from ucsschool_objects.database_models import (
    Base,
    Group,
    GroupType,
    Role,
    School,
    SchoolMembership,
    User,
)


@pytest.fixture(scope="session")
def unset_sentinel() -> object:
    return object()


@pytest.fixture(scope="session")
def db_engine() -> Iterator[Engine]:
    engine = create_engine("sqlite://")

    @event.listens_for(engine, "connect")
    def set_sqlite_pragma(dbapi_connection: Any, _connection_record: Any) -> None:
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    Base.metadata.create_all(engine)
    yield engine
    Base.metadata.drop_all(engine)
    engine.dispose()


@pytest.fixture(scope="function")
def db_session(db_engine: Engine) -> Iterator[Session]:
    connection = db_engine.connect()
    transaction = connection.begin()
    session = sessionmaker(bind=connection)()
    session.begin_nested()
    yield session
    session.close()
    transaction.rollback()
    connection.close()


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
    db_session: Session,
    school_data_factory: SchoolDataFactory,
    unset_sentinel: object,
) -> SchoolFactory:
    def _school_factory(persisted: bool = True, **overrides: object) -> School:
        school_data = {**school_data_factory(), **overrides}
        for unset_key in (key for key, value in overrides.items() if value == unset_sentinel):
            del school_data[unset_key]
        school = School(**school_data)
        if persisted:
            db_session.add(school)
            db_session.flush()
        return school

    return _school_factory


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
        }

    return _group_data_factory


@pytest.fixture
def group_factory(
    db_session: Session,
    group_data_factory: GroupDataFactory,
    group_type_factory: GroupTypeFactory,
    school_factory: SchoolFactory,
    unset_sentinel: object,
) -> GroupFactory:
    def _group_factory(persisted: bool = True, **overrides: object) -> Group:
        group_data = {**group_data_factory(), **overrides}
        for unset_key in (key for key, value in overrides.items() if value == unset_sentinel):
            del group_data[unset_key]
        group = Group(**group_data)
        if "group_type" not in overrides:
            group.group_type = group_type_factory(persisted=False)
        if "school" not in overrides:
            group.school = school_factory(persisted=False)
        if persisted:
            db_session.add(group)
            db_session.flush()
        return group

    return _group_factory


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
            "birthday": faker.date_time(),
            "expiration_date": faker.date_time(),
            "active": random.choice([True, False]),  # nosec
        }

    return _user_data_factory


@pytest.fixture
def user_factory(
    db_session: Session,
    user_data_factory: UserDataFactory,
    unset_sentinel: object,
) -> UserFactory:
    def _user_factory(persisted: bool = True, **overrides: object) -> User:
        user_data = {**user_data_factory(), **overrides}
        for unset_key in (key for key, value in overrides.items() if value == unset_sentinel):
            del user_data[unset_key]
        user = User(**user_data)
        if persisted:
            db_session.add(user)
            db_session.flush()
        return user

    return _user_factory


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
    db_session: Session,
    role_data_factory: RoleDataFactory,
    unset_sentinel: object,
) -> RoleFactory:
    def _role_factory(persisted: bool = True, **overrides: object) -> Role:
        role_data = {**role_data_factory(), **overrides}
        for unset_key in (key for key, value in overrides.items() if value == unset_sentinel):
            del role_data[unset_key]
        role = Role(**role_data)
        if persisted:
            db_session.add(role)
            db_session.flush()
        return role

    return _role_factory


@pytest.fixture
def group_type_data_factory(faker: Any) -> GroupTypeDataFactory:
    def _group_type_data_factory() -> dict[str, object]:
        return {
            "name": faker.unique.name(),
            "display_name": {"de": faker.name(), "en": faker.name()},
        }

    return _group_type_data_factory


@pytest.fixture
def group_type_factory(
    db_session: Session,
    group_type_data_factory: GroupTypeDataFactory,
    unset_sentinel: object,
) -> GroupTypeFactory:
    def _group_type_factory(persisted: bool = True, **overrides: object) -> GroupType:
        group_type_data = {**group_type_data_factory(), **overrides}
        for unset_key in (key for key, value in overrides.items() if value == unset_sentinel):
            del group_type_data[unset_key]
        group_type = GroupType(**group_type_data)
        if persisted:
            db_session.add(group_type)
            db_session.flush()
        return group_type

    return _group_type_factory


@pytest.fixture
def school_membership_factory(
    db_session: Session,
    school_factory: SchoolFactory,
    user_factory: UserFactory,
    unset_sentinel: object,
) -> SchoolMembershipFactory:
    def _school_membership_factory(persisted: bool = True, **overrides: object) -> SchoolMembership:
        school_membership_data = {**overrides}
        for unset_key in (key for key, value in overrides.items() if value == unset_sentinel):
            del school_membership_data[unset_key]
        school_membership = SchoolMembership(**school_membership_data)
        if "user" not in overrides:
            school_membership.user = user_factory(persisted=False)
        if "school" not in overrides:
            school_membership.school = school_factory(persisted=False)
        if persisted:
            db_session.add(school_membership)
            db_session.flush()
        return school_membership

    return _school_membership_factory
