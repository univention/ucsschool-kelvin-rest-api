# SPDX-FileCopyrightText: 2026 Univention GmbH
# SPDX-License-Identifier: AGPL-3.0-only

from pydantic import PydanticValueError


class ObjectAlreadyExists(PydanticValueError):
    # raise ObjectExistsError(key="name", value=school_class.name)
    code = "object_exists"
    msg_template = 'object with "{key}"="{value}" already exists'


class UnknownUDMProperty(ValueError):
    ...


class InvalidConfiguration(ValueError):
    ...
