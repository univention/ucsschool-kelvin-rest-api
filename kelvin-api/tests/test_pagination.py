# SPDX-FileCopyrightText: 2026 Univention GmbH
# SPDX-License-Identifier: AGPL-3.0-only

"""Unit tests for the keyset pagination of the v2 collection endpoints.

The search itself is the ``search_after`` of ``ucsschool-objects`` and tested
there. What is tested here is the part Kelvin adds: the cursor, the request
parameters, cutting what was fetched into a page, and the links to its
neighbours.
"""

import base64
import json
from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Annotated, cast

import orjson
import pytest
from fastapi import Depends, FastAPI, HTTPException
from fastapi.testclient import TestClient
from pydantic import BaseModel
from starlette.requests import Request
from ucsschool_objects import Filter, LoadSpec, Manager, Operator, SearchQuery, SortSpec

from ucsschool.kelvin.routers.v2._pagination import (
    MAX_PAGE_SIZE,
    Cursor,
    ModelPageResponse,
    PageItems,
    PageRequest,
    cut_page,
    page_request,
    page_response,
    page_url,
    search_page,
)


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


@pytest.mark.parametrize("forward", [True, False])
def test_cursor_survives_the_round_trip(forward: bool) -> None:
    cursor = Cursor(name="DEMOSCHOOL-1a ä/+", forward=forward)

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
    ],
)
def test_a_cursor_kelvin_did_not_make_is_rejected(token: str) -> None:
    with pytest.raises(HTTPException) as exc_info:
        Cursor.decode(token)

    assert exc_info.value.status_code == 400


def test_without_limit_there_is_no_page() -> None:
    assert page_request(limit=None, cursor=None) is None


def test_a_cursor_without_limit_is_rejected() -> None:
    cursor = Cursor(name="a", forward=True).encode()

    with pytest.raises(HTTPException) as exc_info:
        page_request(limit=None, cursor=cursor)

    assert exc_info.value.status_code == 400


def test_limit_alone_asks_for_the_first_page() -> None:
    assert page_request(limit=10, cursor=None) == PageRequest(size=10, cursor=None)


def test_limit_and_cursor_ask_for_the_page_at_the_cursor() -> None:
    cursor = Cursor(name="anton", forward=False)

    assert page_request(limit=10, cursor=cursor.encode()) == PageRequest(size=10, cursor=cursor)


def test_the_first_page_searches_forward_from_the_start() -> None:
    page = PageRequest(size=10, cursor=None)

    assert page.sort_by == (SortSpec(field="name", ascending=True),)
    assert page.search_after is None
    assert page.fetch_limit == 11


def test_paging_back_searches_backward_from_the_cursor() -> None:
    page = PageRequest(size=10, cursor=Cursor(name="zoe", forward=False))

    assert page.sort_by == (SortSpec(field="name", ascending=False),)
    assert page.search_after == ("zoe",)


def test_first_page_with_more_to_come_links_only_forward() -> None:
    found = cut_page(PageRequest(size=2, cursor=None), _fetched("a", "b", "c"), _name)

    assert _names(found.items) == ["a", "b"]
    assert found.next_cursor == Cursor(name="b", forward=True)
    assert found.previous_cursor is None


def test_a_single_page_links_nowhere() -> None:
    found = cut_page(PageRequest(size=2, cursor=None), _fetched("a", "b"), _name)

    assert _names(found.items) == ["a", "b"]
    assert found.next_cursor is None
    assert found.previous_cursor is None


def test_last_page_links_only_back() -> None:
    page = PageRequest(size=2, cursor=Cursor(name="b", forward=True))

    found = cut_page(page, _fetched("c"), _name)

    assert _names(found.items) == ["c"]
    assert found.next_cursor is None
    assert found.previous_cursor == Cursor(name="c", forward=False)


def test_paging_back_puts_the_page_in_ascending_order() -> None:
    page = PageRequest(size=2, cursor=Cursor(name="e", forward=False))

    found = cut_page(page, _fetched("d", "c", "b"), _name)

    assert _names(found.items) == ["c", "d"]
    assert found.next_cursor == Cursor(name="d", forward=True)
    assert found.previous_cursor == Cursor(name="c", forward=False)


def test_paging_back_to_the_start_links_only_forward() -> None:
    page = PageRequest(size=2, cursor=Cursor(name="c", forward=False))

    found = cut_page(page, _fetched("b", "a"), _name)

    assert _names(found.items) == ["a", "b"]
    assert found.next_cursor == Cursor(name="b", forward=True)
    assert found.previous_cursor is None


@pytest.mark.parametrize("forward", [True, False])
def test_an_empty_page_links_nowhere(forward: bool) -> None:
    page = PageRequest(size=2, cursor=Cursor(name="m", forward=forward))

    found = cut_page(page, list[Named](), _name)

    assert found == PageItems(items=[], next_cursor=None, previous_cursor=None)


def test_page_url_keeps_every_filter_and_replaces_the_cursor() -> None:
    old = Cursor(name="a", forward=True).encode()
    new = Cursor(name="b", forward=True)
    request = _request(f"school=DEMOSCHOOL&name=x*&name=y&limit=2&cursor={old}")

    url = page_url(request, new)

    assert url == (
        "https://kelvin.example.com/ucsschool/kelvin/v2/users/"
        f"?school=DEMOSCHOOL&name=x%2A&name=y&limit=2&cursor={new.encode()}"
    )


def test_page_url_without_a_cursor_is_none() -> None:
    assert page_url(_request("limit=2"), None) is None


def test_page_response_serialises_the_page() -> None:
    found = PageItems(
        items=[Named("a")],
        next_cursor=Cursor(name="a", forward=True),
        previous_cursor=None,
    )

    response = page_response(_request("limit=1"), found, [Item(name="a")])

    assert isinstance(response, ModelPageResponse)
    assert orjson.loads(response.body) == {
        "results": [{"name": "a"}],
        "next_page_url": page_url(_request("limit=1"), found.next_cursor),
        "previous_page_url": None,
    }


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


async def test_paging_back_to_a_short_start_answers_with_the_first_page() -> None:
    """``bb`` was created after the client left ``[a, b]``: going back from ``[b, bb]``
    finds only ``[a]`` before it, and answers with ``[a, b]`` instead."""
    manager = _RecordingManager(found=[_fetched("a"), _fetched("a", "b", "bb")])
    page = PageRequest(size=2, cursor=Cursor(name="b", forward=False))
    query = SearchQuery(where=Filter(field="name", op=Operator.MATCHES, value="*"))
    load = LoadSpec.from_attributes("name")

    found = await search_page(manager.as_manager(), query, page, _name, load=load)

    assert [call[1]["search_after"] for call in manager.calls] == [("b",), None]
    assert manager.calls[1] == (
        query,
        {
            "sort_by": (SortSpec(field="name", ascending=True),),
            "search_after": None,
            "limit": 3,
            "load": load,
        },
    )
    assert found == PageItems(
        items=_fetched("a", "b"),
        next_cursor=Cursor(name="b", forward=True),
        previous_cursor=None,
    )


async def test_paging_back_to_an_emptied_start_answers_with_the_first_page() -> None:
    manager = _RecordingManager(found=[[], _fetched("c", "d")])
    page = PageRequest(size=2, cursor=Cursor(name="c", forward=False))

    found = await search_page(manager.as_manager(), None, page, _name)

    assert _names(found.items) == ["c", "d"]
    assert found.previous_cursor is None


@pytest.mark.parametrize(
    "fetched",
    [
        pytest.param(_fetched("b", "a"), id="full-page-at-the-start"),
        pytest.param(_fetched("c", "b", "a"), id="more-before"),
    ],
)
async def test_paging_back_to_a_full_page_searches_once(fetched: list[Named]) -> None:
    manager = _RecordingManager(found=[fetched])
    page = PageRequest(size=2, cursor=Cursor(name="d", forward=False))

    found = await search_page(manager.as_manager(), None, page, _name)

    assert len(manager.calls) == 1
    assert len(found.items) == 2


async def test_a_short_last_page_going_forward_searches_once() -> None:
    manager = _RecordingManager(found=[_fetched("c")])
    page = PageRequest(size=2, cursor=Cursor(name="b", forward=True))

    found = await search_page(manager.as_manager(), None, page, _name)

    assert len(manager.calls) == 1
    assert _names(found.items) == ["c"]


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


def test_limit_is_read_from_the_query_string() -> None:
    response = TestClient(_app()).get("/", params={"limit": MAX_PAGE_SIZE})

    assert response.json() == {"size": MAX_PAGE_SIZE}
