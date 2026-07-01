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
requires updating stale "case sensitive" docstrings; opens Q2 (literal `*`
reintroduction in exact-lookup endpoints, see `context.md`).

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
