# Copyright 2022 Univention GmbH
#
# http://www.univention.de/
#
# All rights reserved.
#
# The source code of this program is made available
# under the terms of the GNU Affero General Public License version 3
# (GNU AGPL V3) as published by the Free Software Foundation.
#
# Binary versions of this program provided by Univention to you as
# well as other copyrighted, protected or trademarked materials like
# Logos, graphics, fonts, specific documentations and configurations,
# cryptographic keys etc. are subject to a license agreement between
# you and Univention and not subject to the GNU AGPL V3.
#
# In the case you use this program under the terms of the GNU AGPL V3,
# the program is provided in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
# GNU Affero General Public License for more details.
#
# You should have received a copy of the GNU Affero General Public
# License with the Debian GNU/Linux or Univention distribution in file
# /usr/share/common-licenses/AGPL-3; if not, see
# <http://www.gnu.org/licenses/>.

import random
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

import ucsschool.kelvin.constants
import ucsschool.kelvin.routers.role
from ucsschool.kelvin.main import app, clear_stats_cache

pytestmark = pytest.mark.skipif(
    not ucsschool.kelvin.constants.CN_ADMIN_PASSWORD_FILE.exists(),
    reason="Must run inside Docker container started by appcenter.",
)


@pytest.fixture
def clear_stats_after_test():
    yield
    clear_stats_cache()


def test_get_status_no_errors():
    clear_stats_cache()
    url = app.url_path_for("get_status")
    client = TestClient(app)
    response = client.get(url)
    json_resp = response.json()
    assert response.status_code == 200
    assert json_resp["internal_errors_last_minute"] == 0
    assert json_resp["version"] == str(ucsschool.kelvin.constants.APP_VERSION)


def test_get_status_with_errors(auth_header, clear_stats_after_test, url_fragment):
    num_errors = random.randint(3, 6)
    # Don't raise the exception here in the test code, but let the server handle it
    # -> HTTP 500 -> main.unhandled_exception_handler()
    client = TestClient(app, raise_server_exceptions=False)
    # create exception in SchoolUserRole.to_url():
    # TypeError: <lambda>() takes 0 positional arguments but 2 were given
    # That exception will lead to a HTTP 500
    with patch.object(ucsschool.kelvin.routers.role.SchoolUserRole, "to_url", lambda: "foo"):
        for _ in range(num_errors):
            response = client.get(f"{url_fragment}/roles", headers=auth_header)
            assert response.status_code == 500

    response = client.get(app.url_path_for("get_status"))
    assert response.status_code == 200
    json_resp = response.json()
    assert json_resp["internal_errors_last_minute"] == num_errors
    assert json_resp["version"] == str(ucsschool.kelvin.constants.APP_VERSION)
