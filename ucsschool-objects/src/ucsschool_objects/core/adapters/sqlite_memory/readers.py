from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession
from ucsschool_objects.core.adapters.postgres.readers import (
    PostgresGroupReader,
    PostgresSchoolReader,
    PostgresUserReader,
)


class SqliteMemorySchoolReader(PostgresSchoolReader):
    def __init__(self, session: AsyncSession):
        super().__init__(session)


class SqliteMemoryGroupReader(PostgresGroupReader):
    def __init__(self, session: AsyncSession):
        super().__init__(session)


class SqliteMemoryUserReader(PostgresUserReader):
    def __init__(self, session: AsyncSession):
        super().__init__(session)
