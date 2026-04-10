from __future__ import annotations

from collections.abc import Callable

from sqlalchemy.orm import Session
from ucsschool_objects.database_models import Group, SchoolMembership


def seed_school_user_group_graph(
    session: Session,
    *,
    school_factory: Callable[..., object],
    user_factory: Callable[..., object],
    group_factory: Callable[..., Group],
    school_membership_factory: Callable[..., SchoolMembership],
) -> tuple[object, object, Group]:
    school = school_factory(name="alpha")
    user = user_factory(name="anna", firstname="Anna", lastname="A")
    membership = school_membership_factory(user=user, school=school, is_primary=True)
    group = group_factory(name="alpha-team", school=school)
    membership.groups.append(group)
    session.flush()
    return school, user, group
