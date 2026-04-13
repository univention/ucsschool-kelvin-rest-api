# SPDX-FileCopyrightText: 2026 Univention GmbH
# SPDX-License-Identifier: AGPL-3.0-only

import packaging.version

from ucsschool.kelvin.constants import APP_VERSION


def test_parse_version():
    packaging.version.parse(str(APP_VERSION))
