from datetime import date

from loguru import logger
from pydantic import UUID4, BaseModel, Extra, Field, validator

# ── Per-type properties models ────────────────────────────────────────────────


class UcsschoolRole(BaseModel):
    role: str
    context: str
    school: str


class GuardianRole(BaseModel):
    app: str
    namespace: str
    role_name: str


def _parse_ucsschool_role_item(v):
    if isinstance(v, str):
        # Split like ucs-school-lib's get_role_info: the context (third part)
        # may itself contain colons, e.g. in additional-context role strings.
        role, context, school = v.split(":", 2)
        return {"role": role, "context": context, "school": school}
    return v


def _parse_ucsschool_roles(values):
    # Skip malformed role strings instead of rejecting the whole object: one
    # garbage entry must not make an otherwise valid user or group invisible
    # to the cache. An object with no parseable role at all still fails
    # validation through min_items.
    roles = []
    for item in values:
        try:
            roles.append(_parse_ucsschool_role_item(item))
        except ValueError:
            logger.warning("Ignoring malformed ucsschool role string {!r}", item)
    return roles


def _parse_guardian_role_item(v):
    if isinstance(v, str):
        app, namespace, role_name = v.split(":")
        return {"app": app, "namespace": namespace, "role_name": role_name}
    return v


class UserProperties(BaseModel):
    univentionObjectIdentifier: UUID4
    ucsschoolRole: list[UcsschoolRole] = Field(..., min_items=1)
    username: str
    school: list[str]
    groups: list[str]
    ucsschoolLegalWard: list[str] = Field(default_factory=list)
    ucsschoolLegalGuardian: list[str] = Field(default_factory=list)
    disabled: bool
    firstname: str
    lastname: str
    ucsschoolRecordUID: str | None
    ucsschoolSourceUID: str | None
    mailPrimaryAddress: str | None
    birthday: date | None
    userexpiry: date | None

    @validator("ucsschoolRole", pre=True)
    @classmethod
    def parse_ucsschool_roles(cls, v):
        return _parse_ucsschool_roles(v)

    class Config:
        extra = Extra.allow


class GroupProperties(BaseModel):
    univentionObjectIdentifier: UUID4
    ucsschoolRole: list[UcsschoolRole] = Field(..., min_items=1)
    name: str
    allowedEmailUsers: list[str]
    allowedEmailGroups: list[str]
    users: list[str]
    mailAddress: str | None
    guardianMemberRoles: list[GuardianRole]

    @validator("ucsschoolRole", pre=True)
    @classmethod
    def parse_ucsschool_roles(cls, v):
        return _parse_ucsschool_roles(v)

    @validator("guardianMemberRoles", pre=True, each_item=True)
    @classmethod
    def parse_guardian_roles(cls, v):
        return _parse_guardian_role_item(v)

    class Config:
        extra = Extra.allow


class SchoolProperties(BaseModel):
    univentionObjectIdentifier: UUID4
    name: str
    displayName: str

    class Config:
        extra = Extra.allow


# ── Payload models (dn + typed properties) ───────────────────────────────────


class EventPayload(BaseModel):
    dn: str = Field(..., min_length=1)
    id: str
    position: str
    object_type: str = Field(..., alias="objectType")

    class Config:
        extra = Extra.allow


class UserPayload(EventPayload):
    properties: UserProperties


class GroupPayload(EventPayload):
    properties: GroupProperties


class SchoolPayload(EventPayload):
    properties: SchoolProperties


class DeletedObjectProperties(BaseModel):
    """Properties of a deleted object — only the identifier is required.

    The rest of a deleted object's state may be malformed (it may even be the
    reason it was deleted) and must not prevent removing it from the cache:
    a dropped delete event leaves a stale row that no future event can ever
    repair.
    """

    univentionObjectIdentifier: UUID4
    username: str = ""
    name: str = ""

    class Config:
        extra = Extra.allow


class DeletePayload(EventPayload):
    properties: DeletedObjectProperties


# ── Per-operation event models ────────────────────────────────────────────────


class EventBase(BaseModel):
    timestamp: str
    sequence_number: int


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
    univentionObjectIdentifier: UUID4
    description: str | None
    name: str
    hosts: list[str]

    class Config:
        extra = Extra.allow


class HostGroupPayload(EventPayload):
    properties: HostGroupProperties


class HostGroupCreateEvent(EventBase):
    new: HostGroupPayload


class HostGroupModifyEvent(EventBase):
    new: HostGroupPayload


class HostGroupDeleteEvent(EventBase):
    old: HostGroupPayload
