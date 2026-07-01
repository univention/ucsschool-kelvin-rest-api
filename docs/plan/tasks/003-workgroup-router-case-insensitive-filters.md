# Task 003 — Workgroup router: case-insensitive filters

**Status:** not started

## Objective

Make the v2 workgroup-search `name` filter and the nested `school.name` join
filter case-insensitive; leave the already-case-insensitive `get()` endpoint
untouched (it just needs Task 005's index).

## Context

See [`../context.md`](../context.md) for full background, and Task 001 for
the reference `_str_filter` change.

Relevant decisions: [`../decisions.md`](../decisions.md) D1, D5, D9 (accept
`*` as a wildcard consistently, including in the `school.name` join filter).

Current code (`kelvin-api/ucsschool/kelvin/routers/v2/workgroup.py`):

```python
def _str_filter(field: str, value: str) -> Filter:
    """Create a string filter with wildcard support and proper escaping."""
    return (
        make_wildcard_filter(field, value)
        if "*" in value
        else Filter(field=field, op=Operator.EQ, value=value)
    )
```

`search()` (lines ~160-186):
```python
clauses = [Filter(field="school.name", op=Operator.EQ, value=school)]
if workgroup_name:
    clauses.append(_str_filter("name", f"{school}-{workgroup_name}"))
```
with the `school` query param docstring currently reading: "Name of school
(``OU``) in which to search for workgroups (**case sensitive, exact match,
required**)."

`get()` (lines 189-213) **already** uses:
```python
Filter(field="name", op=Operator.MATCHES_CI, value=full_name)
```
— leave this endpoint's filter construction unchanged.

## Scope

- `kelvin-api/ucsschool/kelvin/routers/v2/workgroup.py` only.
- Mirror Task 001's `_str_filter` change.
- Switch the `school.name` join filter in `search()` to
  `make_wildcard_filter("school.name", school, case_insensitive=True)`.
- Pass `case_insensitive=True` for the `name` filter in `search()`.
- Update the stale "case sensitive, exact match, required" docstring text for
  the `school` query param (drop "case sensitive").
- Leave `get()` completely unchanged.

## Non-goals

- `get()`'s filter construction (already correct, just needs indexing).
- `Group.email`/`Group.display_name` (out of scope per D2).

## Dependencies

None functionally, but mirrors Task 001's pattern — do that one first.

## Implementation steps

1. Copy Task 001's updated `_str_filter` into this file.
2. Update `search()`:
   ```python
   clauses = [make_wildcard_filter("school.name", school, case_insensitive=True)]
   if workgroup_name:
       clauses.append(_str_filter("name", f"{school}-{workgroup_name}", case_insensitive=True))
   ```
3. Update the `school` query param's docstring to remove "case sensitive,"
   and reflect that `*` now acts as a wildcard here too (per D9) — e.g.
   "Name of school (``OU``) in which to search for workgroups (exact match,
   ``*`` can be used for an inexact search, required)."
4. Do not touch `get()`.

## Acceptance criteria

- Workgroup search by `name` and by `school` OU is case-insensitive.
- `get()` behavior is unchanged (still case-insensitive as before).
- Docstring no longer claims case-sensitivity where it no longer applies.

## Validation / test steps

- Task 010 unit tests for this file's `_str_filter`.
- Task 011 extends `kelvin-api/tests/test_route_workgroup.py`'s search test
  with case-variation cases.

## Likely files to inspect or modify

- `kelvin-api/ucsschool/kelvin/routers/v2/workgroup.py` (modify)
- `kelvin-api/tests/test_route_workgroup.py` (read only here; edited in
  Task 011)

## Open questions / blockers

None.

## Notes for next session

- This task is structurally identical to Task 004 (`school_class.py`) —
  consider implementing both together once the pattern is settled here.
