# SPDX-FileCopyrightText: 2026 Univention GmbH
# SPDX-License-Identifier: AGPL-3.0-only

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError, InvalidRequestError
from ucsschool_objects.database_models import (
    GroupGroupEmailSendersAssociation,
    GroupMemberAssociation,
    GroupRoleAssociation,
    GroupUserEmailSendersAssociation,
    LegalGuardianAssociation,
    SchoolMembership,
    SchoolMembershipRoleAssociation,
)

if TYPE_CHECKING:
    from collections.abc import Sequence
    from typing import Any

    from sqlalchemy.orm import Session
    from tests.test_types import ModelFactory


@pytest.mark.parametrize(
    "model_factory,fk_name",
    [
        ("group_factory", "group_type_id"),
        ("group_factory", "school_id"),
        ("school_membership_factory", "user_id"),
        ("school_membership_factory", "school_id"),
    ],
    indirect=["model_factory"],
)
def test_foreign_key_not_nullable(
    db_session: Session, model_factory: ModelFactory, fk_name: str
) -> None:
    instance = model_factory()
    setattr(instance, fk_name, None)
    db_session.add(instance)
    with pytest.raises(IntegrityError, match="NOT NULL constraint failed"):
        db_session.flush()


@pytest.mark.parametrize(
    "model_factory,fk_name",
    [
        ("school_membership_factory", "primary_user_constraint"),
    ],
    indirect=["model_factory"],
)
def test_foreign_key_nullable(db_session: Session, model_factory: ModelFactory, fk_name: str) -> None:
    instance = model_factory()
    setattr(instance, fk_name, None)
    db_session.add(instance)
    db_session.flush()
    db_session.refresh(instance)
    assert getattr(instance, fk_name) is None


@pytest.mark.parametrize(
    "model_factory,relation_name",
    [
        ("group_factory", "group_type"),
        ("group_factory", "school"),
    ],
    indirect=["model_factory"],
)
def test_foreign_key_prevents_deletion(
    db_session: Session, model_factory: ModelFactory, relation_name: str
) -> None:
    instance = model_factory()
    db_session.delete(getattr(instance, relation_name))
    with pytest.raises(IntegrityError, match="FOREIGN KEY constraint failed"):
        db_session.flush()


@pytest.mark.parametrize(
    "model_factory,model_factory2,relation_name",
    [
        ("school_membership_factory", "group_factory", "members"),
        ("group_factory", "school_membership_factory", "groups"),
        ("user_factory", "group_factory", "allowed_email_senders_users"),
        ("group_factory", "group_factory", "allowed_email_senders_groups"),
        ("user_factory", "user_factory", "legal_wards"),
        ("user_factory", "user_factory", "legal_guardians"),
        ("school_membership_factory", "user_factory", "school_memberships"),
        ("role_factory", "school_membership_factory", "roles"),
        ("role_factory", "group_factory", "member_roles"),
    ],
    indirect=["model_factory", "model_factory2"],
)
def test_many_to_many_fk_delete_cascade(
    db_session: Session,
    model_factory: ModelFactory,
    model_factory2: ModelFactory,
    relation_name: str,
) -> None:
    instance1 = model_factory()
    instance2 = model_factory2(**{relation_name: [instance1]})
    db_session.delete(instance1)
    db_session.flush()
    db_session.refresh(instance2, [relation_name])
    assert getattr(instance2, relation_name) == []


@pytest.mark.parametrize(
    "model_factory,model_factory2,relation_name,association_cls",
    [
        ("school_membership_factory", "group_factory", "members", GroupMemberAssociation),
        ("group_factory", "school_membership_factory", "groups", GroupMemberAssociation),
        (
            "user_factory",
            "group_factory",
            "allowed_email_senders_users",
            GroupUserEmailSendersAssociation,
        ),
        (
            "group_factory",
            "group_factory",
            "allowed_email_senders_groups",
            GroupGroupEmailSendersAssociation,
        ),
        ("user_factory", "user_factory", "legal_wards", LegalGuardianAssociation),
        ("user_factory", "user_factory", "legal_guardians", LegalGuardianAssociation),
        ("school_membership_factory", "user_factory", "school_memberships", SchoolMembership),
        ("role_factory", "school_membership_factory", "roles", SchoolMembershipRoleAssociation),
        ("role_factory", "group_factory", "member_roles", GroupRoleAssociation),
    ],
    indirect=["model_factory", "model_factory2"],
)
def test_many_to_many_orm_delete_cascade(
    db_session: Session,
    model_factory: ModelFactory,
    model_factory2: ModelFactory,
    relation_name: str,
    association_cls: type,
) -> None:
    instance1 = model_factory()
    model_factory2(**{relation_name: [instance1]})
    associations: Sequence[Any] = db_session.execute(select(association_cls)).all()
    assert len(associations) == 1
    db_session.delete(instance1)
    db_session.flush()
    associations = db_session.execute(select(association_cls)).all()
    assert len(associations) == 0


@pytest.mark.parametrize(
    "model_factory,relation_name",
    [
        ("group_factory", "group_type"),
        ("group_factory", "school"),
        ("school_membership_factory", "user"),
        ("school_membership_factory", "school"),
    ],
    indirect=["model_factory"],
)
def test_relation_is_eager_loaded(
    db_session: Session, model_factory: ModelFactory, relation_name: str
) -> None:
    instance = model_factory()
    model_cls = type(instance)
    instance_id = instance.id
    db_session.expunge(instance)
    loaded_instance = db_session.query(model_cls).get(instance_id)
    assert loaded_instance is not None
    getattr(loaded_instance, relation_name)


@pytest.mark.parametrize(
    "model_factory,relation_name",
    [
        ("group_factory", "members"),
        ("group_factory", "allowed_email_senders_users"),
        ("group_factory", "allowed_email_senders_groups"),
        ("group_factory", "member_roles"),
        ("school_membership_factory", "groups"),
        ("user_factory", "legal_wards"),
        ("user_factory", "legal_guardians"),
        ("user_factory", "school_memberships"),
        ("school_membership_factory", "roles"),
    ],
    indirect=["model_factory"],
)
def test_relation_no_indirect_loading(
    db_session: Session, model_factory: ModelFactory, relation_name: str
) -> None:
    instance = model_factory()
    model_cls = type(instance)
    instance_id = instance.id
    db_session.expunge(instance)
    loaded_instance = db_session.query(model_cls).get(instance_id)
    assert loaded_instance is not None
    with pytest.raises(InvalidRequestError, match="is not available due to lazy='raise'"):
        getattr(loaded_instance, relation_name)


@pytest.mark.parametrize(
    "model_factory,relation_name,model_factory2,relation_name2",
    [
        ("group_factory", "members", "school_membership_factory", "groups"),
        ("school_membership_factory", "groups", "group_factory", "members"),
        ("user_factory", "legal_wards", "user_factory", "legal_guardians"),
        ("user_factory", "legal_guardians", "user_factory", "legal_wards"),
    ],
    indirect=["model_factory", "model_factory2"],
)
def test_many_to_many_relation_back_population(
    db_session: Session,
    model_factory: ModelFactory,
    relation_name: str,
    model_factory2: ModelFactory,
    relation_name2: str,
) -> None:
    instance = model_factory()
    db_session.refresh(instance, attribute_names=[relation_name])
    instance2 = model_factory2(**{relation_name2: [instance]})
    assert getattr(instance, relation_name) == [instance2]
