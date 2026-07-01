# Task 004 — School-class router: case-insensitive filters

**Status:** not started

## Objective

Make the v2 school-class-search `name` filter and the nested `school.name`
join filter case-insensitive; leave the already-case-insensitive `get()`
endpoint untouched (it just needs Task 005's index).

## Context

See [`../context.md`](../context.md) for full background. This task is
structurally identical to Task 003 (`workgroup.py`) — same duplicated
`_str_filter` pattern exists in `school_class.py`.

Relevant decisions: [`../decisions.md`](../decisions.md) D1, D5, D9 (accept
`*` as a wildcard consistently, including in the `school.name` join filter).

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
- Identical changes to Task 003, applied to this file:
  - Mirror Task 001's `_str_filter` change.
  - Switch `school.name` join filter to
    `make_wildcard_filter("school.name", school, case_insensitive=True)`.
  - Pass `case_insensitive=True` for the `name` filter.
  - Update the stale "case sensitive, exact match, required" docstring text.
  - Leave `get()` unchanged.

## Non-goals

Same as Task 003: `get()`'s filter construction; `Group.email`/
`Group.display_name`.

## Dependencies

None functionally; mirrors Tasks 001 and 003.

## Implementation steps

Identical to Task 003's steps 1-4 (post-resolution), applied to
`school_class.py` instead of `workgroup.py`.

## Acceptance criteria

- School-class search by `name` and by `school` OU is case-insensitive.
- `get()` behavior is unchanged.
- Docstring updated.

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
