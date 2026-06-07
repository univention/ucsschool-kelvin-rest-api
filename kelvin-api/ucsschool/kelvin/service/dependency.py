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


from functools import lru_cache
from typing import AsyncGenerator

from fastapi import HTTPException, Request, status
from sqlalchemy import create_engine
from ucsschool_objects import KelvinStorageSession

from alembic.config import Config
from alembic.migration import MigrationContext
from alembic.script import ScriptDirectory
from ucsschool.kelvin.constants import ALEMBIC_CONFIG_FILE
from ucsschool.kelvin.database import get_database_url


@lru_cache(maxsize=1)
def _get_alembic_head_revision() -> str:
    # Not CWD-relative: a relative path only resolves when the process
    # happens to start in /kelvin (gunicorn does, the test runner does not).
    # Override via the ALEMBIC_CONFIG env var, e.g. for uv-based dev runs.
    alembic_cfg = Config(toml_file=str(ALEMBIC_CONFIG_FILE))
    return ScriptDirectory.from_config(alembic_cfg).get_current_head()


def check_db_compatibility() -> bool:
    head_revision = _get_alembic_head_revision()
    database_url = get_database_url()
    engine = create_engine(database_url)
    try:
        with engine.connect() as connection:
            context = MigrationContext.configure(connection)
            current_revision = context.get_current_revision()
            connection.commit()
    finally:
        engine.dispose()
    if current_revision != head_revision:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="This instance is deprecated. Please upgrade.",
        )


async def get_storage_session(request: Request) -> AsyncGenerator[KelvinStorageSession, None]:
    async with request.app.state.storage_session_factory.session_scope() as session:
        yield session
