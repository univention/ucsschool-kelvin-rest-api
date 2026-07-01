# Task 011 — E2E tests: case-insensitive search behavior

**Status:** not started

## Objective

Extend the existing, real end-to-end tests (against a live LDAP/UDM server
and the actual v2 API/Postgres backend) with case-variation and
email-wildcard test cases, providing the load-bearing proof that
case-insensitive search actually works (per Risk 1 — SQLite tests can't prove
this).

## Context

See [`../context.md`](../context.md) — corrects an earlier assumption that
these tests were fast/SQLite-based; they are real E2E tests using `udm_kwargs`,
`create_ou_using_python`, `retry_http_502` fixtures. This is exactly why
they're the right place to prove case-insensitivity actually works against
the real Postgres-backed v2 API.

Existing tests to extend:
- `kelvin-api/tests/test_route_user.py::test_search_filter` (parametrized,
  lines ~350-439) — covers `email`, `record_uid`, `source_uid`, `birthday`,
  `expiration_date`, `disabled`, `firstname`, `lastname`, `roles`, `school`.
- `kelvin-api/tests/test_route_school.py` — analogous search test.
- `kelvin-api/tests/test_route_workgroup.py` — analogous search test.
- `kelvin-api/tests/test_route_school_class.py` — analogous search test.

## Scope

- Extend the 4 files above with new parametrized cases.
- `test_route_user.py`: add case-variation cases (query value
  uppercased/mixed-case relative to the created user's actual `name`/
  `firstname`/`lastname`/`email`, asserting the user is still found), plus a
  new email-wildcard case (e.g. `f"{prefix}*"` matching the created user's
  email, which was not previously possible since `email` never accepted `*`
  before Task 001).
- `test_route_school.py`/`test_route_workgroup.py`/
  `test_route_school_class.py`: add analogous case-variation cases for their
  respective `name` (and `school`) search parameters.

## Non-goals

- Any new test infrastructure/fixtures — reuse what exists.
- Testing the UDM-property-indexing mechanism (Tasks 006-008) at the E2E
  level — that's adequately covered by Task 012's Postgres integration test.

## Dependencies

Tasks 001-004 (there's nothing case-insensitive to test until those land).

## Implementation steps

1. Read each target test file's current parametrization style in full before
   editing, to match existing conventions exactly (fixture usage, cleanup,
   assertion style).
2. For `test_route_user.py::test_search_filter`, add parametrized cases such
   as:
   - Search `name=<created_username>.upper()` → still finds the user.
   - Search `firstname=<created_firstname> mixed-cased` → still finds.
   - Search `email=<created_email>.upper()` → still finds (new: exact CI
     match).
   - Search `email=<prefix>*` (wildcard, previously unsupported) → finds the
     user by email prefix.
3. Mirror equivalent case-variation additions in `test_route_school.py`
   (school `name`), `test_route_workgroup.py` (`name` and `school`),
   `test_route_school_class.py` (`name` and `school`).
4. Confirm existing (pre-change) test cases still pass — i.e., this task must
   not break any currently-passing search assertions (per the "existing
   search behavior is preserved" acceptance criterion in `../context.md`).

## Acceptance criteria

- All new and existing tests in the 4 target files pass against a real test
  environment.
- At least one test proves email now supports wildcard search.
- At least one test per entity (user/school/workgroup/school_class) proves
  case-insensitive matching works end-to-end.

## Validation / test steps

- Run via whatever mechanism these E2E tests normally run (they need a real
  LDAP/UDM/Postgres environment — check `kelvin-api/Makefile` and any CI
  config for how this suite is normally invoked; do not attempt to run these
  against a bare `pytest` without the required environment).

## Likely files to inspect or modify

- `kelvin-api/tests/test_route_user.py`
- `kelvin-api/tests/test_route_school.py`
- `kelvin-api/tests/test_route_workgroup.py`
- `kelvin-api/tests/test_route_school_class.py`

## Open questions / blockers

Blocked on Tasks 001-004.

## Notes for next session

- Since these are real, environment-dependent E2E tests, verifying them
  requires the appropriate local/CI setup (LDAP + Postgres) — confirm what's
  available before attempting to run them, and document any setup steps
  needed here if they aren't obvious from `kelvin-api/Makefile`.
