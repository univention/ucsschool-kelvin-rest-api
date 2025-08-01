# Copyright 2023 Univention GmbH
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

import pytest
import requests
from faker import Faker

import ucsschool.kelvin.constants

pytestmark = pytest.mark.skipif(
    not ucsschool.kelvin.constants.CN_ADMIN_PASSWORD_FILE.exists(),
    reason="Must run inside Docker container started by appcenter.",
)

fake = Faker()


@pytest.mark.asyncio
@pytest.mark.parametrize("role_name", ["staff", "student", "teacher", "school_admin"])
async def test_get_existing_role(auth_header, retry_http_502, url_fragment, role_name):
    response = retry_http_502(
        requests.get,
        f"{url_fragment}/roles/{role_name}",
        headers=auth_header,
    )
    assert response.status_code == 200, response.reason
    assert response.json()["name"] == role_name


@pytest.mark.asyncio
async def test_get_non_existing_role_returns_404(auth_header, retry_http_502, url_fragment):
    response = retry_http_502(
        requests.get,
        f"{url_fragment}/roles/{fake.user_name()}",
        headers=auth_header,
    )
    assert response.status_code == 404, response.reason
