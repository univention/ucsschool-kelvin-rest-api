# Task 012 — Postgres integration test: migration + index-usage verification

**Status:** not started

## Objective

Prove, via an automated, re-runnable test against a real Postgres instance,
that the migrations from Tasks 005 and 007 actually create the intended
indexes and that representative `ILIKE` queries actually use them (not a
sequential scan) — the concrete, automatable form of the ticket's "verify
that the search query actually uses the intended index" acceptance
criterion.

## Context

See [`../context.md`](../context.md): `postgres_db_engine` (existing fixture)
calls `Base.metadata.create_all()` directly and **bypasses Alembic** — not
suitable here, since the point is to exercise the *actual* migration files.
Use `postgres_db_url` (raw connection string fixture) instead, and drive
Alembic programmatically.

No existing `EXPLAIN`/query-plan test utilities exist anywhere in this
codebase — this task creates the first one.

Postgres will not choose an index over a sequential scan on a tiny table
regardless of whether the index exists — the test must seed enough rows for
the planner to have a realistic incentive to use the index.

## Scope

- New file:
  `ucsschool-objects/tests/core/adapters/test_trigram_index_migration.py`.
- Use the `postgres_db_url` fixture; drive
  `alembic.command.upgrade(alembic_config, "head")` against it. Build an
  `alembic.config.Config` pointing `script_location` at the repo's
  `alembic/` directory, with `sqlalchemy.url` set to `postgres_db_url`.
  **Decide during implementation** whether it's less invasive to (a) set an
  env var that `alembic/env.py`'s `build_settings()` will pick up, or (b)
  adjust `env.py` to prefer an already-set `sqlalchemy.url` main option if
  present before calling `build_settings()` — pick whichever requires less
  change to `env.py` and note the choice here once made.
- Seed 5,000–10,000 rows into `user`/`school`/`group` using the existing
  `AsyncUserFactory`/`AsyncSchoolFactory`/`AsyncGroupFactory` test factories
  (find these in `ucsschool-objects/tests/` — likely near
  `tests/test_types.py` per earlier research; confirm exact location/names
  during implementation), with randomized names.
- A reusable helper, e.g. `_explain_json(session, sql: str) -> dict`,
  wrapping `EXPLAIN (FORMAT JSON) <query>` and parsing the single-row JSON
  result.
- Assertions for leading-wildcard, trailing-wildcard, and no-wildcard `ILIKE`
  queries against each of the 6 fixed indexed columns (Task 005) plus at
  least one dynamically-configured UDM property column (Task 007 — requires
  setting the relevant env var before running the migration in this test):
  the plan tree contains a `Bitmap Index Scan`/`Index Scan` node referencing
  the expected index name, and no top-level `Seq Scan` for that filter.

## Non-goals

- Testing router-level code (Tasks 001-004, 010, 011 cover that).
- Exhaustive coverage of every possible wildcard position/column combination
  — representative coverage (leading/trailing/none, across all 6 fixed
  columns, plus one dynamic UDM property) is sufficient.

## Dependencies

Task 005 and Task 007 (needs both migrations to exist).

## Implementation steps

1. Locate the existing async factories (`AsyncUserFactory` etc.) and confirm
   their exact import path and API.
2. Write a fixture or setup step that: gets `postgres_db_url`, builds an
   `alembic.config.Config`, runs `alembic.command.upgrade(cfg, "head")`
   against it, then seeds rows via the factories using a session bound to
   that same URL.
3. Implement `_explain_json(session, sql)`.
4. Write parametrized test cases per column × wildcard-position, asserting
   index usage as described in Scope.
5. For the dynamic UDM property case, set the relevant
   `UCSSCHOOL_KELVIN_INDEXED_UDM_PROPERTIES_USER` (or similar) env var before
   triggering the migration within this test, then run an `ILIKE` query
   against `udm_properties ->> 'prop'` and assert index usage.
6. Confirm this test module correctly skips (via the existing
   `postgres_db_url` fixture's own skip behavior) when no Postgres
   Testcontainer/`CORELIB_POSTGRES_TEST_URL` is available, consistent with
   other Postgres-only tests in this codebase — no additional marker should
   be needed beyond using the fixture.

## Acceptance criteria

- Test seeds a realistic dataset and the Postgres planner genuinely chooses
  an index scan (not just "the test says so" — actually verify against a
  real `EXPLAIN` output).
- All 6 fixed-index columns plus at least 1 dynamic UDM property column are
  covered.
- No top-level `Seq Scan` appears for any of the asserted queries.
- Test is skippable in environments without Postgres access, per existing
  convention.

## Validation / test steps

- `uv run pytest ucsschool-objects/ --cov-config=ucsschool-objects/pyproject.toml`
  with a Postgres Testcontainer available (Docker running locally) or
  `CORELIB_POSTGRES_TEST_URL` set.

## Likely files to inspect or modify

- New:
  `ucsschool-objects/tests/core/adapters/test_trigram_index_migration.py`
- Read: `ucsschool-objects/tests/conftest.py` (fixtures), `alembic/env.py`
  (to decide the URL-override approach), the async factory definitions.
- Possibly modify: `alembic/env.py` (only if the "prefer already-set
  sqlalchemy.url" approach is chosen — keep this change minimal and
  backward-compatible).

## Open questions / blockers

Blocked on Tasks 005 and 007. The "how to point Alembic at the test DB"
approach (env var vs. `env.py` tweak) is an implementation decision to make
during this task, not a pre-resolved question — record the choice here once
made.

## Notes for next session

- This test's seeded dataset and query set are reused as the basis for
  Task 013's before/after performance evidence — consider writing Task 012
  in a way that makes it easy to also run `EXPLAIN ANALYZE` (with real
  timings) manually against the same setup for that purpose.
