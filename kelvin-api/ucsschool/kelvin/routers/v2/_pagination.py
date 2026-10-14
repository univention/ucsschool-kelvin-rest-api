# SPDX-FileCopyrightText: 2026 Univention GmbH
# SPDX-License-Identifier: AGPL-3.0-only

"""Keyset pagination for the v2 collection endpoints.

A page is requested with ``limit`` and, after the first page, the opaque
``cursor`` taken from the URLs in the ``Link`` header (RFC 8288) of a previous
page. The header links to the ``first``, ``prev``, ``next`` and ``last`` page;
the body stays the plain list of the page's objects. The cursor holds the name
the page continues from, so every request stands on its own: any Kelvin
instance can answer it. Going forward, objects added or removed in between
neither shift nor repeat the rest.

Objects are paged by ``name``, which is unique for every v2 collection.
Without ``limit``, an endpoint answers with the plain list it always did.
"""

import base64
import json
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import Annotated, Generic, TypeVar, cast

from fastapi import HTTPException, Query, Request, status
from pydantic import BaseModel
from ucsschool_objects import LoadSpec, Manager, SearchQuery, SortSpec

from ._responses import ModelListResponse

TModel = TypeVar("TModel", bound=BaseModel)
TItem = TypeVar("TItem")

MAX_PAGE_SIZE = 1000
_CURSOR_VERSION = 1

# For the ``responses`` of a paginated route, to document the header in the OpenAPI schema.
LINK_HEADER_RESPONSES: dict[int | str, dict[str, object]] = {
    200: {
        "headers": {
            "Link": {
                "description": (
                    "Only with ``limit``: the URLs of the ``first``, ``prev``, ``next`` and "
                    "``last`` page, as in RFC 8288. ``prev`` is left out on the first page, "
                    "``next`` on the last."
                ),
                "schema": {"type": "string"},
            }
        }
    }
}


@dataclass(frozen=True)
class Cursor:
    """Position of a page: behind ``name`` going forward, before it going back.

    Going back without a ``name`` starts at the end: the last page.
    """

    name: str | None
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
                if "before" in fields and (before is None or isinstance(before, str)):
                    return cls(name=before, forward=False)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid 'cursor'. Use the URLs of the 'Link' header of a previous page unchanged.",
        )


LAST_PAGE = Cursor(name=None, forward=False)


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
        if self.cursor is None or self.cursor.name is None:
            return None
        return (self.cursor.name,)

    @property
    def fetch_limit(self) -> int:
        # One extra object tells whether there is a next page.
        return self.size + 1


def page_request(
    limit: Annotated[
        int | None,
        Query(
            ge=1,
            le=MAX_PAGE_SIZE,
            description=(
                "Return at most this many objects, as one page. The ``Link`` header "
                "of the response holds the URLs of the first, previous, next and "
                "last page. Without it, all objects are returned."
            ),
        ),
    ] = None,
    cursor: Annotated[
        str | None,
        Query(
            description=(
                "Position of the page to return. Don't build it, take the URLs of "
                "the ``Link`` header of a previous page. Requires ``limit``."
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
    neighbour that exists, or that the client came from, gets a cursor: going
    forward the previous page whenever there was a cursor, going back the next
    one unless the page is the last.
    """
    items = list(fetched[: page.size])
    more = len(fetched) > page.size
    cursor = page.cursor
    if cursor is None or cursor.forward:
        has_next, has_previous = more, cursor is not None
    else:
        items.reverse()
        has_next, has_previous = cursor.name is not None, more
    if not items:
        return PageItems(items=items, next_cursor=None, previous_cursor=None)
    first, last = name(items[0]), name(items[-1])
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
    deleted since the client passed them can leave the page at the start short,
    or even empty. Reaching the start that way answers with the actual first
    page instead. A short last page that reaches the start already is the
    whole collection.
    """
    fetched = await manager.search(
        query,
        sort_by=page.sort_by,
        search_after=page.search_after,
        limit=page.fetch_limit,
        load=load,
    )
    found = cut_page(page, list(fetched), name)
    if (
        not page.forward
        and page.search_after is not None
        and found.previous_cursor is None
        and len(found.items) < page.size
    ):
        first_page = PageRequest(size=page.size, cursor=None)
        return await search_page(manager, query, first_page, name, load=load)
    return found


def page_url(request: Request, cursor: Cursor | None) -> str:
    """The request's own URL, all filters kept, pointing at ``cursor``, or at the first page."""
    url = request.url.remove_query_params("cursor")
    if cursor is not None:
        url = url.include_query_params(cursor=cursor.encode())
    return str(url.replace(scheme="https"))


def link_header(request: Request, page: PageItems[TItem]) -> str:
    """The ``Link`` header value of ``page``: always ``first`` and ``last``, neighbours if any."""
    links = {"first": page_url(request, None)}
    if page.previous_cursor is not None:
        links["prev"] = page_url(request, page.previous_cursor)
    if page.next_cursor is not None:
        links["next"] = page_url(request, page.next_cursor)
    links["last"] = page_url(request, LAST_PAGE)
    return ", ".join(f'<{url}>; rel="{rel}"' for rel, url in links.items())


def page_response(
    request: Request, page: PageItems[TItem], models: Sequence[TModel]
) -> ModelListResponse[TModel]:
    return ModelListResponse(models, headers={"Link": link_header(request, page)})
