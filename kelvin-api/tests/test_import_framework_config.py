# SPDX-FileCopyrightText: 2020-2026 Univention GmbH
# SPDX-License-Identifier: AGPL-3.0-only

import pytest

from ucsschool.importer.exceptions import UcsSchoolImportError
from ucsschool.kelvin.import_config import init_ucs_school_import_framework

pytestmark = pytest.mark.in_container


def test_config_loads():
    init_ucs_school_import_framework()


def test_missing_checks(reset_import_config_module):
    reset_import_config_module()
    with pytest.raises(UcsSchoolImportError) as exc_info:
        init_ucs_school_import_framework(configuration_checks=["mapped_udm_properties"])
    assert 'Missing "class_overwrites" in configuration checks' in exc_info.value.args[0]
    reset_import_config_module()
    with pytest.raises(UcsSchoolImportError) as exc_info:
        init_ucs_school_import_framework(configuration_checks=["class_overwrites"])
    assert 'Missing "mapped_udm_properties" in configuration checks' in exc_info.value.args[0]
    reset_import_config_module()
    init_ucs_school_import_framework(configuration_checks=["mapped_udm_properties", "class_overwrites"])
