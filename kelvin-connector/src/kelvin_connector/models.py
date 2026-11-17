# SPDX-FileCopyrightText: 2026 Univention GmbH
# SPDX-License-Identifier: AGPL-3.0-only

import logging
from datetime import date
from typing import Annotated, Iterable

from pydantic import UUID1, UUID4, BaseModel, BeforeValidator, ConfigDict, Field, field_validator

logger = logging.getLogger(__name__)

# ── Per-type properties models ────────────────────────────────────────────────

# univention object identifier type
UOID = UUID1 | UUID4


class UcsschoolRole(BaseModel):
    role: str
    context: str
    school: str


class GuardianRole(BaseModel):
    app: str
    namespace: str
    role_name: str


def _parse_ucsschool_role_item(v: str | UcsschoolRole):
    """Split like ucs-school-lib's get_role_info"""
    if isinstance(v, str):
        role, context, school = v.split(":")
        return {"role": role, "context": context, "school": school}
    return v


def _parse_ucsschool_roles(values: Iterable[str | UcsschoolRole]) -> list[str]:
    """Skip malformed role strings instead of rejecting the whole object

    one garbage entry must not make an otherwise valid user or group invisible
    to the cache. An object with no parseable role at all still fails
    validation through min_length.
    """
    roles = []
    for item in values:
        try:
            roles.append(_parse_ucsschool_role_item(item))
        except ValueError:
            logger.warning("Ignoring malformed ucsschool role string %r", item)
    return roles


def _parse_guardian_role_item(v):
    if isinstance(v, str):
        app, namespace, role_name = v.split(":")
        return {"app": app, "namespace": namespace, "role_name": role_name}
    return v


class UserProperties(BaseModel):
    univentionObjectIdentifier: UOID
    ucsschoolRole: list[UcsschoolRole] = Field(..., min_length=1)
    username: str
    school: list[str]
    groups: list[str]
    ucsschoolLegalWard: list[str] = Field(default_factory=list)
    ucsschoolLegalGuardian: list[str] = Field(default_factory=list)
    disabled: bool
    firstname: str
    lastname: str
    ucsschoolRecordUID: str | None = None
    ucsschoolSourceUID: str | None = None
    mailPrimaryAddress: str | None = None
    birthday: date | None = None
    userexpiry: date | None = None

    @field_validator("ucsschoolRole", mode="before")
    @classmethod
    def parse_ucsschool_roles(cls, v):
        return _parse_ucsschool_roles(v)

    model_config = ConfigDict(extra="allow")


class GroupProperties(BaseModel):
    univentionObjectIdentifier: UOID
    ucsschoolRole: list[UcsschoolRole] = Field(..., min_length=1)
    name: str
    allowedEmailUsers: list[str]
    allowedEmailGroups: list[str]
    users: list[str]
    mailAddress: str | None = None
    description: str | None = None
    guardianMemberRoles: list[Annotated[GuardianRole, BeforeValidator(_parse_guardian_role_item)]]

    @field_validator("ucsschoolRole", mode="before")
    @classmethod
    def parse_ucsschool_roles(cls, v):
        return _parse_ucsschool_roles(v)

    model_config = ConfigDict(extra="allow")


class SchoolProperties(BaseModel):
    univentionObjectIdentifier: UOID
    name: str
    displayName: str
    ucsschoolClassShareFileServer: str | None = None
    ucsschoolHomeShareFileServer: str | None = None
    model_config = ConfigDict(extra="allow")


# ── Payload models (dn + typed properties) ───────────────────────────────────


class EventPayload(BaseModel):
    dn: str = Field(..., min_length=1)
    model_config = ConfigDict(extra="allow")


class UserPayload(EventPayload):
    properties: UserProperties


class GroupPayload(EventPayload):
    properties: GroupProperties


class SchoolPayload(EventPayload):
    properties: SchoolProperties


class DeletedObjectProperties(BaseModel):
    """Properties of a deleted object, built from the CCF delete task.

    A delete task carries no properties, only the object ID (the
    `univentionObjectIdentifier`) and the DN. `name` is set for DC host
    groups only: they are not stored as objects in the Kelvin DB, their name
    (the leaf cn of the DN) identifies the school whose servers to clear.
    """

    univentionObjectIdentifier: UOID
    name: str = ""
    model_config = ConfigDict(extra="allow")


class DeletePayload(EventPayload):
    properties: DeletedObjectProperties


# ── Per-operation event models ────────────────────────────────────────────────


class EventBase(BaseModel):
    pass


class UserCreateEvent(EventBase):
    new: UserPayload


class UserModifyEvent(EventBase):
    new: UserPayload


class UserDeleteEvent(EventBase):
    old: DeletePayload


class GroupCreateEvent(EventBase):
    new: GroupPayload


class GroupModifyEvent(EventBase):
    new: GroupPayload


class GroupDeleteEvent(EventBase):
    old: DeletePayload


class SchoolCreateEvent(EventBase):
    new: SchoolPayload


class SchoolModifyEvent(EventBase):
    new: SchoolPayload


class SchoolDeleteEvent(EventBase):
    old: DeletePayload


class HostGroupProperties(BaseModel):
    univentionObjectIdentifier: UOID
    description: str | None = None
    name: str
    hosts: list[str]
    model_config = ConfigDict(extra="allow")


class HostGroupPayload(EventPayload):
    properties: HostGroupProperties


class HostGroupCreateEvent(EventBase):
    new: HostGroupPayload


class HostGroupModifyEvent(EventBase):
    new: HostGroupPayload


class HostGroupDeleteEvent(EventBase):
    # The name is the leaf cn of the deleted group's DN (see tasks.py).
    old: DeletePayload
