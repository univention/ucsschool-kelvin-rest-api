import random
import uuid

import pytest
from sqlalchemy import Engine, create_engine, event
from sqlalchemy.orm import sessionmaker
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
def unset_sentinel():
    return object()


@pytest.fixture(scope="session")
def db_engine():
    engine = create_engine("sqlite://")

    @event.listens_for(engine, "connect")
    def set_sqlite_pragma(dbapi_connection, connection_record):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    Base.metadata.create_all(engine)
    yield engine
    Base.metadata.drop_all(engine)
    engine.dispose()


@pytest.fixture(scope="function")
def db_session(db_engine: Engine):
    connection = db_engine.connect()
    transaction = connection.begin()
    session = sessionmaker(bind=connection)()
    session.begin_nested()
    yield session
    session.close()
    transaction.rollback()
    connection.close()


@pytest.fixture
def model_factory(request):
    """Generic fixture that resolves to a specific factory based on param."""
    return request.getfixturevalue(request.param)


@pytest.fixture
def model_factory2(request):
    """There are tests, which need to combine two different model factories."""
    return request.getfixturevalue(request.param)


@pytest.fixture
def school_data_factory(faker):
    def _school_data_factory():
        return {
            "public_id": uuid.uuid4(),
            "record_uid": faker.unique.ssn(),
            "source_uid": faker.unique.ssn(),
            "name": faker.unique.company(),
            "display_name": {"de": faker.name(), "en": faker.name()},
            "educational_servers": [faker.domain_name() for i in range(5)],
            "administrative_servers": [faker.domain_name() for i in range(5)],
            "class_share_file_server": faker.domain_name(),
            "home_share_file_server": faker.domain_name(),
        }

    return _school_data_factory


@pytest.fixture
def school_factory(db_session, school_data_factory, unset_sentinel):
    def _school_factory(persisted=True, **overrides):
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
def group_data_factory(faker):
    def _group_data_factory():
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
def group_factory(db_session, group_data_factory, group_type_factory, school_factory, unset_sentinel):
    def _group_factory(persisted=True, **overrides):
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
def user_data_factory(faker):
    def _user_data_factory():
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
def user_factory(db_session, user_data_factory, unset_sentinel):
    def _user_factory(persisted=True, **overrides):
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
def role_data_factory(faker):
    def _role_data_factory():
        return {
            "public_id": uuid.uuid4(),
            "name": faker.unique.name(),
            "display_name": {"de": faker.name(), "en": faker.name()},
        }

    return _role_data_factory


@pytest.fixture
def role_factory(db_session, role_data_factory, unset_sentinel):
    def _role_factory(persisted=True, **overrides):
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
def group_type_data_factory(faker):
    def _group_type_data_factory():
        return {
            "name": faker.unique.name(),
            "display_name": {"de": faker.name(), "en": faker.name()},
        }

    return _group_type_data_factory


@pytest.fixture
def group_type_factory(db_session, group_type_data_factory, unset_sentinel):
    def _group_type_factory(persisted=True, **overrides):
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
def school_membership_factory(db_session, school_factory, user_factory, unset_sentinel):
    def _school_membership_factory(persisted=True, **overrides):
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
