# Task 003 — Workgroup router: case-insensitive filters

**Status:** done

## Objective

Make the v2 workgroup-search `name` filter case-insensitive. The nested
`school.name` join filter (from the required `school` query param) is an
identifier used to scope the search to one school, not a free-text search
field, and stays case-sensitive and exact (see D9). Leave the
already-case-insensitive `get()` endpoint untouched (it just needs Task 005's
index).

## Context

See [`../context.md`](../context.md) for full background, and Task 001 for
the reference `_str_filter` change.

Relevant decisions: [`../decisions.md`](../decisions.md) D1, D5, D9
(school/OU identifiers, including the `school.name` join filter here, stay
case-sensitive and exact — only free-text `name` search becomes
case-insensitive).

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
- **Update (Task 014 landed early):** `_str_filter` is no longer defined
  locally in this file — it's imported as
  `from ._filters import str_filter as _str_filter` from the shared
  `kelvin-api/ucsschool/kelvin/routers/v2/_filters.py` module and already
  supports `case_insensitive`. No need to touch the function itself; only
  call sites change.
- Pass `case_insensitive=True` for the `name` filter in `search()`.
- **Per D9 (reversed from an earlier direction):** the `school.name` join
  filter in `search()` stays `Filter(field="school.name", op=Operator.EQ,
  value=school)` — case-sensitive, exact, no wildcard. The `school` query
  param docstring keeps its existing "case sensitive, exact match, required"
  wording. No `make_wildcard_filter` import is needed for this.
- Leave `get()` completely unchanged.

## Non-goals

- `get()`'s filter construction (already correct, just needs indexing).
- `Group.email`/`Group.display_name` (out of scope per D2).
- The `school.name` join filter and `school` query param docstring (per
  D9 — identifier used to scope the search, not a free-text search field).

## Dependencies

None functionally, but mirrors Task 001's pattern — do that one first.

## Implementation steps

1. ~~Copy Task 001's updated `_str_filter` into this file.~~ Already done —
   see Scope note above.
2. Update `search()`:
   ```python
   clauses = [Filter(field="school.name", op=Operator.EQ, value=school)]
   if workgroup_name:
       clauses.append(_str_filter("name", f"{school}-{workgroup_name}", case_insensitive=True))
   ```
3. Leave the `school` query param's docstring as-is (per D9, reversed from an
   earlier direction — it stays case-sensitive/exact, so the "case sensitive,
   exact match, required" wording still applies).
4. Do not touch `get()`.

## Acceptance criteria

- Workgroup search by `name` is case-insensitive.
- `school` OU scoping stays case-sensitive and exact (per D9).
- `get()` behavior is unchanged (still case-insensitive as before).

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
