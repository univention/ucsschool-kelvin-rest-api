# SPDX-FileCopyrightText: 2020-2026 Univention GmbH
# SPDX-License-Identifier: AGPL-3.0-only

# Mapped UDM properties that can be set on users
# keep in sync with MAPPED_UDM_PROPERTIES in [ucsschool-repo(4.4|5.0)]/ucs-test-ucsschool/modules/...
# .../univention/testing/ucsschool/conftest.py and [ucs-repo(4.4|5.0)]/test/utils/...
# .../ucsschool_id_connector.py
# if changed: check tests/test_route_user.test_search_filter_udm_properties()
MAPPED_UDM_PROPERTIES = [
    "title",
    "description",
    "displayName",
    "e-mail",
    "employeeType",
    "organisation",
    "phone",
    "uidNumber",
    "gidNumber",
]
