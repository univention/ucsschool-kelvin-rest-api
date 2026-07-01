# Task 010 — Unit tests: router filter-helper functions

**Status:** not started

## Objective

Add fast, DB-free unit tests directly exercising the `_str_filter`/
`_build_query` helper functions in the v2 routers, pinning the exact
correctness detail from Decision D5 (no-wildcard + `case_insensitive=True`
must produce `MATCHES_CI`, not `EQ`).

## Context

See [`../decisions.md`](../decisions.md) D10: this new test file was
approved by the stakeholder. All existing `kelvin-api/tests/test_route_*.py`
files are **live E2E tests against a real LDAP/UDM server** — there is
currently no fast, isolated unit-test layer for these particular router
helper functions. This task creates one.

Also relevant: D8 (UDM-property wildcard filters become case-insensitive
too) and D9 (accept `*` as a wildcard consistently, including in
`school_get`/`school_exists`/`school.name` join filters).

Depends on Tasks 001-004 having landed (or at least drafted) their
`_str_filter` changes, since this task tests the resulting behavior.

## Scope

- New file: `kelvin-api/tests/test_route_v2_filters.py`.
- Import `_str_filter`/`_build_query` directly from each of `user.py`,
  `school.py`, `workgroup.py`, `school_class.py`.
- Assert resulting `Filter`/`SearchQuery` object shapes (operator, field,
  value) for representative inputs — no DB, no FastAPI app instance, no
  network needed.

## Non-goals

- Testing actual DB query execution (that's Tasks 009/012) or full HTTP
  request/response cycles (that's Task 011).
- Testing `_udm_property_filters()`'s `CONTAINS`/digit branches (unchanged,
  out of scope per Task 001/D8 — D8 only affects the wildcard branch).

## Dependencies

Tasks 001-004 (tests the behavior they implement).

## Implementation steps

1. For each of `user.py`/`school.py`/`workgroup.py`/`school_class.py`'s
   `_str_filter`, write parametrized tests asserting:
   - `case_insensitive=True`, no `*` in value → `Filter(op=Operator.MATCHES_CI,
     ...)` — **not** `Operator.EQ`. This is the D5 correctness detail; a
     regression here (e.g. someone "simplifies" `_str_filter` back to a
     short-circuit on `"*" in value`) would silently reintroduce
     case-sensitive exact matching.
   - `case_insensitive=True`, `*` in value → `Filter(op=Operator.MATCHES_CI,
     ...)`.
   - `case_insensitive=False` (default), no `*` → `Filter(op=Operator.EQ,
     ...)` (unchanged legacy behavior — protects `record_uid`/`source_uid`).
   - `case_insensitive=False`, `*` in value → `Filter(op=Operator.MATCHES,
     ...)` (unchanged legacy behavior).
2. For `user.py`'s `_build_query`, assert the `email` clause is now built via
   `_str_filter`-equivalent logic (i.e., accepts `*`, becomes
   `MATCHES_CI`) rather than the old direct `Filter(..., EQ, ...)`.
3. For `user.py`'s `_udm_property_filters()`, assert the wildcard branch
   (`"*" in value`) now produces `Operator.MATCHES_CI` (per D8), while the
   digit-value (`Or(EQ, CONTAINS)`) and plain-string (`CONTAINS`) branches
   remain unchanged.
4. For `school.py`'s `school_get`/`school_exists` and `workgroup.py`/
   `school_class.py`'s `school.name` join filter: assert they now produce
   `MATCHES_CI` filters, and that a literal `*` in the value is treated as a
   wildcard (per D9).

## Acceptance criteria

- All new tests pass.
- The D5 correctness detail (no-wildcard + CI → `MATCHES_CI` not `EQ`) has an
  explicit, clearly-named test case that would fail if that logic regressed.
- `record_uid`/`source_uid`'s unchanged case-sensitive behavior has an
  explicit regression test.
- The D8 change (UDM-property wildcard filters → `MATCHES_CI`) and its
  boundary (CONTAINS/digit branches unchanged) both have explicit tests.
- The D9 change (`*` accepted as wildcard in `school_get`/`school_exists`/
  `school.name` join filters) has an explicit test.

## Validation / test steps

- Run via kelvin-api's test command (see `kelvin-api/Makefile`, `make
  pytest`) — should run fast (no DB, no LDAP) since these are pure
  function-level assertions.

## Likely files to inspect or modify

- New: `kelvin-api/tests/test_route_v2_filters.py`
- Read: `kelvin-api/ucsschool/kelvin/routers/v2/user.py`, `school.py`,
  `workgroup.py`, `school_class.py` (post Tasks 001-004 changes)

## Open questions / blockers

Blocked on Tasks 001-004 being at least drafted.

## Notes for next session

None.
