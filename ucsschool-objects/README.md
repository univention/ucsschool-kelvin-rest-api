# ucsschool-objects

[[_TOC_]]

## Summary

This is an internal library for querying and manipulating UCS@school objects.

The library provides plain-Python domain models,
an async API for querying and mutating them,
and SQL-backed persistence.

The domain layer covering UCS@school core objects (School, Group, Role, User, SchoolMembership)
is persistence-agnostic.

This is a major departure from the `ucs-school-lib` architecture.
The legacy library relies on inheritance-heavy models tightly coupled to UDM/LDAP.
This package stores objects in a SQL database (PostgreSQL in production, SQLite in tests)
— no UDM, no LDAP, no FastAPI dependencies.
It is a v2 rewrite structured as a ports-and-adapters stack.

The test suite requires 100% coverage.

## Setup

Install the project and its dependencies (including development dependencies):

```shell
uv sync
```

For production use, configure the database connection via environment variables
before running any code that accesses the database:

| Variable | Description | Default |
|---|---|---|
| `UCSSCHOOL_KELVIN_DB_URI` | PostgreSQL connection URI (`postgresql://host/dbname`) | — (required) |
| `UCSSCHOOL_KELVIN_DB_USERNAME` | Database username | — |
| `UCSSCHOOL_KELVIN_DB_PASSWORDFILE` | Path to a file containing the database password | `/etc/ucsschool/kelvin/postgresql-kelvin.secret` |

## Usage

All database operations are `async`.
At application startup, create a shared engine
and a Kelvin storage session factory;
then, for each operation, open a session through the factory
and call methods on the managers exposed by the `storage` object
(`storage.schools`, `storage.roles`, `storage.groups`, `storage.users`).

### Where to import from

Clients of this library import from exactly two places:

1. **`ucsschool_objects`** — the public API.
   Domain entities, the query DSL, exceptions, the `Manager[T]` port,
   and the storage-session protocols all come from here.
   Use this for everyday code.
2. **`ucsschool_objects.core.adapters.<backend>`** — the adapter package, **for wiring only**.
   Currently, the only backend is `sqlalchemy`,
   so wiring code imports from `ucsschool_objects.core.adapters.sqlalchemy`.
   This is where the concrete manager classes and the engine/session-factory builders live.

Do not reach into deeper paths (`...adapters.sqlalchemy.session`, `...managers.user_manager`, …)
or into `ucsschool_objects.database_models`.
Those modules are internal and may change without notice.

### Wire up the storage session factory

When using PostgreSQL:

```python
from sqlalchemy import make_url
from ucsschool_objects.core.adapters.sqlalchemy import (
    DatabaseSettings,
    build_engine,
    build_kelvin_storage_session_factory,
)

settings = DatabaseSettings(url=make_url("postgresql+psycopg://kelvin:secret@localhost/kelvin"))
engine = build_engine(settings)
storage_factory = build_kelvin_storage_session_factory(engine)
```

If you're using SQLite during development,
build the engine directly and then wrap it the same way:

```python
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.pool import StaticPool
from ucsschool_objects.core.adapters.sqlalchemy import build_kelvin_storage_session_factory

engine = create_async_engine("sqlite+aiosqlite:///:memory:", poolclass=StaticPool)
storage_factory = build_kelvin_storage_session_factory(engine)
```

Dispose the engine on shutdown:

```python
await engine.dispose()
```

### Type-annotating a manager

Use the `Manager` port from the public API when annotating variables or function parameters.
This keeps call-site code decoupled from the concrete SQLAlchemy implementation:

```python
from ucsschool_objects import Manager, School

def do_something(manager: Manager[School]) -> None:
    ...
```

The concrete classes (`SQLAlchemySchoolManager`, …) are only needed at the wiring point.
Through `storage.schools`, `storage.roles`, `storage.groups`, and `storage.users`,
callers see them as `Manager[T]`.

### Choosing between `session_scope` and `transaction_scope`

Both context managers hand you a `storage` object that exposes the four managers.
The difference is whether a database transaction is opened automatically.

**`transaction_scope`** — use for any write (create / modify / delete).
It wraps the session in a transaction that commits when the block exits cleanly
and rolls back automatically on any exception.
All operations inside the block are atomic:
either all succeed together or none are persisted.

**`session_scope`** — use for read-only queries.
No transaction is started automatically,
so the database does not acquire write locks.
Use it when you only call `get` or `search`.

```
read-only query           →  session_scope
create / modify / delete  →  transaction_scope
mix of reads and writes   →  transaction_scope  (rollback covers everything)
```

### Fetch a school by public ID

```python
import uuid
from ucsschool_objects import NotFound

async def get_school(school_id: uuid.UUID):
    async with storage_factory.session_scope() as storage:
        try:
            return await storage.schools.get(school_id)
        except NotFound:
            return None
```

### Search schools by name

```python
from ucsschool_objects import Filter, Operator, SearchQuery, SortSpec

async def find_schools(name_prefix: str):
    async with storage_factory.session_scope() as storage:
        query = SearchQuery(
            where=Filter(field="name", op=Operator.LIKE, value=f"{name_prefix}%")
        )
        return list(
            await storage.schools.search(query, sort_by=[SortSpec(field="name")])
        )
```

### Get a user with school memberships loaded

Relationships are returned as `UNLOADED` by default.
Use `LoadSpec` to request eager loading:

```python
import uuid
from ucsschool_objects import LoadSpec

async def get_user_with_memberships(user_id: uuid.UUID):
    async with storage_factory.session_scope() as storage:
        user = await storage.users.get(
            user_id,
            load=LoadSpec.from_attributes("school_memberships"),
        )
    for membership in user.school_memberships.values():
        print(membership.school.name, "primary:", membership.is_primary)
```

### Search users who belong to a specific school

Filter on nested fields using dot-paths:

```python
from ucsschool_objects import Filter, Operator, SearchQuery

async def users_in_school(school_name: str):
    async with storage_factory.session_scope() as storage:
        query = SearchQuery(
            where=Filter(field="schools.name", op=Operator.EQ, value=school_name)
        )
        return list(await storage.users.search(query))
```

### Create a new school object

```python
from ucsschool_objects import School

async def create_school():
    new_school = School(
        record_uid="NEWSCHOOL",
        source_uid="default",
        name="NEWSCHOOL",
        display_name={"de": "Neue Schule", "en": "New School"},
        educational_servers={"edu.example.com"},
        administrative_servers=set(),
    )
    async with storage_factory.transaction_scope() as storage:
        await storage.schools.create(new_school)
```

### Delete a school class

```python
import uuid

async def delete_school_class(group_id: uuid.UUID):
    async with storage_factory.transaction_scope() as storage:
        await storage.groups.delete(group_id)
```

### Create a teacher atomically

The following example creates a role and a user inside a single transaction.
If either `create` call raises, the whole block rolls back
and neither object is persisted.

`Role` is read-only after construction and `create()` does not write the generated identifier
back onto the input object,
so the caller assigns `public_id` up front
and reuses the same value when constructing the membership.
The same pattern applies whenever a freshly-built object's identifier is needed
later in the same transaction.

```python
import uuid
from ucsschool_objects import Role, School, SchoolMembership, User

async def create_teacher(school: School) -> None:
    role = Role(
        public_id=uuid.uuid4(),
        name="teacher",
        display_name={"de": "Lehrkraft", "en": "Teacher"},
    )
    membership = SchoolMembership(
        school=school,
        is_primary=True,
        roles={role},
        groups=set(),
    )
    user = User(
        record_uid="a_teacher",
        source_uid="default",
        name="a_teacher",
        firstname="Anne",
        lastname="Teacher",
        active=True,
        school_memberships={school.public_id: membership},
        legal_wards=set(),
        legal_guardians=set(),
    )
    async with storage_factory.transaction_scope() as storage:
        await storage.roles.create(role)
        await storage.users.create(user)
```

## Architecture

The package follows the **ports-and-adapters** (hexagonal) pattern.
The domain layer defines *what* the library does through pure types and abstract contracts.
Adapters plug in a concrete backend that provides *how*.
Dependencies point inward only: adapters know about the domain, never the reverse.

```text
            ┌──────────────────────────────────────────────┐
            │                  caller                      │
            │  (e.g. Kelvin REST API, tests, scripts)      │
            └───────────────────┬──────────────────────────┘
                                │ imports public API
                                ▼
            ┌──────────────────────────────────────────────┐
            │  ucsschool_objects  (public re-export)       │
            └───────────────────┬──────────────────────────┘
                                │
          ┌─────────────────────┴─────────────────────┐
          ▼                                           ▼
  ┌───────────────────┐   implements     ┌────────────────────────┐
  │ core.domain.ports │ ◄──────────────  │core.adapters.sqlalchemy│
  │  (Manager[T]      │                  │  (SQLAlchemy*Manager,  │
  │   Protocol)       │                  │   query_filter,        │
  └─────────┬─────────┘                  │   mapping, session)    │
            │ references                 └──────────┬─────────────┘
            ▼                                       │
  ┌───────────────────┐                             │ reads / writes
  │   core.domain     │                             ▼
  │  (models, query,  │                  ┌────────────────────────┐
  │   load_spec,      │                  │   database_models      │
  │   errors,         │                  │  (SQLAlchemy ORM       │
  │   validators)     │                  │   — internal)          │
  └───────────────────┘                  └──────────┬─────────────┘
                                                    ▼
                                            PostgreSQL / SQLite
```

### Layers

| Layer | Location | May depend on | Must not depend on |
|---|---|---|---|
| Public API | `ucsschool_objects/__init__.py` | `core.domain` | adapters, `database_models` |
| Domain | `core.domain` (models, query DSL, load spec, errors, validators) | stdlib only | adapters, `database_models`, frameworks |
| Ports | `core.domain.ports` | domain types | anything concrete |
| Adapters | `core.adapters.<backend>` | domain, `database_models`, backend libs | sibling backends, public re-export |
| ORM | `database_models.py` | `sqlalchemy` | domain, adapters, public re-export |

### Domain — `core.domain`

Pure, persistence-agnostic business types.
No framework or persistence imports; stdlib only.

- **`models.py`** — plain classes for `School`, `Role`, `Group`, `SchoolMembership`, and `User`.
  Fields are stored privately (`_name`) behind public properties whose getters raise
  when the value was not loaded.
  Each model declares `__serialize_fields__`; `get_properties()` and
  `domain_object_properties()` derive the public field names from it.
  Only `Role` is read-only (properties without setters);
  the others have setters because adapters mutate their fields
  (e.g. populating `set`/`dict` relationship fields after construction).
  Equality and hashing are by `public_id` only.
  Partially-loaded objects are represented with an explicit `UNLOADED` sentinel rather than `None`,
  so "not fetched" is distinguishable from "actually null".
- **`query.py`** — a small expression tree (`Filter`, `And`, `Or`, `Not`, `SortSpec`, `SearchQuery`)
  and an `Operator` enum (`eq`, `ne`, `in`, `like`, `gt`/`gte`/`lt`/`lte`).
  Adapters translate this AST into their backend's query language.
- **`load_spec.py`** — `LoadSpec` controls which fields and relationships
  an adapter eagerly loads, GraphQL-style.
  Relationships default to "unloaded" and must be explicitly requested.
- **`errors.py`** — domain exception hierarchy rooted at `CorelibError`
  (`NotFound`, `InvalidFilter`, `UnsupportedFilterField`, …).
  Raised by adapters, caught by callers.
- **`validators.py`** — domain-level invariant checks for the domain models.

### Ports — `core.domain.ports`

The abstract contract between callers and adapters, defined as `typing.Protocol`s
so adapters satisfy them structurally (no inheritance required).

- **`Manager[ManagerT]`** is the single port.
  Every domain object type gets its own manager parameterised on that type.
  Methods:
  - `async get(public_id, *, load=None) -> ManagerT`
  - `async search(query=None, *, sort_by=(), limit=50, offset=0, load=None) -> Iterable[ManagerT]`
  - `async create(data) -> None`
  - `async modify(public_id, operations) -> None`
  - `async delete(public_id) -> None`

`modify` takes a sequence of JSONPath-style operations
(`{"op": "add|replace|set|append|merge", "path": ..., "value": ...}`
or `{"op": "remove", "path": ...}`)
rather than a full replacement object,
so callers express partial updates precisely.

### Adapters — `core.adapters.<backend>`

Concrete implementations of the port.
A caller wires up whichever adapter it wants at startup
and hands the resulting `Manager` instance around through the domain-typed port.

Today the only backend is **`core.adapters.sqlalchemy`**:

- **`managers/{school,role,group,user}_manager.py`** — one `SQLAlchemy*Manager(Manager[DomainType])`
  per domain object.
  Each manager declares a `_FIELD_MAP` and an optional `_NESTED_FIELD_REGISTRY` of `JoinSpec`s
  so query/sort fields map to ORM columns (including dot-paths like `"groups.name"`).
- **`query_filter.py`** — translates the domain `SearchQuery` AST into SQLAlchemy `Select` expressions,
  applies sort specs,
  and raises the domain's `InvalidFilter*` exceptions on unsupported fields or operators.
- **`mappers/to_domain.py`** and **`mappers/to_orm.py`** — project ORM rows to domain objects
  and the reverse direction for writes,
  preserving the `UNLOADED` sentinel for relationships that were not eagerly loaded
  (ORM relationships default to `lazy="raise"` to catch unintended fetches).
- **`session.py`** — `build_engine`, `build_session_factory`, and `build_kelvin_storage_session_factory`.
  The returned `KelvinSqlAlchemySessionFactory` exposes `transaction_scope()` and `session_scope()` methods
  that hand callers a `KelvinStorageSession` context manager.
  Connection details come from environment variables and a password file.

Future backends (e.g. LDAP, in-memory) would live as siblings under `core.adapters.<name>`
and must not cross-import the SQLAlchemy backend.

### ORM — `database_models.py`

Internal SQLAlchemy ORM.
Defines the physical schema (tables, foreign keys, association tables, constraints).
Imports only `sqlalchemy`.
Not part of the public API and not imported by the domain or ports — only by the SQLAlchemy adapter.

### Public API — `ucsschool_objects/__init__.py`

Re-exports the domain entities, query DSL, exceptions, and the `Manager` port.
Concrete adapter classes live one level deeper at
`ucsschool_objects.core.adapters.<backend>` (currently `sqlalchemy`)
and are intentionally not promoted — they are a wiring-time concern.

Clients of this library import from exactly two places:

- `ucsschool_objects` for everyday code (domain types, query DSL, exceptions, `Manager`, storage-session protocols).
- `ucsschool_objects.core.adapters.<backend>` only at the wiring point
  (the chosen backend's manager classes, `DatabaseSettings`, `build_engine`, `build_kelvin_storage_session_factory`, …).

Deeper paths (`...adapters.sqlalchemy.session`, `...managers.user_manager`)
and `ucsschool_objects.database_models` are internal and may change without notice.

### Enforcement

The layer contract is enforced by
[`tests/test_architecture.py`](tests/test_architecture.py), which combines:

- **AST-based scanning** for banned external imports (`sqlalchemy`, `fastapi`, `pydantic`, …)
  in domain and ports.
- **pytestarch rules** for internal cross-package boundaries
  (domain → not adapters / not `database_models`, ORM → not domain, etc.).

## Development

### Install dependencies

```shell
uv sync
```

### Install pre-commit hooks

Pre-commit is configured at the repository root.
Run the following commands from the root of the repository (`../` relative to this package):

```shell
pipx install pre-commit  # or: uv tool install pre-commit
pre-commit install
pre-commit install --hook-type commit-msg
```

### Run the test suite

```shell
uv run pytest
```

Tests use an in-memory SQLite database by default.
To additionally run the PostgreSQL contract tests, provide a connection URL:

```shell
CORELIB_POSTGRES_TEST_URL=postgresql+psycopg://user:pass@localhost/testdb \
    uv run pytest
```

The suite requires **100 % branch coverage**
and fails automatically if coverage drops below that threshold.

### Tooling conventions

The following tools are enforced by pre-commit:

| Tool | Purpose |
|---|---|
| **black** | Code formatting |
| **isort** | Import ordering |
| **flake8** | Style and error linting |
| **mypy --strict** | Static type checking (this package only) |
| **bandit** | Security scanning |
| **conventional-pre-commit** | Commit message format |

Commit messages must follow the [Conventional Commits](https://www.conventionalcommits.org/) format
and include an issue or bug reference on its own line after a blank line:

```
feat(school): add create support to SQLAlchemy adapter

Issue univention/ucsschool-kelvin-rest-api#42
```

or

```
fix: correct edge case in query filter

Bug #123456
```

### Design conventions

#### Python style

- Every module starts with `from __future__ import annotations`.
- Import order: `__future__` → stdlib → third-party → internal.
  Conditional imports for type-checking only go under `if TYPE_CHECKING:`.
- Adapter modules declare `__all__` listing their exported symbols.
- Use `TypeAlias` for complex or reused type expressions.

#### Domain models

- Domain models are **plain classes**.
  Fields are stored privately (`_name`) behind public properties whose getters raise
  via `_require_loaded` when the value is `UNLOADED`.
- Each model declares `__serialize_fields__`, the single source of truth for introspection —
  use `get_properties()` / `domain_object_properties()`.
  Adding a field means updating `__init__`, the property pair, and `__serialize_fields__`.
- `Role` is read-only (properties without setters);
  the other models have setters because their collection fields are mutated
  by the SQLAlchemy adapter after construction.
- Equality and hashing are by `public_id` only — implement custom `__eq__` and `__hash__` on every model.
- Relationship collections are typed as `set[T]` (and `dict[UUID, SchoolMembership]` for `User.school_memberships`)
  rather than `list`,
  so duplicate-handling and lookup semantics match the domain's set-based identity.
- "Not yet fetched" is represented by the `UNLOADED` singleton (type `UnloadedType`), not by `None`.
  Field type is `T | UnloadedType`.
- "Not yet persisted" (no `public_id` assigned)
  is represented by the `UNSET` singleton (type `UnsetType`).
  Default value is `= UNSET`.
- Computed properties that depend on relationships
  must check `isinstance(self.<rel>, UnloadedType)` first
  and return `UNLOADED` if the relationship was not loaded.

#### Errors

- All domain exceptions inherit from `CorelibError`.
- Filter-related exceptions inherit from `InvalidFilter`.
- Adapters raise domain exceptions (e.g., `NotFound`, `InvalidFilter`),
  never raw SQLAlchemy or database errors.
- Exception constructors store context attributes (`field`, `operator`, `value`, …)
  before calling `super().__init__(message)`.

#### Ports and adapters

- Ports are `typing.Protocol` classes, not abstract base classes.
  Adapters satisfy them structurally — no inheritance required.
- Manager classes define class-level field maps
  (`_SCALAR_FIELD_MAP`, `_BASE_FIELD_MAP`, `_LOAD_ATTRIBUTE_MAP`, `_FIELD_MAP`)
  that map domain field names to ORM columns.
- Nested field filters (dot-paths like `"schools.name"`)
  are declared via `JoinSpec` entries in `_NESTED_FIELD_REGISTRY`.

#### ORM

- All ORM relationships default to `lazy="raise"` to catch accidental lazy loading at runtime.
  Eager loading must be requested explicitly via `selectinload` (triggered by `LoadSpec`).
- `LoadSpec` is the only mechanism for requesting eager loading in manager methods
  — never add unconditional `joinedload`/`selectinload` calls to a query.
- The `database_models` module is internal.
  Domain and port layers must not import from it.

#### Testing

- The suite requires **100 % branch coverage**.
- Domain contracts are tested via shared contract test functions
  in `tests/core/contracts/contract_test_support.py`,
  not by repeating identical tests per manager.
- Test fixtures use factory callables (e.g., `school_factory`, `user_factory`)
  rather than constructing ORM objects directly.
- Simple domain objects for unit tests are created by builder functions
  in `tests/core/domain/helpers/model_builders.py`.
  Use these instead of constructing models inline in test bodies.
