# Task 004 — School-class router: case-insensitive filters

**Status:** done

## Objective

Make the v2 school-class-search `name` filter case-insensitive. The nested
`school.name` join filter (from the required `school` query param) is an
identifier used to scope the search to one school, not a free-text search
field, and stays case-sensitive and exact (see D9). Leave the
already-case-insensitive `get()` endpoint untouched (it just needs Task 005's
index).

## Context

See [`../context.md`](../context.md) for full background. This task is
structurally identical to Task 003 (`workgroup.py`) — same duplicated
`_str_filter` pattern exists in `school_class.py`.

Relevant decisions: [`../decisions.md`](../decisions.md) D1, D5, D9
(school/OU identifiers, including the `school.name` join filter here, stay
case-sensitive and exact — only free-text `name` search becomes
case-insensitive).

Current code (`kelvin-api/ucsschool/kelvin/routers/v2/school_class.py`):

```python
def _str_filter(field: str, value: str) -> Filter:
    """Create a string filter with wildcard support and proper escaping."""
    return (
        make_wildcard_filter(field, value)
        if "*" in value
        else Filter(field=field, op=Operator.EQ, value=value)
    )
```

`search()` (~lines 145-168):
```python
clauses = [Filter(field="school.name", op=Operator.EQ, value=school)]
if class_name:
    clauses.append(_str_filter("name", f"{school}-{class_name}"))
```
with the `school` param docstring also reading "case sensitive, exact match,
required".

`get()` (lines ~171-195) **already** uses:
```python
Filter(field="name", op=Operator.MATCHES_CI, value=full_name)
```
— leave unchanged.

## Scope

- `kelvin-api/ucsschool/kelvin/routers/v2/school_class.py` only.
- **Update (Task 014 landed early):** `_str_filter` is no longer defined
  locally in this file — it's imported as
  `from ._filters import str_filter as _str_filter` from the shared
  `kelvin-api/ucsschool/kelvin/routers/v2/_filters.py` module and already
  supports `case_insensitive`. No need to touch the function itself; only
  call sites change.
- Identical changes to Task 003, applied to this file:
  - ~~Mirror Task 001's `_str_filter` change~~ (already done, see above).
  - Pass `case_insensitive=True` for the `name` filter.
  - **Per D9 (reversed from an earlier direction):** the `school.name` join
    filter stays `Filter(field="school.name", op=Operator.EQ, value=school)`
    — case-sensitive, exact, no wildcard. The `school` query param docstring
    keeps its existing "case sensitive, exact match, required" wording.
  - Leave `get()` unchanged.

## Non-goals

Same as Task 003: `get()`'s filter construction; `Group.email`/
`Group.display_name`; the `school.name` join filter and `school` query param
docstring (per D9).

## Dependencies

None functionally; mirrors Tasks 001 and 003.

## Implementation steps

Identical to Task 003's steps 1-4 (post-resolution), applied to
`school_class.py` instead of `workgroup.py`.

## Acceptance criteria

- School-class search by `name` is case-insensitive.
- `school` OU scoping stays case-sensitive and exact (per D9).
- `get()` behavior is unchanged.

## Validation / test steps

- Task 010 unit tests for this file's `_str_filter`.
- Task 011 extends `kelvin-api/tests/test_route_school_class.py`'s search
  test with case-variation cases.

## Likely files to inspect or modify

- `kelvin-api/ucsschool/kelvin/routers/v2/school_class.py` (modify)
- `kelvin-api/tests/test_route_school_class.py` (read only here; edited in
  Task 011)

## Open questions / blockers

None.

## Notes for next session

- Implement alongside Task 003 if convenient — the diffs are nearly
  identical modulo the entity name (`class_name` vs `workgroup_name`).
