import pytest
from sqlalchemy.exc import IntegrityError


def test_one_primary_school_only(db_session, user_factory, school_factory, school_membership_factory):
    user = user_factory()
    school = school_factory()
    school2 = school_factory()
    db_session.refresh(user, attribute_names=["school_memberships"])
    user.school_memberships = [
        school_membership_factory(persisted=False, school=school, user=user, is_primary=True),
        school_membership_factory(persisted=False, school=school2, user=user, is_primary=True),
    ]
    db_session.add(user)
    with pytest.raises(IntegrityError, match="UNIQUE constraint failed"):
        db_session.flush()


def test_user_school_id_unique(db_session, school_membership_factory):
    school_membership = school_membership_factory()
    with pytest.raises(IntegrityError, match="UNIQUE constraint failed"):
        school_membership_factory(user=school_membership.user, school=school_membership.school)
