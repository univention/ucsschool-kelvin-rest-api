# SPDX-FileCopyrightText: 2026 Univention GmbH
# SPDX-License-Identifier: AGPL-3.0-only

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING

import pytest
from sqlalchemy import null, update
from sqlalchemy.exc import IntegrityError

if TYPE_CHECKING:
    from sqlalchemy.orm import Session
    from tests.test_types import ModelFactory, RecordSourceFactory, SchoolFactory


@pytest.mark.parametrize(
    "model_factory,attribute_name",
    [
        ("school_factory", "public_id"),
        ("school_factory", "name"),
        ("school_factory", "display_name"),
        ("school_factory", "educational_servers"),
        ("school_factory", "administrative_servers"),
        ("school_factory", "record_uid"),
        ("school_factory", "source_uid"),
        ("group_factory", "public_id"),
        ("group_factory", "name"),
        ("group_factory", "display_name"),
        ("group_factory", "has_share"),
        ("group_factory", "record_uid"),
        ("group_factory", "source_uid"),
        ("user_factory", "public_id"),
        ("user_factory", "name"),
        ("user_factory", "firstname"),
        ("user_factory", "lastname"),
        ("user_factory", "record_uid"),
        ("user_factory", "source_uid"),
        ("user_factory", "active"),
        ("role_factory", "public_id"),
        ("role_factory", "name"),
        ("role_factory", "display_name"),
        ("group_type_factory", "name"),
        ("group_type_factory", "display_name"),
        ("school_membership_factory", "is_primary"),
    ],
    indirect=["model_factory"],
)
def test_not_nullable_scalar_raises_error(
    db_session: Session, model_factory: ModelFactory, attribute_name: str
) -> None:
    instance = model_factory()
    model_cls = type(instance)
    stmt = update(model_cls).where(model_cls.id == instance.id).values(**{attribute_name: null()})
    with pytest.raises(IntegrityError, match="NOT NULL constraint failed"):
        db_session.execute(stmt)


@pytest.mark.parametrize(
    "model_factory,attribute_name",
    [
        ("school_factory", "class_share_file_server"),
        ("school_factory", "home_share_file_server"),
        ("group_factory", "email"),
        ("user_factory", "email"),
        ("user_factory", "birthday"),
        ("user_factory", "expiration_date"),
        ("school_membership_factory", "primary_user_constraint"),
    ],
    indirect=["model_factory"],
)
def test_nullable_scalar_set_to_null(
    db_session: Session, model_factory: ModelFactory, attribute_name: str
) -> None:
    instance = model_factory()
    model_cls = type(instance)
    stmt = update(model_cls).where(model_cls.id == instance.id).values(**{attribute_name: null()})
    db_session.execute(stmt)
    db_session.flush()
    db_session.refresh(instance)
    assert getattr(instance, attribute_name) is None


@pytest.mark.parametrize(
    "model_factory,attribute_name",
    [
        ("school_factory", "id"),
        ("school_factory", "public_id"),
        ("school_factory", "name"),
        ("group_factory", "id"),
        ("group_factory", "public_id"),
        ("group_factory", "name"),
        ("group_factory", "email"),
        ("user_factory", "id"),
        ("user_factory", "public_id"),
        ("user_factory", "name"),
        ("user_factory", "email"),
        ("role_factory", "id"),
        ("role_factory", "public_id"),
        ("role_factory", "name"),
        ("group_type_factory", "id"),
        ("group_type_factory", "name"),
        ("school_membership_factory", "id"),
    ],
    indirect=["model_factory"],
)
def test_unique_scalar_raise_error(
    db_session: Session, model_factory: ModelFactory, attribute_name: str
) -> None:
    instance = model_factory()
    with pytest.raises(IntegrityError, match="UNIQUE constraint failed"):
        model_factory(**{attribute_name: getattr(instance, attribute_name)})


@pytest.mark.parametrize(
    "model_factory,attribute_name",
    [
        ("school_factory", "display_name"),
        ("school_factory", "educational_servers"),
        ("school_factory", "administrative_servers"),
        ("school_factory", "class_share_file_server"),
        ("school_factory", "home_share_file_server"),
        ("school_factory", "record_uid"),
        ("school_factory", "source_uid"),
        ("group_factory", "display_name"),
        ("group_factory", "has_share"),
        ("group_factory", "record_uid"),
        ("group_factory", "source_uid"),
        ("user_factory", "firstname"),
        ("user_factory", "lastname"),
        ("user_factory", "record_uid"),
        ("user_factory", "source_uid"),
        ("user_factory", "birthday"),
        ("user_factory", "expiration_date"),
        ("user_factory", "active"),
        ("role_factory", "display_name"),
        ("group_type_factory", "display_name"),
    ],
    indirect=["model_factory"],
)
def test_non_unique_scalar_set_to_duplicate(
    db_session: Session, model_factory: ModelFactory, attribute_name: str
) -> None:
    instance = model_factory()
    instance2 = model_factory(**{attribute_name: getattr(instance, attribute_name)})
    assert getattr(instance, attribute_name) == getattr(instance2, attribute_name)


@pytest.mark.parametrize(
    "model_factory,attribute_name,expected_value",
    [
        ("school_factory", "id", int),
        ("school_factory", "public_id", uuid.UUID),
        ("school_factory", "display_name", {}),
        ("school_factory", "administrative_servers", []),
        ("group_factory", "id", int),
        ("group_factory", "public_id", uuid.UUID),
        ("group_factory", "display_name", {}),
        ("group_factory", "has_share", False),
        ("user_factory", "id", int),
        ("user_factory", "public_id", uuid.UUID),
        ("user_factory", "active", True),
        ("role_factory", "id", int),
        ("role_factory", "public_id", uuid.UUID),
        ("role_factory", "display_name", {}),
        ("group_type_factory", "id", int),
        ("group_type_factory", "display_name", {}),
        ("school_membership_factory", "is_primary", False),
    ],
    indirect=["model_factory"],
)
def test_scalar_default_value(
    db_session: Session,
    model_factory: ModelFactory,
    unset_sentinel: object,
    attribute_name: str,
    expected_value: object,
) -> None:
    instance = model_factory(**{attribute_name: unset_sentinel})
    db_session.refresh(instance)
    if isinstance(expected_value, type):
        assert isinstance(getattr(instance, attribute_name), expected_value)
    else:
        assert getattr(instance, attribute_name) == expected_value


@pytest.mark.parametrize(
    "model_factory",
    ["school_factory", "group_factory", "user_factory"],
    indirect=["model_factory"],
)
def test_record_source_uid_unique_constraint(
    db_session: Session, model_factory: RecordSourceFactory
) -> None:
    instance = model_factory()
    with pytest.raises(IntegrityError, match="UNIQUE constraint failed"):
        model_factory(**{"source_uid": instance.source_uid, "record_uid": instance.record_uid})


@pytest.mark.parametrize("value", [None, []])
def test_school_educational_servers_not_empty(
    school_factory: SchoolFactory, value: list[str] | None
) -> None:
    with pytest.raises(ValueError, match="The attribute educational_servers must not be None or empty."):
        school_factory(educational_servers=value)
