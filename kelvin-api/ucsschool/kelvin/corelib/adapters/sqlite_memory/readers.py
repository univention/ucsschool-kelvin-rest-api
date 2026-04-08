from __future__ import annotations

from sqlalchemy.orm import Session

from ucsschool.kelvin.corelib.adapters.postgres.readers import (
    PostgresGroupReader,
    PostgresSchoolReader,
    PostgresUserReader,
)


class SqliteMemorySchoolReader(PostgresSchoolReader):
    def __init__(self, session: Session):
        super().__init__(session)


class SqliteMemoryGroupReader(PostgresGroupReader):
    def __init__(self, session: Session):
        super().__init__(session)


class SqliteMemoryUserReader(PostgresUserReader):
    def __init__(self, session: Session):
        super().__init__(session)
