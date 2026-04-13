# SPDX-FileCopyrightText: 2026 Univention GmbH
# SPDX-License-Identifier: AGPL-3.0-only

from collections.abc import Callable
from typing import TypeAlias

from ucsschool_objects.database_models import (
    Group,
    GroupType,
    Role,
    School,
    SchoolMembership,
    User,
)

SchoolDataFactory: TypeAlias = Callable[[], dict[str, object]]
GroupDataFactory: TypeAlias = Callable[[], dict[str, object]]
UserDataFactory: TypeAlias = Callable[[], dict[str, object]]
RoleDataFactory: TypeAlias = Callable[[], dict[str, object]]
GroupTypeDataFactory: TypeAlias = Callable[[], dict[str, object]]

SchoolFactory: TypeAlias = Callable[..., School]
GroupFactory: TypeAlias = Callable[..., Group]
UserFactory: TypeAlias = Callable[..., User]
RoleFactory: TypeAlias = Callable[..., Role]
GroupTypeFactory: TypeAlias = Callable[..., GroupType]
SchoolMembershipFactory: TypeAlias = Callable[..., SchoolMembership]

ModelInstance: TypeAlias = Group | GroupType | Role | School | SchoolMembership | User
RecordSourceInstance: TypeAlias = Group | School | User

ModelFactory: TypeAlias = (
    SchoolFactory | GroupFactory | UserFactory | RoleFactory | GroupTypeFactory | SchoolMembershipFactory
)
RecordSourceFactory: TypeAlias = Callable[..., RecordSourceInstance]
