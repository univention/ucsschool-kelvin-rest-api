from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession
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
    session: AsyncSession,
) -> tuple[PostgresSchoolReader, PostgresUserReader, PostgresGroupReader]:
    return PostgresSchoolReader(session), PostgresUserReader(session), PostgresGroupReader(session)


def sqlite_readers(
    session: AsyncSession,
) -> tuple[SqliteMemorySchoolReader, SqliteMemoryUserReader, SqliteMemoryGroupReader]:
    return (
        SqliteMemorySchoolReader(session),
        SqliteMemoryUserReader(session),
        SqliteMemoryGroupReader(session),
    )
