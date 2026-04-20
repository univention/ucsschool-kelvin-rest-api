from __future__ import annotations

from typing import TYPE_CHECKING

import pytest
from ucsschool_objects.core.adapters.sqlalchemy import SQLAlchemyUserReader
from ucsschool_objects.core.domain import Filter, LoadSpec, Operator, SearchQuery

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession
    from tests.test_types import (
        AsyncSchoolFactory as SchoolFactory,
        AsyncSchoolMembershipFactory as SchoolMembershipFactory,
        AsyncUserFactory as UserFactory,
    )


@pytest.mark.asyncio
async def test_primary_school_raises_when_no_primary(
    db_session: AsyncSession,
    school_factory: SchoolFactory,
    user_factory: UserFactory,
    school_membership_factory: SchoolMembershipFactory,
) -> None:
    school = await school_factory(name="non_primary_school")
    user = await user_factory(name="noprimaryuser")
    await school_membership_factory(user=user, school=school, is_primary=False)

    reader = SQLAlchemyUserReader(db_session)
    results = list(
        await reader.search(
            SearchQuery(where=Filter(field="name", op=Operator.EQ, value="noprimaryuser")),
            load=LoadSpec.from_attributes("primary_school"),
        )
    )
    assert len(results) == 1
    with pytest.raises(ValueError, match="no primary school"):
        _ = results[0].primary_school
