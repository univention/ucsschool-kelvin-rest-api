# Task 009 — Unit tests: query-filter adapter case-insensitive coverage

**Status:** not started

## Objective

Add fast, SQLite-fixture-based unit tests confirming
`Filter(field, Operator.MATCHES_CI, value)` behaves correctly at the adapter
level — as a smoke check, explicitly not the load-bearing proof of
case-insensitivity (see Risk 1).

## Context

See [`../context.md`](../context.md) Risk 1: **SQLite's `LIKE` is already
case-insensitive by default for ASCII text**, so a SQLite-based test
asserting "case-insensitive search works" could pass even if the code
accidentally used `Operator.MATCHES` (case-sensitive intent) instead of
`MATCHES_CI` — SQLAlchemy's `.like()` compiles to SQLite's inherently-CI
`LIKE`. This means these tests **cannot** be trusted alone to catch a
case-sensitivity regression. Tasks 011 (E2E) and 012 (Postgres integration)
are the load-bearing tests for that; this task is a fast, secondary check
only (e.g., of escaping/wildcard-translation edge cases which SQLite *can*
validate correctly).

`Operator.MATCHES_CI` already exists and is already tested to some extent —
`ucsschool-objects/tests/core/adapters/test_nested_field_query_filter.py`
(lines 151-177) already verifies the SQL rendering differs correctly between
Postgres (`ILIKE`) and SQLite (`LIKE lower(...)`) dialects, at the
**SQL-string level** (not by executing against a real SQLite DB). This task
extends that with actual query execution against the `db_session` fixture.

## Scope

- `ucsschool-objects/tests/core/adapters/` — extend
  `test_nested_field_query_filter.py` or add a small sibling file (e.g.
  `test_case_insensitive_filters.py`).
- Use the existing `db_session`/`db_engine` SQLite fixtures from
  `ucsschool-objects/tests/conftest.py`.
- Cover: `MATCHES_CI` with leading wildcard, trailing wildcard, infix
  wildcard, and no wildcard (exact match) — confirming the escaping and
  wildcard-translation logic (`_glob_to_sql_pattern`) behaves correctly, with
  an explicit code comment noting the SQLite case-insensitivity caveat above.

## Non-goals

- Proving case-insensitivity itself is correct end-to-end (that's Tasks 011/
  012's job).
- Any change to `query_filter.py`/`query.py` — this task only adds tests.

## Dependencies

None — the code under test (`MATCHES_CI`) already exists and works. Can start
immediately.

## Implementation steps

1. Read `test_nested_field_query_filter.py` in full to match its existing
   style/fixtures.
2. Add test cases exercising `Filter(field="name", op=Operator.MATCHES_CI,
   value=...)` against seeded rows in the `db_session` SQLite fixture, for:
   - `"John*"` → matches `"John Doe"`, `"john doe"` (SQLite CI caveat
     applies here — note in comment).
   - `"*doe"` → matches trailing.
   - `"*oh*"` → matches infix.
   - `"John Doe"` (no wildcard) → matches exact, case-insensitively (again,
     SQLite-CI-caveat applies).
   - Escaping: a value containing literal `%`/`_` still matches literally
     (this part **is** dialect-independent and worth asserting here).
3. Add a top-of-file or per-test comment explaining the SQLite-CI caveat and
   pointing to `docs/plan/context.md` Risk 1 and Tasks 011/012 as the
   load-bearing tests.

## Acceptance criteria

- New tests pass.
- Escaping behavior (literal `%`/`_` in search values) is asserted and
  passes — this is the part of this task that's actually dialect-independent
  and meaningful regardless of the SQLite caveat.
- Comments clearly flag which assertions are "SQLite happens to also pass
  this" vs. genuinely proving something.

## Validation / test steps

- `uv run pytest ucsschool-objects/ --cov-config=ucsschool-objects/pyproject.toml`

## Likely files to inspect or modify

- `ucsschool-objects/tests/core/adapters/test_nested_field_query_filter.py`
  (extend) or new sibling file
- `ucsschool-objects/tests/conftest.py` (read only, for fixture reference)

## Open questions / blockers

None.

## Notes for next session

- If, during implementation, it turns out SQLite tests genuinely add little
  value beyond what's already in `test_nested_field_query_filter.py`'s
  string-rendering tests, it's fine to keep this task small — don't invent
  extra scope just to fill it out. The important tests are 011 and 012.
