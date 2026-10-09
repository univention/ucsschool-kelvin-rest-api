# SPDX-FileCopyrightText: 2026 Univention GmbH
# SPDX-License-Identifier: AGPL-3.0-only

"""Keyset pagination for the v2 collection endpoints.

A page is requested with ``limit`` and, after the first page, the opaque
``cursor`` taken from a previous page's ``next_page_url`` or
``previous_page_url``. The cursor holds the name of the object the page starts
behind, so every request stands on its own: any Kelvin instance can answer it,
and objects added or removed in between neither shift nor repeat the rest.

Objects are paged by ``name``, which is unique for every v2 collection.
Without ``limit``, an endpoint answers with the plain list it always did.
"""

import base64
import json
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import Annotated, Generic, TypeVar, cast

from fastapi import HTTPException, Query, Request, status
from fastapi.responses import ORJSONResponse
from pydantic import BaseModel
from pydantic.generics import GenericModel
from ucsschool_objects import LoadSpec, Manager, SearchQuery, SortSpec

from ...schema import KelvinBaseModel

TModel = TypeVar("TModel", bound=BaseModel)
TItem = TypeVar("TItem")

MAX_PAGE_SIZE = 1000
_CURSOR_VERSION = 1


class Page(GenericModel, Generic[TModel]):
    """One page of a collection, as documented in the OpenAPI schema."""

    results: list[TModel]
    next_page_url: str | None
    previous_page_url: str | None

    class Config(KelvinBaseModel.Config):
        pass


@dataclass(frozen=True)
class Cursor:
    """Position of a page: behind ``name`` going forward, before it going back."""

    name: str
    forward: bool

    def encode(self) -> str:
        key = "after" if self.forward else "before"
        raw = json.dumps({"v": _CURSOR_VERSION, key: self.name}, separators=(",", ":"))
        return base64.urlsafe_b64encode(raw.encode()).rstrip(b"=").decode("ascii")

    @classmethod
    def decode(cls, token: str) -> "Cursor":
        try:
            data = cast(object, json.loads(base64.urlsafe_b64decode(token + "=" * (-len(token) % 4))))
        except ValueError:  # covers binascii.Error, UnicodeDecodeError and JSONDecodeError
            data = None
        if isinstance(data, dict):
            fields = cast("dict[str, object]", data)
            after, before = fields.get("after"), fields.get("before")
            if fields.get("v") == _CURSOR_VERSION and len(fields) == 2:
                if isinstance(after, str):
                    return cls(name=after, forward=True)
                if isinstance(before, str):
                    return cls(name=before, forward=False)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid 'cursor'. Use the URLs of a previous page unchanged.",
        )


@dataclass(frozen=True)
class PageRequest:
    """What the client asked for, and how to search for it."""

    size: int
    cursor: Cursor | None

    @property
    def forward(self) -> bool:
        return self.cursor is None or self.cursor.forward

    @property
    def sort_by(self) -> tuple[SortSpec, ...]:
        return (SortSpec(field="name", ascending=self.forward),)

    @property
    def search_after(self) -> tuple[str] | None:
        return None if self.cursor is None else (self.cursor.name,)

    @property
    def fetch_limit(self) -> int:
        # The one beyond the page tells whether there is another page.
        return self.size + 1


def page_request(
    limit: Annotated[
        int | None,
        Query(
            ge=1,
            le=MAX_PAGE_SIZE,
            description=(
                "Return at most this many objects, as one page with links to the "
                "next and the previous page. Without it, all objects are returned "
                "as a plain list."
            ),
        ),
    ] = None,
    cursor: Annotated[
        str | None,
        Query(
            description=(
                "Position of the page to return. Don't build it, take the "
                "``next_page_url`` or ``previous_page_url`` of a previous page. "
                "Requires ``limit``."
            ),
        ),
    ] = None,
) -> PageRequest | None:
    if limit is None:
        if cursor is not None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="'cursor' requires 'limit'.",
            )
        return None
    return PageRequest(size=limit, cursor=Cursor.decode(cursor) if cursor else None)


@dataclass(frozen=True)
class PageItems(Generic[TItem]):
    """A page's objects in ascending order and the cursors to its neighbours."""

    items: list[TItem]
    next_cursor: Cursor | None
    previous_cursor: Cursor | None


def cut_page(
    page: PageRequest, fetched: Sequence[TItem], name: Callable[[TItem], str]
) -> PageItems[TItem]:
    """Trim what was fetched for ``page`` to the page and find its neighbours.

    Objects come in search order, which is descending when paging back. A
    neighbour that is known to exist gets a cursor. Going forward, the previous
    page is assumed to exist whenever there was a cursor, and going back the
    next one: the client came from there.
    """
    items = list(fetched[: page.size])
    more = len(fetched) > page.size
    if not page.forward:
        items.reverse()
    if not items:
        return PageItems(items=items, next_cursor=None, previous_cursor=None)
    first, last = name(items[0]), name(items[-1])
    has_next = more if page.forward else True
    has_previous = page.cursor is not None if page.forward else more
    return PageItems(
        items=items,
        next_cursor=Cursor(name=last, forward=True) if has_next else None,
        previous_cursor=Cursor(name=first, forward=False) if has_previous else None,
    )


async def search_page(
    manager: Manager[TItem],
    query: SearchQuery | None,
    page: PageRequest,
    name: Callable[[TItem], str],
    *,
    load: LoadSpec | None = None,
) -> PageItems[TItem]:
    """Search ``manager`` for the objects of ``page``.

    Paging back fills a page from its cursor backwards, so objects created or
    deleted before the cursor in the meantime leave the first page short, or
    even empty. Reaching the start that way answers with the actual first page
    instead.
    """
    fetched = await manager.search(
        query,
        sort_by=page.sort_by,
        search_after=page.search_after,
        limit=page.fetch_limit,
        load=load,
    )
    found = cut_page(page, list(fetched), name)
    if not page.forward and found.previous_cursor is None and len(found.items) < page.size:
        first_page = PageRequest(size=page.size, cursor=None)
        return await search_page(manager, query, first_page, name, load=load)
    return found


def page_url(request: Request, cursor: Cursor | None) -> str | None:
    """The request's own URL, all filters kept, pointing at ``cursor``."""
    if cursor is None:
        return None
    return str(request.url.include_query_params(cursor=cursor.encode()).replace(scheme="https"))


class ModelPageResponse(ORJSONResponse, Generic[TModel]):
    """Serialise a ``Page`` the way ``ModelListResponse`` does a plain list."""

    def __init__(
        self,
        models: Sequence[TModel],
        next_page_url: str | None,
        previous_page_url: str | None,
    ) -> None:
        super().__init__(
            {
                "results": [model.dict(by_alias=True) for model in models],
                "next_page_url": next_page_url,
                "previous_page_url": previous_page_url,
            }
        )


def page_response(
    request: Request, page: PageItems[TItem], models: Sequence[TModel]
) -> ModelPageResponse[TModel]:
    return ModelPageResponse(
        models,
        next_page_url=page_url(request, page.next_cursor),
        previous_page_url=page_url(request, page.previous_cursor),
    )
