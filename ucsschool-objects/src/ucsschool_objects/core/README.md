# Kelvin Core Library

The core library provides a persistence-agnostic business layer for read and search access to School, Group, Role, and User domain objects.

## Quick Wiring (SQLAlchemy Adapter)

```python
from sqlalchemy import make_url

from ucsschool_objects.core.adapters.sqlalchemy.session import (
    DatabaseSettings,
    build_engine,
    build_kelvin_storage_session_factory,
)

settings = DatabaseSettings(url=make_url("postgresql+psycopg://kelvin@db.example/kelvin"))
engine = build_engine(settings)
storage_factory = build_kelvin_storage_session_factory(engine)
```

## Session Scope: Get Domain Models

```python
from uuid import UUID

school_id = UUID("11111111-1111-1111-1111-111111111111")
user_id = UUID("22222222-2222-2222-2222-222222222222")

async with storage_factory.session_scope() as storage:
    school = await storage.schools.get(school_id)
    user = await storage.users.get(user_id)
```

## Transactional Scope: Modify Domain Models

`modify()` uses ordered JSONPath operations. For `transaction_scope`, commit/rollback is automatic on context exit.

```python
group_id = UUID("33333333-3333-3333-3333-333333333333")

ops = [
    {"op": "replace", "path": "display_name/de", "value": "Neue Gruppe"},
    {"op": "set", "path": "email", "value": "group@example.org"},
]

async with storage_factory.transaction_scope() as storage:
    await storage.groups.modify(group_id, ops)
```

## Notes

- Managers exposed by `storage`: `schools`, `roles`, `groups`, `users`.
- Scope behavior:
  - `transaction_scope`: success -> commit, exception -> rollback
  - `session_scope`: success -> no implicit commit, exception -> rollback
- Dispose the engine on shutdown:

```python
await engine.dispose()
```

## Python Typing and Private API Policy

- Prefer `_` prefixes for private or internal symbols.
- Keep `reportPrivateUsage` enabled by default.
- Use file-level `# pyright: reportPrivateUsage=false` only when the whole file intentionally works with private or internal APIs.
- Good examples for file-level suppression:
    - package facade modules such as `__init__.py` that re-export private implementation modules via `__all__`
    - white-box tests for internal helpers
    - legacy compatibility shims
    - composition or wiring modules that assemble internal components
- Prefer line-level suppression for isolated cases: `# pyright: ignore[reportPrivateUsage]`
- Avoid suppressing this warning in normal domain or business code.
- Avoid depending on private symbols from external packages.
- If many files need the suppression, reconsider the package boundaries or expose a proper public API.

Rule of thumb:

Use file-level `reportPrivateUsage=false` only when private access is intentional, local to our project, and part of an API boundary, test, compatibility, or wiring layer.
