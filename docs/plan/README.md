# Indexed case-insensitive wildcard search — planning workspace

## Overall goal

Make v2 API search on `username`, `firstname`, `lastname`, `email`,
`school name`, and `group name` case-insensitive — matching v1's LDAP-backed
case-insensitive behavior ("v1/v2 parity") — while keeping it fast via
targeted PostgreSQL `pg_trgm` GIN trigram indexes, and add an optional,
deployment-configurable mechanism to index specific UDM JSON properties too.

See [`context.md`](context.md) for full background (problem statement,
current-state findings, constraints, risks) and [`decisions.md`](decisions.md)
for why things are shaped the way they are.

## Task index

| ID | Title | Status | Area |
|----|-------|--------|------|
| [001](tasks/001-user-router-case-insensitive-filters.md) | User router: case-insensitive filters + email wildcard/CI | done | Router |
| [002](tasks/002-school-router-case-insensitive-filters.md) | School router: case-insensitive filters | done | Router |
| [003](tasks/003-workgroup-router-case-insensitive-filters.md) | Workgroup router: case-insensitive filters | done | Router |
| [004](tasks/004-school-class-router-case-insensitive-filters.md) | School-class router: case-insensitive filters | done | Router |
| [005](tasks/005-migration-fixed-trigram-indexes.md) | Migration: fixed `pg_trgm` GIN indexes | not started | Migration |
| [006](tasks/006-indexed-udm-properties-config-module.md) | Indexed-UDM-properties config module | not started | Config |
| [007](tasks/007-migration-configurable-udm-property-indexes.md) | Migration: configurable UDM-property GIN indexes | not started | Migration |
| [008](tasks/008-kelvin-api-startup-validation-indexed-udm-properties.md) | kelvin-api startup validation for indexed UDM properties | not started | Config |
| [009](tasks/009-unit-tests-query-filter-case-insensitive.md) | Unit tests: query-filter adapter case-insensitive coverage | not started | Tests |
| [010](tasks/010-unit-tests-router-filter-helpers.md) | Unit tests: router filter-helper functions | not started | Tests |
| [011](tasks/011-e2e-tests-case-insensitive-search.md) | E2E tests: case-insensitive search behavior | not started | Tests |
| [012](tasks/012-postgres-integration-test-index-usage.md) | Postgres integration test: migration + index-usage verification | not started | Tests |
| [013](tasks/013-performance-evaluation-evidence.md) | Performance evaluation evidence | not started | Tests |
| [014](tasks/014-optional-hoist-shared-str-filter.md) | Optional: hoist duplicated `_str_filter` into a shared module | done | Cleanup (optional) |

## Recommended execution order

- **Phase A — foundation** (no code deps on each other): Task 005 (fixed
  trigram indexes migration), Task 006 (indexed-UDM-properties config module).
- **Phase B — router changes** (can start anytime, but should land close to
  Phase A so case-insensitive search doesn't ship unindexed even temporarily):
  Tasks 001, 002, 003, 004. Do 001 first — it's the reference implementation
  the other three mirror.
- **Phase C — configurable UDM indexing** (depends on Task 006): Task 007,
  Task 008.
- **Phase D — tests** (depends on A+B+C being functionally complete): Tasks
  009, 010, 011, 012, 013.
- **Optional**, anytime after Phase B: Task 014.

## Dependencies between tasks

- 001–004 each independently mirror the same `_str_filter` pattern; 001
  (`user.py`) is the reference implementation the others copy.
- 007 depends on 006 (needs the config module to exist).
- 008 depends on 006 (imports the same config module).
- 012 depends on 005 and 007 (needs both migrations to exist to test index
  usage end-to-end).
- 011 depends on 001–004 (nothing to test case-insensitivity on otherwise).
- 009 depends on nothing code-side (tests the existing `query_filter.py`
  `MATCHES_CI` support, which already exists) but is logically part of this
  body of work.
- 013 depends on 012 (reuses its seeded dataset/queries for the before/after
  evidence).

## Resuming work in a future session

1. Read this README for current status.
2. Read [`context.md`](context.md) once for full background — it's written so
   a fresh session needs nothing else from prior chat transcripts.
3. Read [`decisions.md`](decisions.md) to avoid re-litigating settled
   questions.
4. Open the next `not started`/`in progress` task file in the recommended
   order above.
5. Update that task file's status and this README's status table as work
   progresses.
6. If a task surfaces a new decision, record it in `decisions.md` rather than
   leaving it only in a chat transcript.

All 14 tasks are unblocked and ready to implement in the order above.
