from __future__ import annotations

from typing import TYPE_CHECKING

import pytest
from sqlalchemy.exc import IntegrityError

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession
    from tests.test_types import AsyncSchoolFactory, AsyncSchoolMembershipFactory, AsyncUserFactory


async def test_one_primary_school_only(
    db_session: AsyncSession,
    user_factory: AsyncUserFactory,
    school_factory: AsyncSchoolFactory,
    school_membership_factory: AsyncSchoolMembershipFactory,
) -> None:
    user = await user_factory()
    school = await school_factory()
    school2 = await school_factory()
    await db_session.refresh(user, attribute_names=["school_memberships"])
    user.school_memberships = [
        await school_membership_factory(persisted=False, school=school, user=user, is_primary=True),
        await school_membership_factory(persisted=False, school=school2, user=user, is_primary=True),
    ]
    db_session.add(user)
    with pytest.raises(IntegrityError, match="UNIQUE constraint failed"):
        await db_session.flush()


async def test_user_school_id_unique(
    db_session: AsyncSession, school_membership_factory: AsyncSchoolMembershipFactory
) -> None:
    school_membership = await school_membership_factory()
    with pytest.raises(IntegrityError, match="UNIQUE constraint failed"):
        await school_membership_factory(user=school_membership.user, school=school_membership.school)
