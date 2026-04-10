---
title: 'Refactor readers.py into a readers subpackage'
type: 'refactor'
created: '2026-04-20'
status: 'in-review'
baseline_commit: '890b5fac441d7afd3f943320904180ead0289276'
context: []
---

<frozen-after-approval reason="human-owned intent — do not modify unless human renegotiates">

## Intent

**Problem:** `readers.py` contains four reader classes plus all shared helpers in a single ~500-line file, making it hard to navigate and extend.

**Approach:** Convert `readers.py` into a `readers/` package. Each reader class moves to its own submodule; shared types and helpers go to `readers/_shared.py`; `readers/__init__.py` re-exports all previously public symbols so every existing import keeps working.

## Boundaries & Constraints

**Always:**
- All existing public import paths (`from ucsschool_objects.core.adapters.sqlalchemy.readers import ...`) must continue to work unchanged.
- `JoinSpec`, `JoinType`, and the four `SQLAlchemy*Reader` classes must remain importable from `ucsschool_objects.core.adapters.sqlalchemy.readers`.
- The original `readers.py` file must be deleted after the package is created.
- No logic changes — pure structural move.

**Ask First:**
- If any circular-import issue surfaces at runtime that cannot be resolved cleanly without a logic change.

**Never:**
- Change any business logic, SQL query construction, or mapping behaviour.
- Introduce new public symbols or rename existing ones.
- Split `_shared.py` further (e.g. into separate type and helper files) — one shared module is sufficient.

</frozen-after-approval>

## Code Map

- `ucsschool-objects/src/ucsschool_objects/core/adapters/sqlalchemy/readers.py` -- source file to be replaced by the package
- `ucsschool-objects/src/ucsschool_objects/core/adapters/sqlalchemy/__init__.py` -- imports from `.readers`; no change needed if `__init__.py` of new package re-exports correctly
- `ucsschool-objects/src/ucsschool_objects/core/adapters/sqlalchemy/query_filter.py` -- TYPE_CHECKING import of `JoinSpec` from `readers`; must keep working
- `ucsschool-objects/tests/core/adapters/test_nested_field_queries.py` -- imports reader classes and `JoinSpec`
- `ucsschool-objects/tests/core/adapters/test_nested_field_query_filter.py` -- imports `JoinSpec`, `JoinType`

## Tasks & Acceptance

**Execution:**
- [ ] Create `ucsschool-objects/src/ucsschool_objects/core/adapters/sqlalchemy/readers/_shared.py` -- move all shared types (`JoinType`, `JoinSpec`, `QueryExpr`, `ModelClass`, `TSelect`, `_USER_LOAD_ATTRIBUTE_MAP`) and all private helper functions (`_get_exposed_fields`, `_iter_filters`, `_compose_field_map`, `_load_requested_scalar_attributes`, `_school_scalar_columns`, `_group_scalar_columns`, `_role_scalar_columns`, `_user_scalar_columns`, `_includes_user_memberships`, `_with_user_related_load_options`, `_with_user_load_options`) here
- [ ] Create `ucsschool-objects/src/ucsschool_objects/core/adapters/sqlalchemy/readers/school_reader.py` -- move `SQLAlchemySchoolReader`; import dependencies from `._shared` and `query_filter`
- [ ] Create `ucsschool-objects/src/ucsschool_objects/core/adapters/sqlalchemy/readers/group_reader.py` -- move `SQLAlchemyGroupReader`; import dependencies from `._shared` and `query_filter`
- [ ] Create `ucsschool-objects/src/ucsschool_objects/core/adapters/sqlalchemy/readers/role_reader.py` -- move `SQLAlchemyRoleReader`; import dependencies from `._shared` and `query_filter`
- [ ] Create `ucsschool-objects/src/ucsschool_objects/core/adapters/sqlalchemy/readers/user_reader.py` -- move `SQLAlchemyUserReader`; import dependencies from `._shared` and `query_filter`
- [ ] Create `ucsschool-objects/src/ucsschool_objects/core/adapters/sqlalchemy/readers/__init__.py` -- re-export `SQLAlchemyGroupReader`, `SQLAlchemyRoleReader`, `SQLAlchemySchoolReader`, `SQLAlchemyUserReader`, `JoinSpec`, `JoinType` and update `__all__`
- [ ] Delete `ucsschool-objects/src/ucsschool_objects/core/adapters/sqlalchemy/readers.py` -- replaced by the package

**Acceptance Criteria:**
- Given the package is installed, when `from ucsschool_objects.core.adapters.sqlalchemy.readers import SQLAlchemySchoolReader, SQLAlchemyGroupReader, SQLAlchemyRoleReader, SQLAlchemyUserReader, JoinSpec, JoinType` is executed, then no `ImportError` is raised.
- Given the test suite, when `pytest ucsschool-objects/tests/` is run, then all previously passing tests still pass.
- Given the readers package, when `from ucsschool_objects.core.adapters.sqlalchemy import SQLAlchemySchoolReader` is executed, then it resolves correctly.

## Design Notes

`_shared.py` holds only what is used by two or more reader submodules. Each reader submodule imports exclusively from `._shared` (package-relative), standard library, SQLAlchemy, and domain models — never from sibling reader modules.

`__init__.py` example (public surface only):

```python
from .group_reader import SQLAlchemyGroupReader
from .role_reader import SQLAlchemyRoleReader
from .school_reader import SQLAlchemySchoolReader
from .user_reader import SQLAlchemyUserReader
from ._shared import JoinSpec, JoinType

__all__ = [
    "SQLAlchemyGroupReader",
    "SQLAlchemyRoleReader",
    "SQLAlchemySchoolReader",
    "SQLAlchemyUserReader",
    "JoinSpec",
    "JoinType",
]
```

## Verification

**Commands:**
- `uv run python -c "from ucsschool_objects.core.adapters.sqlalchemy.readers import SQLAlchemySchoolReader, SQLAlchemyGroupReader, SQLAlchemyRoleReader, SQLAlchemyUserReader, JoinSpec, JoinType; print('OK')"` -- expected: `OK`
- `uv run pytest tests/ -x -q` -- expected: all tests pass

## Spec Change Log
