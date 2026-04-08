"""
Static-analysis conformance checks — never executed at runtime.

mypy verifies at analysis time that each adapter is assignable to its Protocol.
If an adapter stops satisfying its protocol (removed method, wrong signature, …)
mypy raises an assignment-incompatibility error on the annotated variables below,
failing the ``make typecheck-ucsschool-objects`` step.
"""

from __future__ import annotations

from sqlalchemy.orm import Session
from ucsschool_objects.core.adapters import (
    SqlAlchemyGroupReader,
    SqlAlchemySchoolReader,
    SqlAlchemyUserReader,
)
from ucsschool_objects.core.ports import GroupReader, SchoolReader, UserReader


def assert_reader_protocol_conformance(session: Session) -> None:
    user_reader: UserReader = SqlAlchemyUserReader(session)
    group_reader: GroupReader = SqlAlchemyGroupReader(session)
    school_reader: SchoolReader = SqlAlchemySchoolReader(session)

    _ = user_reader, group_reader, school_reader
