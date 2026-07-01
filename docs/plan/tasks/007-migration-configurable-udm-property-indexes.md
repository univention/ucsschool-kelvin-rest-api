# Task 007 — Migration: configurable UDM-property GIN indexes

**Status:** not started

## Objective

Add a second new Alembic migration that reads Task 006's config module at
migration-run time and creates GIN trigram expression indexes on the
configured `udm_properties` JSON keys.

## Context

See [`../context.md`](../context.md), especially Risk 4 (config/migration
"not live" limitation) and Risk 2 (ordering hazard with Task 008's startup
validation). Relevant decisions: [`../decisions.md`](../decisions.md) D2, D6,
D7.

This migration is deployment-specific (driven by env vars that vary per
installation), unlike Task 005's fixed migration. It must read the config
**at migration-run time** — the same process that runs `alembic upgrade` has
access to the same environment variables `alembic/env.py` already reads for
`UCSSCHOOL_KELVIN_DB_URI` etc.

`school_class` and `workgroup` share the physical `group` table — if both
configs list the same property name, the migration must deduplicate
`(table, property)` pairs before emitting `CREATE INDEX`, both to avoid
redundant `IF NOT EXISTS` no-ops and to give the index a name that doesn't
imply an entity not reflected in the underlying table.

## Scope

- One new file:
  `alembic/versions/<new_revision2>_add_configurable_udm_property_indexes.py`,
  with `down_revision` set to whatever revision id Task 005 produced.
- Imports `build_indexed_udm_properties_config` and `_TABLE_FOR_ENTITY` from
  Task 006's module.
- Calls `config.validate_identifiers()` before generating any SQL (fail fast
  on a misconfigured env var, before it reaches DDL text).
- For each configured `(entity, property)` pair, deduplicated by
  `(table, property)`, emits:
  ```sql
  CREATE INDEX IF NOT EXISTS "ix_<table>_udm_<prop>_trgm"
  ON "<table>" USING gin ((udm_properties ->> '<prop>') gin_trgm_ops)
  ```
- Module docstring documenting the "not live" operational limitation (Risk 4
  in `../context.md`): this migration is a one-time snapshot of the env var
  at the moment it's run; editing the env var afterward has no effect until a
  new migration is authored; removing a property from config does not
  auto-drop its index.

## Non-goals

- Automatic index reconciliation/sync on every deploy — explicitly rejected
  as over-engineering for this story (see Risk 4).
- Dropping indexes for properties removed from config — manual follow-up,
  not automated.

## Dependencies

Task 006 (needs the config module to exist and be importable).

## Implementation steps

1. Confirm Task 005's assigned revision id and use it as `down_revision`
   here.
2. Write `upgrade()`:
   ```python
   from alembic import op
   import sqlalchemy as sa
   from ucsschool_objects.core.adapters.sqlalchemy.indexed_udm_properties import (
       build_indexed_udm_properties_config,
       _TABLE_FOR_ENTITY,
   )

   revision = "<new2>"
   down_revision = "<task-005-revision>"
   branch_labels = None
   depends_on = None

   def upgrade() -> None:
       config = build_indexed_udm_properties_config()
       config.validate_identifiers()
       seen: set[tuple[str, str]] = set()
       per_entity = (
           ("user", config.user), ("school", config.school),
           ("school_class", config.school_class), ("workgroup", config.workgroup),
       )
       for entity, props in per_entity:
           table = _TABLE_FOR_ENTITY[entity]
           for prop in props:
               if (table, prop) in seen:
                   continue
               seen.add((table, prop))
               index_name = f"ix_{table}_udm_{prop}_trgm"
               op.execute(sa.text(
                   f'CREATE INDEX IF NOT EXISTS "{index_name}" ON "{table}" '
                   f"USING gin ((udm_properties ->> '{prop}') gin_trgm_ops)"
               ))
   ```
3. Write `downgrade()` mirroring the same iteration/dedup logic but emitting
   `DROP INDEX IF EXISTS "ix_<table>_udm_<prop>_trgm"`.
4. Add the module docstring documenting the operational limitations (see
   Scope above) — this is the primary place this gets documented, since it's
   not going into a separate permanent doc file.
5. Note in a code comment why `prop` is safe to interpolate into the SQL
   string literal (`-> '{prop}'`) even though it comes from a raw env var:
   `validate_identifiers()` (Task 006) has already rejected anything outside
   `[A-Za-z0-9_]`, which excludes quote characters, before this code runs.

## Acceptance criteria

- With no env vars set, this migration is a no-op (`upgrade()` completes
  successfully, creates nothing).
- With `UCSSCHOOL_KELVIN_INDEXED_UDM_PROPERTIES_USER=phone` set,
  `alembic upgrade head` creates
  `ix_user_udm_phone_trgm ON "user" USING gin ((udm_properties ->> 'phone') gin_trgm_ops)`.
  ```
- With the same property configured for both `school_class` and `workgroup`,
  only one index is created on `group` (dedup works).
- A malicious/malformed env var (e.g. containing a quote or semicolon) causes
  `validate_identifiers()` to raise before any SQL is executed.

## Validation / test steps

- Task 012's Postgres integration test should include at least one scenario
  with an env var set before running this migration, verifying both the
  index gets created and that an `ILIKE` query against
  `udm_properties ->> 'prop'` uses it.
- Manual check: run against local Postgres with an env var set and inspect
  `pg_indexes` for the expected expression index.

## Likely files to inspect or modify

- New:
  `alembic/versions/<new_revision2>_add_configurable_udm_property_indexes.py`
- Read: Task 006's module (once it exists), Task 005's migration (for the
  `down_revision` value)

## Open questions / blockers

- Blocked on Task 006 existing.
- Blocked on Task 005's final revision id being known (to set
  `down_revision`).

## Notes for next session

- If Task 005's migration file naming/revision changes after this task was
  planned, update `down_revision` here accordingly.
- This is also a good place to double check: does the existing
  `advisory_lock`/transaction wrapping in `alembic/env.py` handle a migration
  whose `upgrade()` might do nothing (no configured properties) without
  issue? Expected: yes, since it's just a normal migration with conditional
  DDL — but worth a quick smoke test with an empty-env-var run.
