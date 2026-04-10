from typing import TYPE_CHECKING
from uuid import UUID

import pytest
from ucsschool_objects.core.adapters.sqlite_memory.readers import SqliteMemorySchoolReader
from ucsschool_objects.core.domain import SortSpec

if TYPE_CHECKING:
    from sqlalchemy.orm import Session
    from tests.test_types import SchoolFactory


@pytest.mark.asyncio
async def test_deterministic_sort_and_pagination(
    db_session: Session, school_factory: SchoolFactory
) -> None:
    school_factory(name="s2")
    school_factory(name="s1")
    school_factory(name="s3")
    reader = SqliteMemorySchoolReader(db_session)

    ordered = await reader.search(sort_by=(SortSpec(field="name", ascending=True),), limit=10, offset=0)
    assert [item.name for item in ordered] == ["s1", "s2", "s3"]

    page = await reader.search(sort_by=(SortSpec(field="name", ascending=True),), limit=2, offset=1)
    assert [item.name for item in page] == ["s2", "s3"]


@pytest.mark.asyncio
async def test_deterministic_sort_and_pagination_with_duplicate_sort_keys(
    db_session: Session, school_factory: SchoolFactory
) -> None:
    first = school_factory(
        name="s1",
        class_share_file_server="same-server",
        public_id=UUID("00000000-0000-0000-0000-00000000000a"),
    )
    second = school_factory(
        name="s2",
        class_share_file_server="same-server",
        public_id=UUID("00000000-0000-0000-0000-00000000000b"),
    )
    school_factory(name="s3", class_share_file_server="zzz-server")
    reader = SqliteMemorySchoolReader(db_session)
    duplicate_public_ids = [str(first.public_id), str(second.public_id)]

    ordered = await reader.search(
        sort_by=(SortSpec(field="class_share_file_server", ascending=True),), limit=10, offset=0
    )
    assert [str(item.public_id) for item in ordered[:2]] == duplicate_public_ids

    page = await reader.search(
        sort_by=(SortSpec(field="class_share_file_server", ascending=True),), limit=1, offset=1
    )
    assert str(page[0].public_id) == duplicate_public_ids[1]
