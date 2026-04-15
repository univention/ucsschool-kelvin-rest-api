from __future__ import annotations

from ucsschool_objects.core.domain import (
    UNLOADED,
    Group,
    Role,
    School,
    SchoolMembership,
    UnloadedType,
    User,
)
from ucsschool_objects.database_models import (
    Group as GroupModel,
    Role as RoleModel,
    School as SchoolModel,
    SchoolMembership as SchoolMembershipModel,
    User as UserModel,
)


def to_school(model: SchoolModel) -> School:
    return School(
        public_id=model.public_id,
        record_uid=model.record_uid,
        source_uid=model.source_uid,
        name=model.name,
        display_name=dict(model.display_name),
        educational_servers=frozenset(model.educational_servers),
        administrative_servers=frozenset(model.administrative_servers),
        class_share_file_server=model.class_share_file_server,
        home_share_file_server=model.home_share_file_server,
    )


def to_role(model: RoleModel) -> Role:
    return Role(
        public_id=model.public_id,
        name=model.name,
        display_name=dict(model.display_name),
    )


def to_group(model: GroupModel, *, include_school: bool) -> Group:
    school: School | UnloadedType
    if include_school:
        school = to_school(model.school)
    else:
        school = UNLOADED

    return Group(
        public_id=model.public_id,
        record_uid=model.record_uid,
        source_uid=model.source_uid,
        name=model.name,
        display_name=dict(model.display_name),
        create_share=model.has_share,
        group_type=model.group_type.name,
        email=model.email,
        allowed_email_senders_users=frozenset(user.name for user in model.allowed_email_senders_users),
        allowed_email_senders_groups=frozenset(
            group.name for group in model.allowed_email_senders_groups
        ),
        member_roles=UNLOADED,
        school=school,
    )


def _to_school_membership(
    model: SchoolMembershipModel,
    *,
    include_roles: bool,
    include_groups: bool,
) -> SchoolMembership:
    roles: frozenset[Role] | UnloadedType = (
        frozenset(to_role(r) for r in model.roles) if include_roles else UNLOADED
    )
    groups: frozenset[Group] | UnloadedType = (
        frozenset(to_group(g, include_school=False) for g in model.groups)
        if include_groups
        else UNLOADED
    )
    return SchoolMembership(
        school=to_school(model.school),
        is_primary=model.is_primary,
        roles=roles,
        groups=groups,
    )


def _to_related_user(model: UserModel) -> User:
    return User(
        public_id=model.public_id,
        record_uid=model.record_uid,
        source_uid=model.source_uid,
        name=model.name,
        firstname=model.firstname,
        lastname=model.lastname,
        email=model.email,
        birthday=model.birthday,
        expiration_date=model.expiration_date,
        active=model.active,
        school_memberships=UNLOADED,
        legal_wards=UNLOADED,
        legal_guardians=UNLOADED,
    )


def _optional_user_relation(models: tuple[UserModel, ...] | list[UserModel]) -> frozenset[User]:
    return frozenset(_to_related_user(model) for model in models)


def to_user(
    model: UserModel,
    *,
    include_memberships: bool,
    include_groups: bool,
    include_roles: bool,
    include_legal_wards: bool,
    include_legal_guardians: bool,
) -> User:
    school_memberships: frozenset[SchoolMembership] | UnloadedType = UNLOADED

    if include_memberships:
        school_memberships = frozenset(
            _to_school_membership(m, include_roles=include_roles, include_groups=include_groups)
            for m in model.school_memberships
        )

    legal_wards: frozenset[User] | UnloadedType = UNLOADED
    if include_legal_wards:
        legal_wards = _optional_user_relation(model.legal_wards)

    legal_guardians: frozenset[User] | UnloadedType = UNLOADED
    if include_legal_guardians:
        legal_guardians = _optional_user_relation(model.legal_guardians)

    return User(
        public_id=model.public_id,
        record_uid=model.record_uid,
        source_uid=model.source_uid,
        name=model.name,
        firstname=model.firstname,
        lastname=model.lastname,
        email=model.email,
        birthday=model.birthday,
        expiration_date=model.expiration_date,
        active=model.active,
        school_memberships=school_memberships,
        legal_wards=legal_wards,
        legal_guardians=legal_guardians,
    )
