# SPDX-FileCopyrightText: 2026 Univention GmbH
# SPDX-License-Identifier: AGPL-3.0-only

from typing import Any, Union

from cachetools import LRUCache, cached
from cachetools.keys import hashkey
from fastapi import Request
from pydantic import HttpUrl
from starlette.datastructures import URL
from starlette.routing import NoMatchFound, Router

from ucsschool.lib.models.base import NoObject
from ucsschool.lib.models.utils import env_or_ucr

from .ldap import get_dn_of_user


def _matching_path_segments(path_a: str, path_b: str) -> int:
    segments_a = [part for part in path_a.strip("/").split("/") if part]
    segments_b = [part for part in path_b.strip("/").split("/") if part]

    matching = 0
    for part_a, part_b in zip(segments_a, segments_b):
        if part_a != part_b:
            break
        matching += 1
    return matching


def _request_route_signature(request: Request) -> str:
    route = request.scope.get("route")
    if route is not None and getattr(route, "path_format", None):
        return route.path_format
    return request.url.path


def _url_for_same_api_prefix(request: Request, name: str, **path_params: Any) -> URL:
    request_path = request.url.path
    fallback_url = None
    fallback_score = -1
    router: Router = request.app.router

    for route in router.routes:
        try:
            url_path = route.url_path_for(name, **path_params)
        except NoMatchFound:
            continue

        url = URL(str(url_path.make_absolute_url(base_url=request.base_url)))
        score = _matching_path_segments(request_path, url.path)
        if score > fallback_score:
            fallback_score = score
            fallback_url = url

    if fallback_url is not None:
        return fallback_url
    raise NoMatchFound(name, path_params)


@cached(
    cache=LRUCache(maxsize=10240),
    key=lambda request, name, **path_params: hashkey(
        name,
        request.base_url.scheme,
        request.headers.get("host", None),
        _request_route_signature(request),
        tuple(sorted(path_params.items())),
    ),
)
def cached_url_for(request: Request, name: str, **path_params: Any) -> URL:
    """Cached drop-in replacement for `request.url_for()`."""
    # Using `cachetools`, because `lru_cache` does not support dropping a function argument. And we
    # don't want the `request` object to be part of the cache key.
    return _url_for_same_api_prefix(request, name, **path_params)


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
    https://.../kelvin/v2/schools/DEMOSCHOOL => DEMOSCHOOL
    https://.../kelvin/v2/users/demo_student => demo_student
    https://.../kelvin/v2/roles/student => student
    https://.../kelvin/dev/schools/DEMOSCHOOL => DEMOSCHOOL
    https://.../kelvin/dev/users/demo_student => demo_student
    https://.../kelvin/dev/roles/student => student
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
