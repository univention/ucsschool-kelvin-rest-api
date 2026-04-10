from __future__ import annotations

import os
from collections.abc import Iterator

import pytest
from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import Session, sessionmaker
from ucsschool_objects.database_models import Base

POSTGRES_TEST_URL_ENV = "CORELIB_POSTGRES_TEST_URL"


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
def postgres_db_session(postgres_db_engine: Engine) -> Iterator[Session]:
    connection = postgres_db_engine.connect()
    transaction = connection.begin()
    session = sessionmaker(bind=connection)()
    session.begin_nested()
    yield session
    session.close()
    transaction.rollback()
    connection.close()
