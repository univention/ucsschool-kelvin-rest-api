# Task 006 — Indexed-UDM-properties config module

**Status:** not started

## Objective

Create a new, lightweight, deployment-configurable module that lists which
UDM JSON properties (per entity: `user`/`school`/`school_class`/`workgroup`)
should get a GIN trigram expression index — the foundation both Task 007
(migration) and Task 008 (kelvin-api validation) build on.

## Context

See [`../context.md`](../context.md) for full background on
`UDM_MAPPING_CONFIG` (the existing, heavier, per-deployment "which UDM
properties are mapped into the API at all" config) and why this new config is
deliberately separate and lighter-weight. Relevant decision:
[`../decisions.md`](../decisions.md) D7.

Style to mirror: `ucsschool_objects/core/adapters/sqlalchemy/session.py`
(lines 37-70) — plain frozen dataclass + `os.getenv()`, no pydantic-settings,
no JSON config file.

Key constraint: this module must have **zero dependency on the `kelvin-api`
package**, since `alembic/env.py` currently only imports from
`ucsschool_objects` and Task 007's migration needs to import this module
directly.

`school_class` and `workgroup` are not separate tables — both map to the
physical `group` table (confirmed in `database_models.py`). This module must
expose that mapping so downstream consumers (Task 007's migration) can
deduplicate `(table, property)` pairs.

## Scope

- One new file:
  `ucsschool-objects/src/ucsschool_objects/core/adapters/sqlalchemy/indexed_udm_properties.py`.
- A frozen dataclass `IndexedUdmPropertiesConfig` with `user`, `school`,
  `school_class`, `workgroup` tuples of property names.
- A `build_indexed_udm_properties_config()` factory reading 4 comma-separated
  env vars.
- A `_SAFE_PROPERTY_NAME` regex and `validate_identifiers()` method that
  raises `ValueError` on any configured property name that doesn't match a
  safe identifier pattern (defense against unsafe SQL interpolation
  downstream in Task 007's migration).
- A `_TABLE_FOR_ENTITY` mapping (`"school_class"` → `"group"`,
  `"workgroup"` → `"group"`, `"user"` → `"user"`, `"school"` → `"school"`).

## Non-goals

- Actually creating any indexes — that's Task 007.
- Validating against `UDM_MAPPING_CONFIG` — that's Task 008 (lives in
  `kelvin-api`, which this module must not depend on).
- JSON-file-based config loading (explicitly rejected per D7).

## Dependencies

None — can start immediately (Phase A), independent of Task 005.

## Implementation steps

1. Create the module:
   ```python
   import os
   import re
   from dataclasses import dataclass

   _SAFE_PROPERTY_NAME = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")

   _ENV_VARS = {
       "user": "UCSSCHOOL_KELVIN_INDEXED_UDM_PROPERTIES_USER",
       "school": "UCSSCHOOL_KELVIN_INDEXED_UDM_PROPERTIES_SCHOOL",
       "school_class": "UCSSCHOOL_KELVIN_INDEXED_UDM_PROPERTIES_SCHOOL_CLASS",
       "workgroup": "UCSSCHOOL_KELVIN_INDEXED_UDM_PROPERTIES_WORKGROUP",
   }

   _TABLE_FOR_ENTITY = {
       "user": "user",
       "school": "school",
       "school_class": "group",
       "workgroup": "group",
   }

   def _parse_csv_env(env_var: str) -> list[str]:
       raw = os.getenv(env_var, "")
       return [p.strip() for p in raw.split(",") if p.strip()]

   @dataclass(frozen=True, slots=True)
   class IndexedUdmPropertiesConfig:
       user: tuple[str, ...] = ()
       school: tuple[str, ...] = ()
       school_class: tuple[str, ...] = ()
       workgroup: tuple[str, ...] = ()

       def validate_identifiers(self) -> None:
           for entity, props in (
               ("user", self.user), ("school", self.school),
               ("school_class", self.school_class), ("workgroup", self.workgroup),
           ):
               for prop in props:
                   if not _SAFE_PROPERTY_NAME.match(prop):
                       raise ValueError(
                           f"Invalid UDM property name {prop!r} configured for "
                           f"indexing on entity {entity!r}: must match "
                           f"{_SAFE_PROPERTY_NAME.pattern!r}."
                       )

   def build_indexed_udm_properties_config() -> IndexedUdmPropertiesConfig:
       return IndexedUdmPropertiesConfig(
           user=tuple(_parse_csv_env(_ENV_VARS["user"])),
           school=tuple(_parse_csv_env(_ENV_VARS["school"])),
           school_class=tuple(_parse_csv_env(_ENV_VARS["school_class"])),
           workgroup=tuple(_parse_csv_env(_ENV_VARS["workgroup"])),
       )
   ```
2. Add a module or class docstring explaining the distinction from
   `UDMMappingConfiguration` (this controls *indexing*, not *which properties
   are exposed by the API* — that stays `kelvin-api`'s job) and pointing to
   `docs/plan/context.md`/`decisions.md` D7 for the full rationale, so a
   future reader without this planning context understands why two config
   systems exist.

## Acceptance criteria

- `build_indexed_udm_properties_config()` returns empty tuples when no env
  vars are set.
- Comma-separated env var values are parsed into a tuple, with whitespace
  trimmed and empty entries dropped.
- `validate_identifiers()` raises `ValueError` for any property name
  containing characters outside `[A-Za-z0-9_]` or starting with a digit.
- `_TABLE_FOR_ENTITY` correctly maps `school_class` and `workgroup` to
  `"group"`.

## Validation / test steps

- New unit tests (pure-function, no DB needed) — could live in
  `ucsschool-objects/tests/core/adapters/test_indexed_udm_properties.py`:
  - empty env → empty config
  - `"foo, bar ,baz"` → `("foo", "bar", "baz")`
  - invalid name (e.g. `"1foo"`, `"foo-bar"`, `"foo'; DROP TABLE"`) →
    `validate_identifiers()` raises.
- Run via: `uv run pytest ucsschool-objects/ --cov-config=ucsschool-objects/pyproject.toml`

## Likely files to inspect or modify

- New:
  `ucsschool-objects/src/ucsschool_objects/core/adapters/sqlalchemy/indexed_udm_properties.py`
- New:
  `ucsschool-objects/tests/core/adapters/test_indexed_udm_properties.py`
- Read for style reference:
  `ucsschool-objects/src/ucsschool_objects/core/adapters/sqlalchemy/session.py`

## Open questions / blockers

None.

## Notes for next session

- Once this module exists, Task 007 imports
  `build_indexed_udm_properties_config` and `_TABLE_FOR_ENTITY` from it, and
  Task 008 imports `build_indexed_udm_properties_config` from it too.
- If the env var naming scheme changes during implementation, update
  Tasks 007/008's references here and in their own files.
