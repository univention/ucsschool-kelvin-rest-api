from __future__ import annotations

import os
import random
import uuid
from collections.abc import Iterator
from typing import Any, Callable, cast

import pytest
from sqlalchemy import Engine, create_engine, event
from sqlalchemy.orm import Session, sessionmaker
from ucsschool_objects.database_models import Base, Group, GroupType, School, SchoolMembership, User

POSTGRES_TEST_URL_ENV = "CORELIB_POSTGRES_TEST_URL"


@pytest.fixture(scope="session")
def db_engine() -> Iterator[Engine]:
    engine = create_engine("sqlite://")

    @event.listens_for(engine, "connect")
    def _set_sqlite_pragma(dbapi_connection: Any, _connection_record: Any) -> None:
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    Base.metadata.create_all(engine)
    yield engine
    Base.metadata.drop_all(engine)
    engine.dispose()


@pytest.fixture(scope="session")
def postgres_db_engine() -> Iterator[Engine]:
    database_url = os.getenv(POSTGRES_TEST_URL_ENV)
    if not database_url:
        pytest.skip(f"Set {POSTGRES_TEST_URL_ENV} to run PostgreSQL corelib tests.")

    engine = create_engine(database_url)
    Base.metadata.create_all(engine)
    yield engine
    Base.metadata.drop_all(engine)
    engine.dispose()


@pytest.fixture
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
def postgres_db_session(postgres_db_engine: Engine) -> Iterator[Session]:
    connection = postgres_db_engine.connect()
    transaction = connection.begin()
    session = sessionmaker(bind=connection)()
    session.begin_nested()
    yield session
    session.close()
    transaction.rollback()
    connection.close()


@pytest.fixture
def school_factory(db_session: Session) -> Callable[..., School]:
    def _factory(**overrides: object) -> School:
        target_session = cast(Session, overrides.pop("db_session", db_session))
        school = School(
            public_id=overrides.get("public_id", uuid.uuid4()),
            record_uid=overrides.get("record_uid", f"school-record-{uuid.uuid4()}"),
            source_uid=overrides.get("source_uid", "source-a"),
            name=overrides.get("name", f"school-{uuid.uuid4()}"),
            display_name=overrides.get("display_name", {"de": "Schule", "en": "School"}),
            educational_servers=overrides.get("educational_servers", ["edu1.example"]),
            administrative_servers=overrides.get("administrative_servers", ["adm1.example"]),
            class_share_file_server=overrides.get("class_share_file_server", "class.example"),
            home_share_file_server=overrides.get("home_share_file_server", "home.example"),
        )
        target_session.add(school)
        target_session.flush()
        return school

    return _factory


@pytest.fixture
def group_factory(db_session: Session, school_factory: Callable[..., School]) -> Callable[..., Group]:
    def _factory(**overrides: object) -> Group:
        target_session = cast(Session, overrides.pop("db_session", db_session))
        group_type = GroupType(
            name=overrides.get("group_type_name", f"type-{uuid.uuid4()}"),
            display_name={"de": "Typ", "en": "Type"},
        )
        school = overrides.get("school") or school_factory(db_session=target_session)
        group = Group(
            public_id=overrides.get("public_id", uuid.uuid4()),
            record_uid=overrides.get("record_uid", f"group-record-{uuid.uuid4()}"),
            source_uid=overrides.get("source_uid", "source-a"),
            name=overrides.get("name", f"group-{uuid.uuid4()}"),
            display_name=overrides.get("display_name", {"de": "Gruppe", "en": "Group"}),
            has_share=bool(overrides.get("has_share", random.choice([True, False]))),  # nosec
            email=overrides.get("email", f"group-{uuid.uuid4()}@example.com"),
            group_type=group_type,
            school=school,
        )
        target_session.add(group)
        target_session.flush()
        return group

    return _factory


@pytest.fixture
def user_factory(db_session: Session) -> Callable[..., User]:
    def _factory(**overrides: object) -> User:
        target_session = cast(Session, overrides.pop("db_session", db_session))
        user = User(
            public_id=overrides.get("public_id", uuid.uuid4()),
            record_uid=overrides.get("record_uid", f"user-record-{uuid.uuid4()}"),
            source_uid=overrides.get("source_uid", "source-a"),
            name=overrides.get("name", f"user-{uuid.uuid4()}"),
            firstname=overrides.get("firstname", "Test"),
            lastname=overrides.get("lastname", "User"),
            email=overrides.get("email", f"user-{uuid.uuid4()}@example.com"),
            birthday=overrides.get("birthday", None),
            expiration_date=overrides.get("expiration_date", None),
            active=bool(overrides.get("active", True)),
        )
        target_session.add(user)
        target_session.flush()
        return user

    return _factory


@pytest.fixture
def membership_factory(
    db_session: Session,
    school_factory: Callable[..., School],
    user_factory: Callable[..., User],
) -> Callable[..., SchoolMembership]:
    def _factory(**overrides: object) -> SchoolMembership:
        target_session = cast(Session, overrides.pop("db_session", db_session))
        membership = SchoolMembership(
            user=overrides.get("user") or user_factory(db_session=target_session),
            school=overrides.get("school") or school_factory(db_session=target_session),
            is_primary=bool(overrides.get("is_primary", False)),
        )
        target_session.add(membership)
        target_session.flush()
        return membership

    return _factory
