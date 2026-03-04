# ADR: Dual API Version Routing for Kelvin REST API (v1 + v2)

## Status

**Proposed** (Decision: **Option 2**)

## Context

The Kelvin REST API currently exposes endpoints under `/v1/`. For the KelvinV2 roadmap (notably migrating read access operations to SQL), we need to expose **the same functional API under `/v2/`** as an interim step. Both versions must coexist in the same container and initially behave identically for consumers.

Nuance: **`/v2` will not support PyHook when reading/searching objects**, while remaining otherwise identical at this stage.

Docs endpoints currently exist under `/v1` as well (Swagger UI, ReDoc, OpenAPI JSON, changelog, …). We must decide whether to keep docs versioned, duplicate them, or move “generic” docs to `/`.

## Decision drivers

* **Backward compatibility:** `/v1` must remain unchanged and stable.
* **Controlled divergence:** `/v2` will diverge soon (SQL read-path, hook behavior) without contaminating v1.
* **Maintainability:** avoid scattered “if v2” logic across handlers and service code.
* **Documentation correctness:** avoid confusing or misleading OpenAPI schemas and docs as soon as v2 differs.
* **Testability:** must verify v1/v2 identical behavior where intended and explicitly test intended differences.
* **Operational simplicity:** both versions served from one container.

---

## Considered options

# Option 1 — Dual include_router: include the same routers twice under `/v1` and `/v2`

## Description

Single FastAPI app; the same router modules are included twice via two wrapper routers (or directly with different prefixes). This keeps code paths shared and keeps changes minimal.

## Code snippet (core routing)

```python
from fastapi import FastAPI, APIRouter
from .routers import users, groups  # exports `router` with paths like "/users"

app = FastAPI(title="Kelvin API")

v1 = APIRouter(prefix="/v1")
v2 = APIRouter(prefix="/v2")

v1.include_router(users.router, tags=["users"])
v1.include_router(groups.router, tags=["groups"])

v2.include_router(users.router, tags=["users"])
v2.include_router(groups.router, tags=["groups"])

app.include_router(v1)
app.include_router(v2)
```

## Code snippet (important: avoid OpenAPI operationId collisions)

Registering the same endpoints twice often causes duplicate `operationId`s and breaks client generation unless you namespace them.

```python
from typing import Any

def make_unique_id_function(version: str):
    def _unique_id(route: Any) -> str:
        methods = "_".join(sorted(getattr(route, "methods", []) or []))
        name = getattr(route, "name", None) or route.path_format.replace("/", "_").strip("_")
        return f"{version}_{name}_{methods}".lower()
    return _unique_id

app = FastAPI(
    title="Kelvin API",
    generate_unique_id_function=make_unique_id_function("root"),
)
```

> Note: In Option 1, you still must ensure uniqueness between v1 and v2 endpoints. In practice this often requires explicit `name=` per route or a unique-id function that incorporates the router prefix.

## Code snippet (v2 “no PyHook reads/search” via capabilities)

A pragmatic pattern is to derive “capabilities” from the request and enforce policy centrally (ideally in the service layer / pipeline entrypoint).

```python
from dataclasses import dataclass
from fastapi import Request, Depends

@dataclass(frozen=True)
class ApiCapabilities:
    allow_read_pyhook: bool

def capabilities(request: Request) -> ApiCapabilities:
    is_v2 = request.url.path.startswith("/v2/")
    return ApiCapabilities(allow_read_pyhook=not is_v2)

def run_read_pyhook_if_enabled(caps: ApiCapabilities, *args, **kwargs) -> None:
    if not caps.allow_read_pyhook:
        return
    # run hook...

# In a read/search pipeline entrypoint:
def read_users(..., caps: ApiCapabilities = Depends(capabilities)):
    run_read_pyhook_if_enabled(caps, ...)
    ...
```

## Pros

* **Minimal diff / fastest path** to expose `/v2`.
* **Single lifecycle** and shared middleware/dependency configuration.
* Easy to parametrize tests over `/v1` and `/v2`.

## Cons / risks

* **OpenAPI/doc complexity:** by default you get one combined schema with both versions; divergence becomes confusing without custom OpenAPI work.
* **Version branching tends to spread:** capabilities are useful, but as divergence increases, more layers gain `if v2` conditionals.
* Hard to cleanly diverge middleware/exception handling per version without path sniffing.
* Higher risk of accidental v1 regressions during v2 migrations because the app composition remains tightly shared.

---

# Option 2 — Mounted sub-app: mount a dedicated FastAPI sub-application under `/v2`

## Description

Root app mounts a separate `v2_app` at `/v2` (and optionally a `v1_app` at `/v1` for symmetry). Both apps can reuse the same router modules/handlers but maintain separate configuration (OpenAPI, docs, middleware, exception handlers, dependencies).

## Code snippet (app factory + mount)

```python
from __future__ import annotations

from contextlib import asynccontextmanager
from typing import Any, Callable, Literal

from fastapi import FastAPI
from .routers import users, groups


def make_unique_id_function(version: str) -> Callable[[Any], str]:
    def _unique_id(route: Any) -> str:
        methods = "_".join(sorted(getattr(route, "methods", []) or []))
        name = getattr(route, "name", None) or route.path_format.replace("/", "_").strip("_")
        return f"{version}_{name}_{methods}".lower()
    return _unique_id


class Capabilities:
    def __init__(self, *, allow_read_pyhook: bool):
        self.allow_read_pyhook = allow_read_pyhook


def capabilities_for(version: Literal["v1", "v2"]) -> Capabilities:
    # Central policy: v2 disables PyHook for read/search.
    return Capabilities(allow_read_pyhook=(version == "v1"))


def setup_common(app: FastAPI) -> None:
    # add middleware, exception handlers, logging, etc.
    pass


def create_api_app(version: Literal["v1", "v2"]) -> FastAPI:
    app = FastAPI(
        title=f"Kelvin API {version}",
        version=version,
        docs_url="/docs",
        redoc_url="/redoc",
        openapi_url="/openapi.json",
        generate_unique_id_function=make_unique_id_function(version),
    )
    setup_common(app)

    app.state.capabilities = capabilities_for(version)

    # reuse the same routers/handlers
    app.include_router(users.router, tags=["users"])
    app.include_router(groups.router, tags=["groups"])
    return app


@asynccontextmanager
async def lifespan(root: FastAPI):
    # init shared resources once (db engine, cache clients, etc.)
    # root.state.engine = ...
    yield
    # close resources


def create_root_app() -> FastAPI:
    root = FastAPI(title="Kelvin API", lifespan=lifespan)
    setup_common(root)

    root.mount("/v1", create_api_app("v1"))
    root.mount("/v2", create_api_app("v2"))
    return root


app = create_root_app()
```

## Code snippet (use v2 capability in a shared router)

```python
from fastapi import APIRouter, Request, Depends

router = APIRouter()

def get_caps(request: Request):
    return request.app.state.capabilities

@router.get("/users", name="list_users")
def list_users(caps=Depends(get_caps)):
    return {"allow_read_pyhook": caps.allow_read_pyhook, "items": []}
```

## Docs outcome (clean by default)

* `/v1/docs`, `/v1/openapi.json`, `/v1/redoc`
* `/v2/docs`, `/v2/openapi.json`, `/v2/redoc`

## Pros

* **Real separation boundary:** v2 can diverge without contaminating v1.
* **Separate schemas/docs** stay accurate as soon as v2 differs.
* **Less incentive for scattered branching:** differences can be expressed by app composition (wiring), not path sniffing.
* Supports v2 SQL migration cleanly (swap the v2 read/search pipeline without touching v1).

## Cons / costs

* More structure/boilerplate (factory + mount).
* Must ensure shared resources are initialized once (root lifespan).
* Tests with dependency overrides must target the correct app (root vs mounted sub-app).

---

## Knowledge gains / updated analysis from discussion

### “Can’t Option 1 disadvantages be handled by rules?”

We discussed a governance approach for Option 1:

1. **Use capabilities as long as possible** to express differences (feature flags such as “no PyHook reads/search”).
2. **If capabilities can’t cover required changes, add v2-specific routers/handlers**.

This approach is workable and can mitigate Option 1 initially. However, key observations:

* **Capabilities tend to become leaky as divergence grows.** Once differences include cross-cutting behavior (middleware, error mapping, pagination semantics, response models, auth rules, caching), capabilities often spread into multiple layers and create many `if v2` branches.
* **Introducing v2-specific routers inside one app effectively recreates Option 2’s separation by convention**, but without the framework-enforced boundaries (separate app objects, separate OpenAPI schemas, separate middleware graphs). Over time this becomes a maintenance burden and a source of accidental coupling.
* **OpenAPI/doc separation remains a recurring pain point in Option 1.** Even if operationId collisions are fixed, a single combined schema becomes confusing once v2 diverges, unless you invest in non-trivial custom OpenAPI generation.

Conclusion of the knowledge gain: **Option 1 + rules can work for shallow divergence**, but if v2 is expected to diverge materially (as in KelvinV2 SQL read path), Option 2’s composition boundary remains cheaper and safer long-term.

---

## Decision

**Choose Option 2 (Mounted `/v2` sub-app).**

### Rationale

* v2 is expected to diverge soon (SQL read-path) and already diverges by policy (“no PyHook read/search”).
* Option 2 minimizes long-term “if v2” branching and supports clean separation of docs/OpenAPI.
* The “Option 1 + capabilities + v2-only routers” strategy tends to drift toward Option 2 anyway, but with weaker boundaries.

---

## Consequences

### Positive

* v1 remains stable while v2 evolves with low coupling.
* Separate docs/schemas reduce consumer confusion.
* Cleaner incremental migration to SQL reads for v2.

### Negative / mitigations

* Extra setup → mitigate with shared `create_api_app(version)` factory and `setup_common()`.
* Shared resources lifecycle complexity → mitigate with root lifespan and shared `root.state.*` objects.
* Tests/dependency overrides complexity → standardize test helpers that can override dependencies on both mounted apps if needed.

---

## Testing strategy

1. Parametrize endpoint tests over `base = "/v1"` and `"/v2"` for endpoints expected to be identical.
2. Add equivalence integration tests: same request against v1/v2 ⇒ identical response payloads (status + JSON).
3. Add v2-specific tests verifying **no PyHook** for read/search (spy/mock side effects).

---

## Documentation decision

Keep docs versioned:

* `/v1/docs`, `/v1/redoc`, `/v1/openapi.json`
* `/v2/docs`, `/v2/redoc`, `/v2/openapi.json`

Optionally later add root `/docs` redirect to `/v2/docs` once v2 becomes preferred, while keeping `/v1/docs` available for legacy consumers.
