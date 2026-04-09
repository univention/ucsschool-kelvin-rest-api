from __future__ import annotations

from sqlalchemy.orm import Session
from ucsschool_objects.core.adapters.postgres.readers import (
    PostgresGroupReader,
    PostgresSchoolReader,
    PostgresUserReader,
)
from ucsschool_objects.core.adapters.sqlite_memory.readers import (
    SqliteMemoryGroupReader,
    SqliteMemorySchoolReader,
    SqliteMemoryUserReader,
)


def postgres_readers(
    session: Session,
) -> tuple[PostgresSchoolReader, PostgresUserReader, PostgresGroupReader]:
    return PostgresSchoolReader(session), PostgresUserReader(session), PostgresGroupReader(session)


def sqlite_readers(
    session: Session,
) -> tuple[SqliteMemorySchoolReader, SqliteMemoryUserReader, SqliteMemoryGroupReader]:
    return (
        SqliteMemorySchoolReader(session),
        SqliteMemoryUserReader(session),
        SqliteMemoryGroupReader(session),
    )
