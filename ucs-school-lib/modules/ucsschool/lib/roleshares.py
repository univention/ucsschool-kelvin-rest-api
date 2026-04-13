# SPDX-FileCopyrightText: 2026 Univention GmbH
# SPDX-License-Identifier: AGPL-3.0-only

"""
Role specific shares
"""

import os
from typing import List

from ucsschool.lib.i18n import ucs_school_name_i18n
from ucsschool.lib.roles import (
    role_legal_guardian,
    role_pupil,
    role_school_admin,
    role_staff,
    role_student,
    role_teacher,
)

try:
    from univention.config_registry import ConfigRegistry
except ImportError:
    pass


def roleshare_name(role: str, school_ou: str, ucr: ConfigRegistry) -> str:
    custom_roleshare_name = ucr.get("ucsschool/import/roleshare/%s" % (role,))
    if custom_roleshare_name:
        return custom_roleshare_name
    else:
        return "-".join((ucs_school_name_i18n(role), school_ou))


def roleshare_path(role: str, school_ou: str, ucr: ConfigRegistry) -> str:
    custom_roleshare_path = ucr.get("ucsschool/import/roleshare/%s/path" % (role,))
    if custom_roleshare_path:
        return custom_roleshare_path
    else:
        return os.path.join(school_ou, ucs_school_name_i18n(role))


def roleshare_home_subdir(school_ou: str, roles: List[str], ucr: ConfigRegistry = None) -> str:
    if not ucr:
        from .models.utils import ucr
    if ucr.is_true("ucsschool/import/roleshare", True):
        # student is a role from kelvin, which here should be treated like 'pupil'
        # see bug #52926
        for role in (
            role_student,
            role_pupil,
            role_teacher,
            role_legal_guardian,
            role_school_admin,
            role_staff,
        ):
            if role in roles:
                role_for_path = role
                if role_for_path == role_student:
                    role_for_path = role_pupil
                return roleshare_path(role_for_path, school_ou, ucr)
    return ""
