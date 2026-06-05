# AGENTS.md — ucsschool-objects

Internal library that backs Kelvin `v2`'s SQL read cache.
For full documentation (setup, usage examples, environment variables, design rationale),
see [README.md](README.md).
This file captures the conventions an agent is most likely to get wrong without a reminder.

## Scope

`ucsschool-objects` provides domain models for UCS@school core objects
(`School`, `Group`, `Role`, `User`, `SchoolMembership`),
an async `Manager[T]` port for querying and mutating them,
and a SQLAlchemy adapter that persists them to PostgreSQL (production) or SQLite (tests).

It has **no UDM, no LDAP, no FastAPI, and no Pydantic dependencies**
and must stay that way.

## Common commands

Run from this directory (`ucsschool-objects/`).

```shell
uv sync                                     # install deps (incl. dev)
uv run pytest                               # full suite, in-memory SQLite
uv run pytest tests/path/to/test_foo.py::test_bar   # single test
uv run pytest -k some_keyword               # subset by keyword
CORELIB_POSTGRES_TEST_URL=postgresql+psycopg://user:pass@host/db uv run pytest
                                            # also run PostgreSQL contract tests
```

Pre-commit (black, isort, flake8, mypy --strict, bandit, conventional-pre-commit) runs from the repository root.

## Architecture (one-paragraph version)

Ports-and-adapters / hexagonal.
Dependencies point inward only.

```
public API  →  domain (models, query, ports, errors)
                  ▲
                  │ implements
                  │
              adapters/sqlalchemy  →  database_models.py (ORM)  →  PostgreSQL / SQLite
```

| Layer | Path | May import | Must NOT import |
|---|---|---|---|
| Public API | `ucsschool_objects/__init__.py` | `core.domain` | adapters, `database_models` |
| Domain | `core.domain.*` | stdlib only | `sqlalchemy`, `pydantic`, `fastapi`, adapters, ORM |
| Ports | `core.domain.ports` | domain | anything concrete |
| Adapters | `core.adapters.<backend>` | domain, `database_models`, backend libs | sibling backends, public re-export |
| ORM | `database_models.py` | `sqlalchemy` | domain, ports, public re-export |

`tests/test_architecture.py` enforces these boundaries with a dual strategy:
**pytestarch** for internal cross-package rules and **AST scanning** for banned external imports.
Failures here are not arbitrary — they protect the v2 architecture.
Don't relax a rule to make a test pass; restructure the import.

### Client import boundary

When writing code that **uses** this library
(Kelvin REST API wiring, scripts, tests outside this package),
import from exactly two places:

1. `ucsschool_objects` — domain entities, query DSL, exceptions,
   the `Manager[T]` port, and the `KelvinStorageSession` / `KelvinStorageSessionFactory` protocols.
2. `ucsschool_objects.core.adapters.<backend>` — **wiring only**.
   Currently the only backend is `sqlalchemy`,
   so wiring code imports from `ucsschool_objects.core.adapters.sqlalchemy`
   (`DatabaseSettings`, `build_engine`, `build_kelvin_storage_session_factory`,
   the concrete `SQLAlchemy*Manager` classes, …).

Do not reach into deeper module paths
(`...adapters.sqlalchemy.session`, `...managers.user_manager`, mappers, query_filter)
or into `ucsschool_objects.database_models` from outside the package —
they are internal and free to change.
Inside this package, internal modules use the deep paths
(see "Architecture" above); the two-file rule applies only to clients.

## Conventions agents commonly miss

### Module headers
Every Python module starts with `from __future__ import annotations`.
Type-checking-only imports go under `if TYPE_CHECKING:`.

### Sentinels — three distinct meanings
- `UNLOADED` (type `UnloadedType`): "this relationship was not eagerly loaded".
  Field type is `T | UnloadedType`, **not** `T | None`.
- `UNSET` (type `UnsetType`): "no `public_id` assigned yet" (object not persisted).
- `None`: actually null in the domain.

Computed properties that depend on a relationship must check
`isinstance(self.<rel>, UnloadedType)` first and return `UNLOADED` propagatively.

### Eager loading is opt-in
ORM relationships default to `lazy="raise"` so accidental lazy fetches blow up.
The only way to request loading is `LoadSpec` passed to a manager method.
**Never** add unconditional `joinedload` / `selectinload` to a query.

### Domain models
- Plain classes. Fields are stored privately (`_name`) behind
  public properties whose getters raise via `_require_loaded` when the value is `UNLOADED`.
- Each model declares `__serialize_fields__`, the single source of truth for
  introspection — `get_properties()` and `domain_object_properties()` derive the
  public names from it.
- Adding a field means updating `__init__`, the property pair, and `__serialize_fields__`.
- Equality and hashing are by `public_id` only —
  implement custom `__eq__` / `__hash__` on every model.
- `Role` is read-only (properties without setters);
  the others have setters because adapters mutate their fields.
- Relationship collections are `set[T]` (or `dict[UUID, SchoolMembership]` for `User.school_memberships`),
  never `list`.

### Errors
Adapters raise the **domain's** exceptions
(`NotFound`, `InvalidFilter`, `UnsupportedFilterField`, …),
never raw SQLAlchemy or psycopg errors.
All inherit from `CorelibError`.
Constructors store context attributes (`field`, `operator`, `value`) before `super().__init__(message)`.

### Ports
Ports are `typing.Protocol`, not ABCs.
Adapters satisfy them structurally; do not add `class Foo(Manager[X])` inheritance.

### Reads vs writes — pick the right scope
- `session_scope()` — read-only (`get`, `search`). No transaction, no write locks.
- `transaction_scope()` — anything that mutates. Auto-commits on clean exit, rolls back on exception.

### Manager field maps
Each `SQLAlchemy*Manager` declares class-level `_FIELD_MAP` (and friends like
`_LOAD_ATTRIBUTE_MAP`, `_NESTED_FIELD_REGISTRY`).
Adding a queryable / sortable / loadable field means updating these maps —
not just adding an attribute.

## Testing

- **100 % branch coverage** is enforced (`fail_under = 100`).
  A change that drops coverage will fail CI.
- Cross-adapter / domain behavior is exercised via shared contract tests in
  `tests/core/contracts/contract_test_support.py` —
  add to those rather than duplicating per-manager tests.
- Build domain objects in tests via the factory callables in
  `tests/core/domain/helpers/model_builders.py`,
  not by inlining constructor calls.
- Architecture tests live in `tests/test_architecture.py` (see "Architecture" above).

## Commits

Conventional Commits, with an issue or bug reference on its own line after a blank line:

```
feat(school): add create support to SQLAlchemy adapter

Issue univention/ucsschool-kelvin-rest-api#42
```
