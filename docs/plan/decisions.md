# Decisions: Indexed case-insensitive wildcard search

One entry per decision: what was decided, why, what alternatives were
considered, and what it implies going forward. See [`context.md`](context.md)
for the background these decisions respond to.

---

## D1 — Switch v2 list-search call sites to case-insensitive matching

**Decision:** Change `_str_filter`-based filters (`name`, `school`/
`schools.name`, `firstname`, `lastname`) plus `email` to case-insensitive
(`MATCHES_CI`/`ilike`) across `user.py`/`school.py`/`workgroup.py`/
`school_class.py`, rather than only adding indexes for whatever `ILIKE` usage
exists today.

**Rationale:** Confirmed with the user (Jan — ticket author, and author of the
recent case-sensitivity-introducing refactor `4ea66c6c` / issue #207) via
direct question. It's the only reading under which "indexed case-insensitive
wildcard search" and "v1 parity" are actually achieved, since today's v2 list
search is case-sensitive.

**Alternatives considered:** Indexes-only, leaving call sites untouched —
rejected because it would leave the case-sensitivity/parity gap unaddressed,
defeating the ticket's stated goal.

**Consequences:** Touches 4 router files (Tasks 001-004); requires new
indexes (D3) to avoid a performance regression from switching `EQ`
(btree-eligible) to `ILIKE` (btree-ineligible without a supporting index);
requires updating stale "case sensitive" docstrings; raised the question of
literal `*` reintroduction in exact-lookup endpoints, resolved by D9.

---

## D2 — Indexed properties: User(name, firstname, lastname, email) + School(name) + Group(name), plus configurable UDM property indexing

**Decision:** Fixed indexes on exactly these 6 columns (Task 005);
additionally, build a deployment-configurable mechanism (not a fixed
migration) to index specific `udm_properties` JSON keys per entity
(Tasks 006-008).

**Rationale:** User's explicit choice, extending beyond the ticket's literal
list ("username, first/last name, email, school name, ...") because
`Group.name` already has unindexed `ILIKE` usage in production
(`workgroup.py`/`school_class.py` `get()`), and the user wants UDM properties
indexable too without hardcoding which ones (per-deployment mapped
properties already exist via `UDM_MAPPING_CONFIG`).

**Alternatives considered:**
- User + School only (the ticket's literal list) — rejected, leaves
  `Group.name`'s real unindexed ILIKE unaddressed.
- Index all mapped UDM properties — rejected by the user and by the ticket's
  "avoid broad or unnecessary indexes" constraint.

**Consequences:** Needs a new shared config module (Task 006), a second
migration (Task 007), and startup validation (Task 008); introduces risk 4
(config/migration drift) and risk 2 (ordering hazard) documented in
`context.md`.

---

## D3 — Index strategy: GIN trigram (`pg_trgm`) only, no `lower()` B-tree tier

**Decision:** Use `gin_trgm_ops` GIN indexes exclusively for all target
columns; explicitly do not implement the two-tier (btree-`lower()` + GIN
trigram) strategy the ticket floated.

**Rationale:** User's explicit choice — simpler, no query-builder rewriting
needed (`ILIKE` with any wildcard position, including none, can use a
trigram index directly), acceptable to be marginally less optimal than a
dedicated btree for pure prefix/exact lookups.

**Alternatives considered:** Two-tier `lower()`-btree + GIN trigram (the
ticket's suggested approach) — rejected for now due to added complexity (it
requires the query builder to choose SQL form based on wildcard position so
the planner picks the cheaper index). Explicitly documented as a **future
option** if a prefix-heavy/autocomplete access pattern turns out to be
common/perf-critical enough to justify a second index.

**Consequences:** Simpler migrations and router code; index storage/
maintenance cost is somewhat higher than a slimmer btree would be for pure
exact-match traffic; revisit if profiling later shows this matters.

---

## D4 — Add wildcard support + case-insensitivity to `email`

**Decision:** Route `email` through the same `_str_filter`(-style) helper
with `case_insensitive=True`, instead of the current direct
`Filter(field="email", op=Operator.EQ, value=email)`.

**Rationale:** User's explicit choice — for parity with the other listed
fields; the ticket lists "email" under wildcard-search-needing properties
even though today's code never accepted `*` for email at all.

**Alternatives considered:** Case-insensitive exact-match only (no
wildcard) — rejected in favor of full parity with name/firstname/lastname.

**Consequences:** This is a genuine new user-facing capability (wildcard
email search), not purely a case-sensitivity fix — noted as a deliberate,
approved scope expansion, not scope creep.

---

## D5 — `record_uid`/`source_uid` stay case-sensitive; `_str_filter` gains an opt-in `case_insensitive` parameter

**Decision:** `_str_filter(field, value, *, case_insensitive: bool = False)`
— default `False`, not a global behavior flip.

**Rationale:** `record_uid`/`source_uid` are external-system correlation
identifiers, not part of the ticket's named properties; flipping the global
default behavior would silently change their semantics with no request to do
so.

**Alternatives considered:** Making `_str_filter` always case-insensitive —
rejected as unscoped, riskier blast radius.

**Consequences:** Callers must opt in explicitly per field. Critically: the
no-wildcard branch when `case_insensitive=True` must **not** short-circuit to
`Operator.EQ` — it must still route through `make_wildcard_filter` so it
becomes an ILIKE-exact match. This exact logic detail is called out in
Task 001 to avoid a subtle correctness bug (a naive implementation might keep
the old `"*" in value` branching and only flip the operator used in the
`else` branch, which would produce `Operator.EQ` regardless of the CI flag —
wrong).

---

## D6 — Migration DDL style: raw `op.execute(text(...))`, plain `CREATE INDEX`, no ORM `Index()` objects

**Decision:** Migrations use raw `op.execute(text(...))` DDL rather than
`op.create_index(..., postgresql_using=..., postgresql_ops=...)`; use plain
`CREATE INDEX`, not `CONCURRENTLY`; do not add `Index()` objects to
`database_models.py`.

**Rationale:** `CREATE EXTENSION` has no `op.*` helper at all (must be raw
SQL) — keeping the index statements raw too keeps the migration internally
consistent and auditable, and the dynamic UDM-property migration (Task 007)
*must* use raw SQL anyway (expression indexes on JSON keys aren't
expressible via `op.create_index`'s column-list API). Plain `CREATE INDEX`
matches the existing migration style in this repo and avoids interacting
awkwardly with the custom Postgres advisory-lock transaction wrapper in
`env.py` that `CONCURRENTLY` would require working around. Not adding ORM
`Index()` objects avoids two sources of truth for indexes and keeps
`Base.metadata` (shared with the SQLite test fixture) untouched by
Postgres-only DDL.

**Alternatives considered:**
- `op.create_index` with dialect kwargs — works for the 6 fixed indexes, but
  not for the dynamic expression indexes, so rejected for consistency across
  both migrations.
- `CREATE INDEX CONCURRENTLY` — safer for very large tables, but more
  complex given the existing advisory-lock pattern — documented as a
  fallback option per-deployment, not the default.

**Consequences:** Migration files are less "Alembic-idiomatic" (raw SQL
blocks) but more consistent and auditable across both migrations; a
large-table deployment must consciously opt into `CONCURRENTLY` and validate
it against the advisory-lock interaction before doing so.

---

## D7 — Indexed-UDM-properties config: plain comma-separated env vars, new module in `ucsschool_objects`

**Decision:** A new module in `ucsschool_objects` (Task 006) using plain
comma-separated env vars, not the JSON-file/pydantic-settings pattern used by
`UDMMappingConfiguration`.

**Rationale:** Mirrors the existing lightweight `session.py` style already
used in `ucsschool_objects` for DB connection settings; avoids adding a
second, heavier config system for what is a narrower, more mechanical need
(a handful of property names per entity); keeps the config importable by
both the Alembic migration (Postgres-only, `ucsschool_objects`-only
dependency, no `kelvin-api` import) and by `kelvin-api`'s startup validation.

**Alternatives considered:** Extending `UDMMappingConfiguration` itself with
a new field — rejected because it would pull the JSON-file config-loading and
pydantic-settings machinery into the Alembic migration, adding a new
`kelvin-api`-package dependency to `alembic/env.py`'s import graph, and
because this config's job is orthogonal to which properties are *mapped*
into the API (stays `UDMMappingConfiguration`'s job) vs. which are *indexed*
(new, narrower concern).

**Consequences:** Property names must be validated with a strict identifier
regex before being interpolated into raw DDL text (defense against a
misconfigured env var producing invalid/unsafe SQL) — implemented in the
config module itself (`validate_identifiers()`), not deferred to the
migration.

---

## D8 — UDM-property wildcard filters also become case-insensitive

**Decision:** The UDM-property wildcard branch in `_udm_property_filters()`
(`kelvin-api/ucsschool/kelvin/routers/v2/user.py`, line 150 —
`make_wildcard_filter(field, value)`) switches to
`make_wildcard_filter(field, value, case_insensitive=True)`, matching the
other fields touched by D1.

**Rationale:** User's explicit choice, prioritizing internal consistency:
within the same search request, `name`/`firstname`/`lastname`/`email`/
`schools.name` become case-insensitive while UDM properties would otherwise
stay case-sensitive — a UX inconsistency within a single endpoint. Since D2
already added a mechanism to index specific UDM properties for wildcard
search, leaving their matching case-sensitive would have been an odd partial
state.

**Alternatives considered:** Leaving `_udm_property_filters()`'s wildcard
branch case-sensitive, only adding an index for it (smaller blast radius,
stays strictly within the ticket's named-property list) — rejected in favor
of consistency across the endpoint.

**Consequences:** Slightly expands scope beyond the ticket's literal property
list (now covers arbitrary configured UDM properties, not just the 6 named
columns), but this was already implied by D2's configurable-indexing
mechanism. Task 001's scope grows by one line (the `_udm_property_filters()`
change) rather than being deferred/excluded. The `CONTAINS`/digit branches in
`_udm_property_filters()` remain untouched (still out of scope — this
decision only affects the `"*" in value` wildcard branch).

---

## D9 — Accept `*` as a wildcard consistently, including in "exact-lookup" endpoints

**Decision:** `school_get`/`school_exists` (`school.py`) and the
`school.name` join filter in `workgroup.py`/`school_class.py`'s `search()`
switch to `make_wildcard_filter(field, value, case_insensitive=True)`, the
same helper used everywhere else in this story — even though these
particular values come from path parameters or a required query parameter
rather than free-text search input.

**Rationale:** User's explicit choice, consistent with the existing precedent
in `workgroup.py`/`school_class.py`'s `get()` endpoints, which already treat
`*` as a wildcard in the `name` field today. Using one helper everywhere
avoids introducing a second, bespoke "case-insensitive but wildcard-disabled"
code path purely for these call sites. UCS OU/school naming rules already
disallow `*` in practice, making the theoretical risk (a school/OU name
containing a literal `*` being misinterpreted as a wildcard) low.

**Alternatives considered:** Escaping any literal `*` before calling
`make_wildcard_filter` for these specific call sites, or introducing a
dedicated case-insensitive-exact-only helper — rejected as unnecessary
complexity given the naming-rule constraint and the existing `get()`-endpoint
precedent.

**Consequences:** Tasks 002-004 can proceed without a conditional branch —
`make_wildcard_filter(..., case_insensitive=True)` is used uniformly across
all four router files for every field touched by this story (`name`,
`firstname`, `lastname`, `email`, `schools.name`/`school.name`). If UCS OU
naming rules ever change to permit `*`, this would need revisiting — noted
here for future reference.

---

## D10 — Add a new fast unit-test file for router filter-helper functions

**Decision:** Create `kelvin-api/tests/test_route_v2_filters.py` as a new,
DB-free unit-test layer for the `_str_filter`/`_build_query` router helper
functions, even though all existing `kelvin-api/tests/test_route_*.py` files
are live E2E tests against a real LDAP/UDM server.

**Rationale:** User's explicit choice. This is the only way to cheaply and
precisely pin the exact operator-selection logic this story depends on
(especially the D5 correctness detail: no-wildcard + `case_insensitive=True`
must produce `MATCHES_CI`, not `Operator.EQ`) without requiring a live
LDAP/Postgres environment for every test run.

**Alternatives considered:** Relying solely on Task 011's E2E test additions
— rejected because E2E tests are slower, require live infrastructure, and
test the operator-selection logic only indirectly (via observed search
results), making a regression in the exact-branching logic harder to
pinpoint.

**Consequences:** Introduces a new test-layer convention for this test suite
(`test_route_v2_filters.py` alongside the existing E2E `test_route_*.py`
files) — worth a one-line callout in the PR description so reviewers
understand it's intentionally a different kind of test (pure function
assertions, no fixtures/app/DB) rather than an incomplete E2E test.
