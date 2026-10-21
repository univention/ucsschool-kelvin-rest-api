# SPDX-FileCopyrightText: 2026 Univention GmbH
# SPDX-License-Identifier: AGPL-3.0-only

"""Unit tests for the keyset pagination of the v2 collection endpoints.

The search itself is the ``search_after`` of ``ucsschool-objects`` and tested
there. What is tested here is the part Kelvin adds: the cursor, the request
parameters, cutting what was fetched into a page, and the ``Link`` header
to its neighbours. Walking all pages runs against the real school manager on
SQLite, so the pages and the search they come from are tested together.
"""

import base64
import json
from collections.abc import AsyncGenerator, Sequence
from dataclasses import dataclass, field
from typing import Annotated, cast

import orjson
import pytest
from fastapi import Depends, FastAPI, HTTPException
from fastapi.testclient import TestClient
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool
from starlette.requests import Request
from ucsschool_objects import Filter, LoadSpec, Manager, Operator, School, SearchQuery, SortSpec
from ucsschool_objects.core.adapters.sqlalchemy import SQLAlchemySchoolManager
from ucsschool_objects.database_models import Base, School as SchoolModel

from ucsschool.kelvin.routers.v2._pagination import (
    LAST_PAGE,
    MAX_PAGE_SIZE,
    Cursor,
    PageItems,
    PageRequest,
    cut_page,
    link_header,
    page_request,
    page_response,
    page_url,
    search_page,
)
from ucsschool.kelvin.routers.v2._responses import ModelListResponse


@dataclass(frozen=True)
class Named:
    name: str


class Item(BaseModel):
    name: str


def _name(item: Named) -> str:
    return item.name


def _names(items: Sequence[Named]) -> list[str]:
    return [item.name for item in items]


def _fetched(*names: str) -> list[Named]:
    return [Named(name) for name in names]


def _after(name: str) -> Cursor:
    return Cursor(name=name, forward=True)


def _before(name: str) -> Cursor:
    return Cursor(name=name, forward=False)


def _token(data: object) -> str:
    return base64.urlsafe_b64encode(json.dumps(data).encode()).decode()


def _request(query_string: str) -> Request:
    return Request(
        {
            "type": "http",
            "scheme": "http",
            "server": ("kelvin.example.com", 80),
            "path": "/ucsschool/kelvin/v2/users/",
            "query_string": query_string.encode(),
            "headers": [],
        }
    )


@pytest.mark.parametrize(
    "cursor",
    [
        pytest.param(_after("DEMOSCHOOL-1a ä/+"), id="forward"),
        pytest.param(_before("DEMOSCHOOL-1a ä/+"), id="back"),
        pytest.param(LAST_PAGE, id="last-page"),
    ],
)
def test_cursor_survives_the_round_trip(cursor: Cursor) -> None:
    assert Cursor.decode(cursor.encode()) == cursor


def test_cursor_token_needs_no_quoting_in_a_url() -> None:
    token = Cursor(name="a" * 10, forward=True).encode()

    assert "=" not in token
    assert set(token) <= set("ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-_")


@pytest.mark.parametrize(
    "token",
    [
        pytest.param("not base64!", id="not-base64"),
        pytest.param(base64.urlsafe_b64encode(b"\xff\xfe").decode(), id="not-utf8"),
        pytest.param(base64.urlsafe_b64encode(b"not json").decode(), id="not-json"),
        pytest.param(_token(["after", "a"]), id="not-an-object"),
        pytest.param(_token({"v": 2, "after": "a"}), id="unknown-version"),
        pytest.param(_token({"after": "a"}), id="no-version"),
        pytest.param(_token({"v": 1, "after": 1}), id="name-not-a-string"),
        pytest.param(_token({"v": 1, "after": "a", "before": "b"}), id="both-directions"),
        pytest.param(_token({"v": 1}), id="no-position"),
        pytest.param(_token({"v": 1, "after": None}), id="forward-without-a-name"),
        pytest.param(_token({"v": 1, "after": "a\x00"}), id="nul-in-name-forward"),
        pytest.param(_token({"v": 1, "before": "a\x00"}), id="nul-in-name-back"),
        pytest.param(base64.urlsafe_b64encode(b"[" * 100_000).decode(), id="nested-too-deep"),
    ],
)
def test_a_cursor_kelvin_did_not_make_is_rejected(token: str) -> None:
    with pytest.raises(HTTPException) as exc_info:
        Cursor.decode(token)

    assert exc_info.value.status_code == 400


@pytest.mark.parametrize(
    ("limit", "cursor", "expected"),
    [
        pytest.param(None, None, None, id="without-limit-there-is-no-page"),
        pytest.param(
            10, None, PageRequest(size=10, cursor=None), id="limit-alone-asks-for-the-first-page"
        ),
        pytest.param(
            10,
            _before("anton"),
            PageRequest(size=10, cursor=_before("anton")),
            id="limit-and-cursor-ask-for-the-page-at-the-cursor",
        ),
    ],
)
def test_page_request_reads_limit_and_cursor(
    limit: int | None, cursor: Cursor | None, expected: PageRequest | None
) -> None:
    token = cursor.encode() if cursor else None

    assert page_request(limit=limit, cursor=token) == expected


def test_a_cursor_without_limit_is_rejected() -> None:
    cursor = _after("a").encode()

    with pytest.raises(HTTPException) as exc_info:
        page_request(limit=None, cursor=cursor)

    assert exc_info.value.status_code == 400


@pytest.mark.parametrize(
    ("cursor", "ascending", "search_after"),
    [
        pytest.param(None, True, None, id="first-page-forward-from-the-start"),
        pytest.param(_after("anton"), True, ("anton",), id="forward-from-the-cursor"),
        pytest.param(_before("zoe"), False, ("zoe",), id="back-from-the-cursor"),
        pytest.param(LAST_PAGE, False, None, id="last-page-back-from-the-end"),
    ],
)
def test_page_request_searches_from_the_cursor(
    cursor: Cursor | None, ascending: bool, search_after: tuple[str] | None
) -> None:
    page = PageRequest(size=10, cursor=cursor)

    assert page.sort_by == (SortSpec(field="name", ascending=ascending),)
    assert page.search_after == search_after
    assert page.fetch_limit == 11


@pytest.mark.parametrize(
    ("cursor", "fetched", "expected"),
    [
        pytest.param(
            None,
            _fetched("a", "b", "c"),
            PageItems(items=_fetched("a", "b"), next_cursor=_after("b"), previous_cursor=None),
            id="first-page-with-more-to-come-links-only-forward",
        ),
        pytest.param(
            None,
            _fetched("a", "b"),
            PageItems(items=_fetched("a", "b"), next_cursor=None, previous_cursor=None),
            id="a-single-page-links-nowhere",
        ),
        pytest.param(
            _after("b"),
            _fetched("c"),
            PageItems(items=_fetched("c"), next_cursor=None, previous_cursor=_before("c")),
            id="last-page-links-only-back",
        ),
        pytest.param(
            _before("e"),
            _fetched("d", "c", "b"),
            PageItems(items=_fetched("c", "d"), next_cursor=_after("d"), previous_cursor=_before("c")),
            id="paging-back-puts-the-page-in-ascending-order",
        ),
        pytest.param(
            _before("c"),
            _fetched("b", "a"),
            PageItems(items=_fetched("a", "b"), next_cursor=_after("b"), previous_cursor=None),
            id="paging-back-to-the-start-links-only-forward",
        ),
        pytest.param(
            LAST_PAGE,
            _fetched("e", "d", "c"),
            PageItems(items=_fetched("d", "e"), next_cursor=None, previous_cursor=_before("d")),
            id="the-last-page-links-only-back",
        ),
        pytest.param(
            LAST_PAGE,
            _fetched("b", "a"),
            PageItems(items=_fetched("a", "b"), next_cursor=None, previous_cursor=None),
            id="the-last-page-holding-everything-links-nowhere",
        ),
        pytest.param(
            _after("m"),
            [],
            PageItems(items=list[Named](), next_cursor=None, previous_cursor=None),
            id="an-empty-page-forward-links-nowhere",
        ),
        pytest.param(
            _before("m"),
            [],
            PageItems(items=list[Named](), next_cursor=None, previous_cursor=None),
            id="an-empty-page-back-links-nowhere",
        ),
    ],
)
def test_cut_page(cursor: Cursor | None, fetched: list[Named], expected: PageItems[Named]) -> None:
    found = cut_page(PageRequest(size=2, cursor=cursor), fetched, _name)

    assert found == expected


def test_page_url_keeps_every_filter_and_replaces_the_cursor() -> None:
    old = Cursor(name="a", forward=True).encode()
    new = Cursor(name="b", forward=True)
    request = _request(f"school=DEMOSCHOOL&name=x*&name=y&limit=2&cursor={old}")

    url = page_url(request, new)

    assert url == (
        "https://kelvin.example.com/ucsschool/kelvin/v2/users/"
        f"?school=DEMOSCHOOL&name=x%2A&name=y&limit=2&cursor={new.encode()}"
    )


def test_page_url_without_a_cursor_is_the_first_page() -> None:
    request = _request(f"school=DEMOSCHOOL&limit=2&cursor={_after('a').encode()}")

    assert page_url(request, None) == (
        "https://kelvin.example.com/ucsschool/kelvin/v2/users/?school=DEMOSCHOOL&limit=2"
    )


@pytest.mark.parametrize(
    ("next_cursor", "previous_cursor", "rels"),
    [
        pytest.param(_after("b"), _before("a"), ["first", "prev", "next", "last"], id="in-the-middle"),
        pytest.param(_after("b"), None, ["first", "next", "last"], id="first-page"),
        pytest.param(None, _before("a"), ["first", "prev", "last"], id="last-page"),
        pytest.param(None, None, ["first", "last"], id="single-page"),
    ],
)
def test_link_header_links_first_last_and_the_neighbours(
    next_cursor: Cursor | None, previous_cursor: Cursor | None, rels: list[str]
) -> None:
    request = _request("limit=2")
    urls = {
        "first": page_url(request, None),
        "prev": page_url(request, previous_cursor) if previous_cursor else "",
        "next": page_url(request, next_cursor) if next_cursor else "",
        "last": page_url(request, LAST_PAGE),
    }
    found = PageItems(items=_fetched("a", "b"), next_cursor=next_cursor, previous_cursor=previous_cursor)

    header = link_header(request, found)

    assert header == ", ".join(f'<{urls[rel]}>; rel="{rel}"' for rel in rels)


def test_page_response_is_the_plain_list_with_a_link_header() -> None:
    request = _request("limit=1")
    found = PageItems(items=[Named("a")], next_cursor=_after("a"), previous_cursor=None)

    response = page_response(request, found, [Item(name="a")])

    assert isinstance(response, ModelListResponse)
    assert orjson.loads(response.body) == [{"name": "a"}]
    assert response.headers["link"] == link_header(request, found)


@dataclass
class _RecordingManager:
    """Answers the n-th search with the n-th entry of ``found``."""

    found: list[list[Named]]
    calls: list[tuple[SearchQuery | None, dict[str, object]]] = field(default_factory=list)

    async def search(self, query: SearchQuery | None = None, **kwargs: object) -> list[Named]:
        self.calls.append((query, kwargs))
        return self.found[len(self.calls) - 1]

    def as_manager(self) -> Manager[Named]:
        return cast("Manager[Named]", cast(object, self))


async def test_search_page_asks_the_manager_for_one_beyond_the_page() -> None:
    manager = _RecordingManager(found=[_fetched("b", "c", "d")])
    page = PageRequest(size=2, cursor=Cursor(name="a", forward=True))
    query = SearchQuery(where=Filter(field="name", op=Operator.MATCHES, value="*"))
    load = LoadSpec.from_attributes("name")

    found = await search_page(manager.as_manager(), query, page, _name, load=load)

    assert manager.calls == [
        (
            query,
            {
                "sort_by": page.sort_by,
                "search_after": ("a",),
                "limit": 3,
                "load": load,
            },
        )
    ]
    assert _names(found.items) == ["b", "c"]


@pytest.mark.parametrize(
    ("cursor", "fetched", "items"),
    [
        pytest.param(
            _before("d"), _fetched("b", "a"), ["a", "b"], id="back-to-a-full-page-at-the-start"
        ),
        pytest.param(_before("d"), _fetched("c", "b", "a"), ["b", "c"], id="back-with-more-before"),
        pytest.param(_before("b"), _fetched("a"), ["a"], id="back-to-a-short-page-at-the-start"),
        pytest.param(_before("c"), [], [], id="back-to-an-emptied-start"),
        pytest.param(_after("b"), _fetched("c"), ["c"], id="forward-to-a-short-last-page"),
        pytest.param(LAST_PAGE, _fetched("a"), ["a"], id="a-short-last-page-is-everything"),
    ],
)
async def test_search_page_searches_once(cursor: Cursor, fetched: list[Named], items: list[str]) -> None:
    manager = _RecordingManager(found=[fetched])
    page = PageRequest(size=2, cursor=cursor)

    found = await search_page(manager.as_manager(), None, page, _name)

    assert len(manager.calls) == 1
    assert _names(found.items) == items


@pytest.fixture
async def db_session() -> AsyncGenerator[AsyncSession, None]:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", poolclass=StaticPool)
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    async with async_sessionmaker(bind=engine, expire_on_commit=False)() as session:
        yield session
    await engine.dispose()


async def _walk(
    manager: Manager[School], size: int, start: Cursor | None, forward: bool, total: int
) -> list[list[str]]:
    """The pages from ``start`` on, following ``next`` or ``prev`` until there is none."""
    pages: list[list[str]] = []
    cursor = start
    while True:
        page = PageRequest(size=size, cursor=cursor)
        found = await search_page(manager, None, page, lambda school: school.name)
        pages.append([school.name for school in found.items])
        cursor = found.next_cursor if forward else found.previous_cursor
        if cursor is None:
            return pages
        assert len(pages) <= total, "the pages don't end"


@pytest.mark.parametrize("size", [1, 2, 3, 5])
@pytest.mark.parametrize("total", [0, 1, 2, 3, 4, 5, 6, 7, 10])
async def test_every_object_is_paged_exactly_once_in_both_directions(
    db_session: AsyncSession, total: int, size: int
) -> None:
    names = [f"school{i:02}" for i in range(total)]
    db_session.add_all(
        SchoolModel(name=name, record_uid=name, source_uid="pagination") for name in reversed(names)
    )
    await db_session.flush()
    manager = SQLAlchemySchoolManager(db_session)

    forward = await _walk(manager, size, None, forward=True, total=total)
    back = await _walk(manager, size, LAST_PAGE, forward=False, total=total)

    assert [name for page in forward for name in page] == names
    assert [name for page in reversed(back) for name in page] == names
    assert all(len(page) == size for page in forward[:-1])
    assert all(len(page) == size for page in back[:-1])


def _endpoint(page: Annotated[PageRequest | None, Depends(page_request)]) -> dict[str, int | None]:
    return {"size": page.size if page else None}


def _app() -> FastAPI:
    app = FastAPI()
    _ = app.get("/")(_endpoint)
    return app


@pytest.mark.parametrize("limit", [0, MAX_PAGE_SIZE + 1])
def test_limit_out_of_range_is_rejected(limit: int) -> None:
    response = TestClient(_app()).get("/", params={"limit": limit})

    assert response.status_code == 422


@pytest.mark.parametrize("limit", [1, MAX_PAGE_SIZE])
def test_limit_is_read_from_the_query_string(limit: int) -> None:
    response = TestClient(_app()).get("/", params={"limit": limit})

    assert response.json() == {"size": limit}
