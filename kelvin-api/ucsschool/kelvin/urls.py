# Copyright 2020-2021 Univention GmbH
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

from typing import Any, Union

from cachetools import LRUCache, cached
from cachetools.keys import hashkey
from fastapi import Request
from pydantic import HttpUrl
from starlette.datastructures import URL

from ucsschool.lib.models.base import NoObject
from ucsschool.lib.models.utils import env_or_ucr

from .ldap import get_dn_of_user


@cached(
    cache=LRUCache(maxsize=10240),
    key=lambda request, name, **path_params: hashkey(
        name, request.headers.get("host", None), tuple(sorted(path_params.items()))
    ),
)
def cached_url_for(request: Request, name: str, **path_params: Any) -> URL:
    """Cached drop-in replacement for `request.url_for()`."""
    # Using `cachetools`, because `lru_cache` does not support dropping a function argument. And we
    # don't want the `request` object to be part of the cache key.
    return URL(str(request.url_for(name, **path_params)))


@cached(
    cache=LRUCache(maxsize=10240),
    key=lambda request, obj_type, url: hashkey(obj_type, url),
)
def url_to_name(request: Request, obj_type: str, url: Union[str, HttpUrl]) -> str:
    """
    Convert URL to object name.

    https://.../kelvin/v1/schools/DEMOSCHOOL => DEMOSCHOOL
    https://.../kelvin/v1/users/demo_student => demo_student
    https://.../kelvin/v1/roles/student => student
    """
    if not url:
        return url
    url = URL(str(url))
    if url.scheme == "https":
        raise RuntimeError(f"Missed unscheme_and_unquote() for {url!r}.")
    no_object_exception = NoObject(f"Could not find object of type {obj_type!r} with {url!r}.")
    name = url.path.rstrip("/").split("/")[-1]
    if obj_type == "school":
        calc_url = cached_url_for(request, "school_get", school_name=name)
        if url.path != calc_url.path:
            raise no_object_exception
    elif obj_type == "user":
        calc_url = cached_url_for(request, "get", username=name)
        if url.path != calc_url.path:
            raise no_object_exception
    elif obj_type == "role":
        calc_url = cached_url_for(request, "get", role_name=name)
        if url.path != calc_url.path:
            raise no_object_exception
    else:
        raise no_object_exception
    return name


@cached(
    cache=LRUCache(maxsize=10240),
    key=lambda request, obj_type, url: hashkey(obj_type, url),
)
def url_to_dn(request: Request, obj_type: str, url: str) -> str:
    """
    Guess object ID (e.g. school name or username) from last part of URL. If
    object is user, search object with UDM HTTP API to retrieve DN.
    """
    name = url_to_name(request, obj_type, url)
    if obj_type == "school":
        return f"ou={name},{env_or_ucr('ldap/base')}"
    elif obj_type == "user":
        if dn := get_dn_of_user(name):
            return dn
        else:
            raise NoObject(f"Could not find object of type {obj_type!r} with URL {url!r}.")
    raise NotImplementedError(f"Don't know how to create DN for obj_type {obj_type!r}.")
