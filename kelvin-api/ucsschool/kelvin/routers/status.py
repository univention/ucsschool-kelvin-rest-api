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

import time
from functools import lru_cache

from diskcache import Cache
from fastapi import APIRouter
from pydantic import BaseModel

from ..constants import APP_VERSION, STATS_CACHE_DIR

router = APIRouter()


class StatusModel(BaseModel):
    internal_errors_last_minute: int
    version: str


@lru_cache(maxsize=1)
def get_stats_cache() -> Cache:
    return Cache(STATS_CACHE_DIR)


def add_error(exc: Exception) -> None:
    cache = get_stats_cache()
    cache.set(time.time(), str(exc), expire=60)


@router.get("", response_model=StatusModel)
async def get_status() -> StatusModel:  # no authentication needed, so this can be used by load balancers
    cache = get_stats_cache()
    cache.expire()
    return StatusModel(internal_errors_last_minute=len(cache), version=str(APP_VERSION))
