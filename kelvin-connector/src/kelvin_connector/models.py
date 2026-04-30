from datetime import date

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
        role, context, school = v.split(":")
        return {"role": role, "context": context, "school": school}
    return v


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

    @validator("ucsschoolRole", pre=True, each_item=True)
    @classmethod
    def parse_ucsschool_roles(cls, v):
        return _parse_ucsschool_role_item(v)

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

    @validator("ucsschoolRole", pre=True, each_item=True)
    @classmethod
    def parse_ucsschool_roles(cls, v):
        return _parse_ucsschool_role_item(v)

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

    class Config:
        extra = Extra.allow


class UserPayload(EventPayload):
    properties: UserProperties


class GroupPayload(EventPayload):
    properties: GroupProperties


class SchoolPayload(EventPayload):
    properties: SchoolProperties


# ── Per-operation event models ────────────────────────────────────────────────


class EventBase(BaseModel):
    timestamp: str
    sequence_number: int


class UserCreateEvent(EventBase):
    new: UserPayload


class UserModifyEvent(EventBase):
    new: UserPayload


class UserDeleteEvent(EventBase):
    old: UserPayload


class GroupCreateEvent(EventBase):
    new: GroupPayload


class GroupModifyEvent(EventBase):
    new: GroupPayload


class GroupDeleteEvent(EventBase):
    old: GroupPayload


class SchoolCreateEvent(EventBase):
    new: SchoolPayload


class SchoolModifyEvent(EventBase):
    new: SchoolPayload


class SchoolDeleteEvent(EventBase):
    old: SchoolPayload
