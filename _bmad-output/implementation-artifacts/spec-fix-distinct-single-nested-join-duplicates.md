---
title: 'Fix duplicate rows for single nested join filters'
type: 'bugfix'
created: '2026-05-11'
status: 'in-review'
baseline_commit: 'bda365488ee8da980d9fcfbe469e4b2b0f55eda9'
context: [
  '{project-root}/ucsschool-objects/src/ucsschool_objects/core/adapters/sqlalchemy/query_filter.py',
  '{project-root}/ucsschool-objects/tests/core/adapters/test_nested_field_query_filter.py'
]
---

<frozen-after-approval reason="human-owned intent — do not modify unless human renegotiates">

## Intent

**Problem:** Query building for nested filters/sorts applies DISTINCT only when more than one join root is requested. A single required nested join can still be N:M (for example user-to-group through membership) and produces duplicate entities in search results.

**Approach:** Apply DISTINCT whenever at least one nested join is applied, and add a regression test asserting distinct application for a single join root so duplicate-prone query shapes remain deduplicated.

## Boundaries & Constraints

**Always:** Keep behavior of join detection and join-path application unchanged; only change DISTINCT decision logic and test coverage directly related to duplicate prevention.

**Ask First:** Any broad optimization that changes SQL semantics beyond DISTINCT thresholding (for example conditional distinct by join cardinality metadata) or API-level response shape changes.

**Never:** Introduce manager/registry schema changes, alter domain filter syntax, or weaken existing nested-field validation/errors.

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|--------------|---------------------------|----------------|
| SINGLE_NESTED_JOIN_DUPLICATE_RISK | `required_joins={"groups"}` with valid join spec containing an N:M path | Returned select has DISTINCT applied and compiles successfully | N/A |
| MULTI_JOIN_STILL_DISTINCT | `required_joins={"groups","roles"}` with valid join specs | Returned select remains DISTINCT (no behavior regression) | N/A |
| NO_JOIN_NO_CHANGE | empty `required_joins` or missing registry | Original statement returned unchanged | N/A |

</frozen-after-approval>

## Code Map

- `ucsschool-objects/src/ucsschool_objects/core/adapters/sqlalchemy/query_filter.py` -- join application and DISTINCT threshold logic in `apply_nested_joins`.
- `ucsschool-objects/tests/core/adapters/test_nested_field_query_filter.py` -- nested join detection and join-application contract tests.

## Tasks & Acceptance

**Execution:**
- [x] `ucsschool-objects/src/ucsschool_objects/core/adapters/sqlalchemy/query_filter.py` -- change DISTINCT condition from `len(required_joins) > 1` to non-empty join set check -- ensures deduplication for single nested join roots.
- [x] `ucsschool-objects/tests/core/adapters/test_nested_field_query_filter.py` -- add/adjust test to assert DISTINCT is applied for a single required nested join -- prevents regression.
- [x] `ucsschool-objects/tests/core/adapters/test_nested_field_query_filter.py` -- keep existing multi-join DISTINCT behavior test green -- confirms no regression in prior contract.

**Acceptance Criteria:**
- Given a query requiring one nested relationship join, when `apply_nested_joins` is called with a populated registry, then the resulting SQL statement includes DISTINCT semantics.
- Given a query requiring multiple nested relationship joins, when `apply_nested_joins` is called, then DISTINCT semantics remain applied.
- Given no required joins (or no registry), when `apply_nested_joins` is called, then the original statement remains unchanged.

## Spec Change Log

## Verification

**Commands:**
- `pytest -q ucsschool-objects/tests/core/adapters/test_nested_field_query_filter.py` -- expected: all tests pass, including single-join DISTINCT regression coverage.
