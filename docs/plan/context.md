# Context: Indexed case-insensitive wildcard search

This document is the durable background for this body of work. A future
session should be able to read only this file (plus `decisions.md` and the
relevant task file) and have everything needed to continue, without
re-deriving anything from chat history.

## Problem statement (original ticket, verbatim)

> ## Story
>
> As an API maintainer, I can use indexed case-insensitive wildcard searches
> on selected searchable properties, so that search queries remain performant
> even when using `ILIKE` / wildcard matching.
>
> ## Context/description
>
> During review we found that `ILIKE` currently does not use the existing
> index, because the index is case-sensitive.
>
> For case-insensitive searches without a leading wildcard, for example `foo`
> or `foo*`, we may be able to use an index on the lower-cased value.
>
> For general wildcard searches, especially patterns with leading or infix
> wildcards, a normal btree index is not sufficient. To support indexed
> wildcard searches, we need a GIN trigram index.
>
> This issue is about introducing an index strategy optimized for
> case-insensitive wildcard searches on dedicated properties only. The
> implementation should avoid adding broad or unnecessary indexes to all
> searchable fields.
>
> Implementation constraints:
>
> * Identify the properties that require indexed case-insensitive wildcard
>   search.
> * Add suitable database indexes for those properties.
> * Prefer a GIN trigram index where general wildcard search needs to be
>   supported.
> * Consider `lower(...)` based indexing where only exact or suffix-style
>   matching is required.
> * Verify that the search query actually uses the intended index.
> * Keep the scope limited to indexing/query optimization; changes to the
>   general search semantics should be handled separately.
>
> Desired artifacts:
>
> * Database migration for the new index/indexes.
> * Tests for the affected search behavior.
> * Performance evaluation or query plan documentation.
> * Attributes: username, first/last name, email, school name, ...
> * Ensure parity between Kelvin v1 and v2 regarding searches
>
> ## Acceptance criteria & steps for reproduction
>
> * [ ] Dedicated properties for case-insensitive wildcard search are
>   identified.
> * [ ] Suitable database index/indexes are added for these properties.
> * [ ] Case-insensitive wildcard search uses the intended index where
>   technically possible.
> * [ ] Existing search behavior is preserved.
> * [ ] Query performance is evaluated, for example with `EXPLAIN ANALYZE`.
> * [ ] All changed lines are covered by a unit test, if possible.
>   * [ ] Happy case.
>   * [ ] Relevant edge cases.
> * [ ] There is at least one end-to-end test that covers the changed search
>   behavior.

Key interpretive note (see `decisions.md` D1): v1 uses LDAP, which is
inherently case-insensitive for these attribute types. v2 uses PostgreSQL via
SQLAlchemy. The "v1/v2 parity" line, combined with "indexed **case-insensitive**
wildcard search", only makes sense if v2's currently case-*sensitive* search on
these fields is meant to become case-insensitive as part of this work — v1
code itself is not touched.

## Current state (as verified by reading the code)

### Domain layer

`ucsschool-objects/src/ucsschool_objects/core/domain/query.py`:
- `Operator` enum: `EQ, NE, IN, MATCHES, MATCHES_CI, GT, GTE, LT, LTE, CONTAINS`.
- `make_wildcard_filter(field, user_value, *, case_insensitive=False)`
  (lines 99-155): converts a user glob pattern (`*` wildcard) into a `Filter`
  with `Operator.MATCHES` (case_insensitive=False) or `Operator.MATCHES_CI`
  (case_insensitive=True). Works correctly even with no `*` in `user_value`
  (produces an escaped-literal pattern, so `ILIKE` against it behaves as a
  case-insensitive **exact** match).
- **No changes needed here** — already fully capable of everything this story
  needs.

### SQL adapter

`ucsschool-objects/src/ucsschool_objects/core/adapters/sqlalchemy/query_filter.py`:
- `_glob_to_sql_pattern()` (377-381): escapes `%`/`_`, turns `*` into `%`.
- `FILTER_OPERATOR_BUILDERS` (384-398):
  - `Operator.EQ` → `column == value`
  - `Operator.MATCHES` → `column.like(pattern, escape="\\")`
  - `Operator.MATCHES_CI` → `column.ilike(pattern, escape="\\")`
- **No changes needed here either.**

### v2 router call sites today (all case-sensitive unless noted)

`kelvin-api/ucsschool/kelvin/routers/v2/user.py`:
- `_str_filter(field, value)` (97-103): `"*" in value` → case-sensitive
  `MATCHES`; else → case-sensitive `EQ`. Used in `_build_query` (156-195) for
  `name`, `schools.name`, `firstname`, `lastname`, `record_uid`, `source_uid`.
- `email` (line 179): built directly as
  `Filter(field="email", op=Operator.EQ, value=email)` — bypasses
  `_str_filter` entirely, so `*` wildcards are **not currently accepted** for
  email at all.
- `_udm_property_filters()` (122-153): wildcard UDM JSON property values
  (line 150) → case-sensitive `MATCHES`; digit values → `Or(EQ, CONTAINS)`;
  other strings → `CONTAINS` (JSON containment, unrelated code path — not in
  scope).

`kelvin-api/ucsschool/kelvin/routers/v2/school.py`:
- Same `_str_filter` pattern (67-73) for school-name list search.
- `school_get`/`school_exists` (lines 135, 159) build
  `Filter(field="name", op=Operator.EQ, value=school_name)` directly.

`kelvin-api/ucsschool/kelvin/routers/v2/workgroup.py` and
`.../school_class.py`:
- Same `_str_filter` pattern for group `name`.
- Both build `Filter(field="school.name", op=Operator.EQ, value=school)`
  directly for the nested school-OU filter (~lines 157/177).
- Their single-item `get()` endpoints (`workgroup.py:202`,
  `school_class.py:184`) **already** use
  `Filter(field="name", op=Operator.MATCHES_CI, value=full_name)` — i.e., an
  unindexed `ILIKE` already runs in production today for these point lookups.
  This is the concrete, already-live instance of the bug the ticket describes.
- Both `search()` docstrings for the `school` query param currently say "case
  sensitive, exact match, required" — this text goes stale once these
  endpoints become case-insensitive and must be updated.

`record_uid`/`source_uid` filters are explicitly **out of scope** — they must
stay case-sensitive (external system correlation identifiers, not part of the
ticket's named properties).

### Database layer

- **Postgres only** in real deployments. SQLite is used solely for fast
  in-memory unit tests via a separate fixture. Alembic migrations only ever
  run against Postgres (`alembic/env.py` uses `build_settings()` from
  `ucsschool_objects.core.adapters.sqlalchemy.session`, always Postgres in
  that codepath).
- Relevant columns, all `String(255)`: `user.name` (username),
  `user.firstname`, `user.lastname`, `user.email`; `school.name`;
  `group.name`. `group.email`/`group.display_name` are explicitly out of
  scope (no current case-insensitive wildcard usage on them).
- **No Postgres extensions** (`pg_trgm`, etc.) or GIN/GIST indexes exist
  anywhere in the codebase today — only plain B-tree (unique index on
  `public_id`, unique constraints on `name`/`email`).
- Alembic revision chain: `f1c5bf519a40` (init_tables) → `e8b27dd51414`
  (add_mapping_tables) → `a3f9c12e8b01` (seed_default_roles) →
  `62810ee19208` (rename_group_type_to_role, **current head**).
  `alembic/env.py` depends only on `ucsschool_objects`
  (`Base.metadata`, `build_settings()`) — **zero dependency on the
  `kelvin-api` package today**. Migrations run inside
  `context.begin_transaction()` (`run_migrations_online()`), wrapped in a
  custom Postgres advisory-lock context manager for concurrent-deploy safety.
- `ucsschool_objects/core/adapters/sqlalchemy/session.py` (lines 37-70) is the
  idiomatic lightweight config style in this package: plain frozen dataclass +
  `os.getenv()`/`_read_env_or_file()`, **not** pydantic-settings/JSON-file
  based. This is the pattern to mirror for the new indexed-UDM-properties
  config (Task 006) — not the heavier `UDMMappingConfiguration` pattern below.
- `kelvin-api/ucsschool/kelvin/config.py`: `UDMMappingConfiguration`
  (lines 48-68, pydantic `BaseSettings`) has `user`/`school`/`school_class`/
  `workgroup` lists of UDM property names, loaded from a JSON config file
  (`UDM_MAPPED_PROPERTIES_CONFIG_FILE` env var) plus env/import overrides —
  a per-deployment, admin-configurable list of "extra" UDM properties surfaced
  via the API (stored in the `udm_properties` JSONB column), not
  static/known at repo-authoring time. `UDM_MAPPING_CONFIG` is a lazy
  singleton (`lazy_object_proxy.Proxy`).
  `prevent_mapped_attributes_in_udm_properties()` (lines 70-86) is the
  existing fail-fast validation pattern to mirror for Task 008, called from
  `load_configurations()` (92-97), itself invoked at startup from
  `kelvin-api/ucsschool/kelvin/service/lifespan.py`.
- `school_class` and `workgroup` are **not separate tables** — both are
  role-tagged rows in the single `group` table (confirmed in
  `database_models.py`). Any per-entity UDM-property-index config for these
  two entities must be deduplicated against the same physical `group` table.

### Existing tests

- Fast, SQLite-backed adapter-level tests live in
  `ucsschool-objects/tests/core/adapters/` (e.g.
  `test_nested_field_query_filter.py`, `test_nested_field_queries.py`), using
  the `db_session`/`db_engine` SQLite fixtures from
  `ucsschool-objects/tests/conftest.py`.
- `kelvin-api/tests/test_route_user.py::test_search_filter` and its siblings
  in `test_route_school.py`/`test_route_workgroup.py`/
  `test_route_school_class.py` are **live end-to-end tests against a real
  LDAP/UDM server**, not fast unit tests (they use `udm_kwargs`,
  `create_ou_using_python`, `retry_http_502` fixtures). This corrects an
  earlier assumption made while first reading the ticket.
- `postgres_db_url`/`postgres_db_engine`/`postgres_db_session` fixtures
  (`ucsschool-objects/tests/conftest.py`, ~lines 50-123) spin up a
  `postgres:15` Testcontainer on demand (or use the
  `CORELIB_POSTGRES_TEST_URL` env var if set; skipped on CI unless that var is
  set). `postgres_db_engine` calls `Base.metadata.create_all()`
  directly — **bypasses Alembic entirely** — so it is not suitable for
  testing the actual migration file. Use `postgres_db_url` (raw connection
  string) plus `alembic.command.upgrade(...)` instead for migration/
  index-usage tests (see Task 012).
- No existing `EXPLAIN`/query-plan test utilities anywhere in the codebase —
  net new for this work.

## Requirements and constraints (from the ticket)

- Identify dedicated properties needing indexed case-insensitive wildcard
  search.
- Add suitable DB indexes for exactly those properties — avoid broad/
  unnecessary indexes on all searchable fields.
- Prefer a GIN trigram index for general wildcard search.
- Consider `lower(...)`-based indexing for exact/suffix-only cases
  (explicitly deferred — see `decisions.md` D3).
- Verify the search query actually uses the intended index (`EXPLAIN`).
- Preserve existing search behavior otherwise (only case-sensitivity/email
  wildcard-capability changes).
- Keep scope limited to indexing/query optimization; general search-semantics
  changes are out of scope (in tension with the case-insensitivity switch —
  resolved via explicit stakeholder decision, see `decisions.md` D1).
- Deliverables: migration(s), tests (unit + e2e), performance
  evaluation/query plan documentation.
- Ensure v1/v2 parity (v1 is LDAP-based and untouched — parity is achieved by
  making v2 match v1's existing case-insensitive user-facing behavior).

## Known risks (not yet mitigated in code)

1. **SQLite masks case-sensitivity bugs.** SQLite's `LIKE` is
   case-insensitive by default for ASCII, so a SQLite-based unit test
   asserting "case-insensitive search works" could pass even if the code
   used `MATCHES` (case-sensitive intent) by mistake. Only the Postgres
   integration test (Task 012) or the real E2E tests against the
   Postgres-backed v2 API (Task 011) can actually catch this class of
   regression — treat those as load-bearing, and SQLite-based tests (Task
   009) as a secondary/fast smoke check only.
2. **Ordering hazard between config validation and migration application.**
   kelvin-api's startup validation (Task 008) and the dynamic migration
   (Task 007) both read the *same* env vars independently, but nothing ties
   them together — a deployment could set the env var without ever running
   the corresponding migration. Startup validation only checks "is this
   property a subset of `UDM_MAPPING_CONFIG`", not "does an index exist for
   it". Result: the app runs correctly (no correctness bug), just without the
   intended index (a silent performance-only gap). This is an **accepted
   risk** — do not build index-existence introspection at startup (a DB
   round-trip on every boot is over-engineering for this story); document
   clearly instead.
3. **`CREATE INDEX` (non-concurrent) write-lock window.** The recommended
   default (`decisions.md` D6) blocks writes to `user`/`school`/`group` for
   the duration of index creation. Acceptable given these are
   school-management-scale tables and migrations already run through an
   advisory-lock/maintenance-style pattern — but flag explicitly so a
   deployment with unexpectedly large tables can choose
   `CREATE INDEX CONCURRENTLY` instead (requires
   `op.get_context().autocommit_block()`, which interacts with the existing
   advisory-lock contextmanager in `env.py` and needs its own testing if
   used).
4. **Adding/removing a configured UDM indexed-property is not "live".**
   Since Alembic only replays migrations not yet applied, editing the
   indexed-UDM-properties env var after Task 007's migration has already run
   has **no effect** until a new migration is authored (or a future "sync
   indexes" management command is built — not part of this story). Removing
   a property from config does **not** drop its index (a dangling index
   remains until a manual `DROP INDEX` or a follow-up migration). Document as
   a known manual process, no auto-reconciliation.

## Unresolved questions (need stakeholder input)

- **Q1 — UDM property wildcard case-sensitivity.** Should the UDM-property
  wildcard branch in `_udm_property_filters()` (`user.py:149-150`) also
  switch to `case_insensitive=True`, or stay case-sensitive (only gaining an
  index, not a semantics change)? One analysis recommended leaving it
  untouched (it's outside the ticket's named-property list, and the indexing
  decision was framed as "indexing", not "semantics"); an earlier analysis
  argued for switching it too, for internal consistency within the same
  search request. **Not yet decided** — default to **leaving it
  case-sensitive** (smaller blast radius) unless the stakeholder says
  otherwise, but do not silently pick this — confirm before or during Task
  001.
- **Q2 — Literal `*` in exact-lookup path/required params.** Switching
  `school_get`/`school_exists` (`school.py`) and the `school.name` join
  filter in `workgroup.py`/`school_class.py`'s `search()` to
  `make_wildcard_filter(..., case_insensitive=True)` reintroduces wildcard
  interpretation of `*` in those values (a school/OU name literally
  containing `*` would be misinterpreted as a wildcard). Precedent already
  exists — `workgroup.py`/`school_class.py`'s `get()` endpoints already do
  this for `name`. Recommend accepting this (UCS OU naming rules already
  disallow `*`) but **confirm with the stakeholder before implementing
  Tasks 002-004**.
- **Q3 — New unit-test file acceptable?** Task 010 proposes a new file,
  `kelvin-api/tests/test_route_v2_filters.py`, testing router helper
  functions (`_str_filter`/`_build_query`) in isolation — a new pattern for
  this test suite (existing `test_route_*.py` files are E2E-only). Confirm
  this is an acceptable addition to the test layout before implementing
  Task 010.

## Relevant commands / files / services

- Run ucsschool-objects unit tests:
  `uv run pytest ucsschool-objects/ --cov-config=ucsschool-objects/pyproject.toml`
- Run kelvin-api tests: see `kelvin-api/Makefile` (`make pytest`,
  `make .coverage`)
- Postgres test container env var override: `CORELIB_POSTGRES_TEST_URL`
- New migrations: `make alembic-migration ALEMBIC_MESSAGE="..."` (root
  `Makefile`, lines 92-93), or hand-write following
  `alembic/versions/f1c5bf519a40_init_tables.py`'s style.
- Alembic config/env: `alembic/env.py`, `.env.alembic`.
- Docker compose (local Postgres): `dev/docker-compose.yaml`.
