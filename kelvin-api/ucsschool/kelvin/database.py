# -*- coding: utf-8 -*-

# Copyright 2026 Univention GmbH
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

import os
from pathlib import Path

from sqlalchemy import make_url
from sqlalchemy.engine.url import URL

from ucsschool.lib.models.utils import env_or_ucr


def get_database_url() -> URL:
    sqlalchemy_url = make_url(env_or_ucr("ucsschool/kelvin/db/uri")).set(
        username=env_or_ucr("ucsschool/kelvin/db/username"),
        password=Path(
            os.getenv(
                "UCSSCHOOL_KELVIN_DB_PASSWORD_FILE", "/etc/ucsschool/kelvin/postgresql-kelvin.secret"
            )
        )
        .read_text()
        .strip(),
    )

    if sqlalchemy_url.drivername == "postgresql":
        sqlalchemy_url = sqlalchemy_url.set(drivername="postgresql+psycopg")
    return sqlalchemy_url
