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
from functools import lru_cache
from pathlib import Path

from fastapi import HTTPException, status
from sqlalchemy import create_engine, make_url

from alembic.config import Config
from alembic.migration import MigrationContext
from alembic.script import ScriptDirectory
from ucsschool.lib.models.utils import env_or_ucr


@lru_cache(maxsize=1)
def _get_alembic_head_revision() -> str:
    alembic_cfg = Config(toml_file="./pyproject.toml")
    return ScriptDirectory.from_config(alembic_cfg).get_current_head()


def check_db_compatibility() -> bool:
    head_revision = _get_alembic_head_revision()
    database_url = make_url(env_or_ucr("ucsschool/kelvin/db/uri")).set(
        username=env_or_ucr("ucsschool/kelvin/db/username"),
        password=Path(
            os.getenv(
                "UCSSCHOOL_KELVIN_DB_PASSWORDFILE", "/etc/ucsschool/kelvin/postgresql-kelvin.secret"
            )
        )
        .read_text()
        .strip(),
    )
    if database_url.drivername == "postgresql":
        database_url = database_url.set(drivername="postgresql+psycopg")

    engine = create_engine(database_url)
    with engine.connect() as connection:
        context = MigrationContext.configure(connection)
        current_revision = context.get_current_revision()
    if current_revision != head_revision:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="This instance is deprecated. Please upgrade.",
        )
