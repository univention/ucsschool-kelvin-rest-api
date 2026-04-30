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

In the Kelvin connector application, these adapter helpers are now consumed through a
`dependency-injector` container at the composition root for standardized startup wiring.

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
