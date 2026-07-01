# Task 002 — School router: case-insensitive filters

**Status:** not started

## Objective

Make the v2 school-search `name` filter, and the exact-lookup endpoints
`school_get`/`school_exists`, case-insensitive.

## Context

See [`../context.md`](../context.md) for full background, and Task 001
(`docs/plan/tasks/001-user-router-case-insensitive-filters.md`) for the
reference `_str_filter` change this task mirrors.

Relevant decisions: [`../decisions.md`](../decisions.md) D1, D5, D9 (accept
`*` as a wildcard consistently, including in `school_get`/`school_exists`).

Current code (`kelvin-api/ucsschool/kelvin/routers/v2/school.py`):

```python
def _str_filter(field: str, value: str) -> Filter:
    """Create a string filter with wildcard support and proper escaping."""
    return (
        make_wildcard_filter(field, value)
        if "*" in value
        else Filter(field=field, op=Operator.EQ, value=value)
    )
```

used in `search()` (line ~114):
```python
query = SearchQuery(where=_str_filter("name", name_filter)) if name_filter else None
```

and directly in `school_get` (line 135) / `school_exists` (line 159):
```python
Filter(field="name", op=Operator.EQ, value=school_name)
```

## Scope

- `kelvin-api/ucsschool/kelvin/routers/v2/school.py` only.
- Mirror Task 001's `_str_filter` signature/body change exactly.
- Update `search()`'s call site to pass `case_insensitive=True`.
- Switch `school_get` and `school_exists`'s direct `Filter(..., EQ, ...)` to
  `make_wildcard_filter("name", school_name, case_insensitive=True)`.

## Non-goals

- Any change to `query_filter.py`/`query.py` — already capable.
- Anything about `School.display_name` or other School fields not in scope
  per `../decisions.md` D2.

## Dependencies

None functionally, but do Task 001 first for a consistent reference pattern.

## Implementation steps

1. Copy Task 001's updated `_str_filter` into this file verbatim (same
   signature/body).
2. Update `search()`'s call site:
   ```python
   query = SearchQuery(where=_str_filter("name", name_filter, case_insensitive=True)) if name_filter else None
   ```
3. Update `school_get` and `school_exists` (per D9 — `*` is accepted as a
   wildcard here too, consistent with the rest of the story):
   ```python
   SearchQuery(where=make_wildcard_filter("name", school_name, case_insensitive=True))
   ```
   (import `make_wildcard_filter` if not already imported in this file — it
   already is, per the existing `_str_filter`).

## Acceptance criteria

- School-name list search is case-insensitive, wildcard behavior preserved
  otherwise.
- `school_get`/`school_exists` find a school regardless of case in the path
  parameter, and treat a literal `*` in `school_name` as a wildcard (per D9).

## Validation / test steps

- Task 010 unit tests (`test_route_v2_filters.py`) for `_str_filter` in this
  file.
- Task 011 extends `kelvin-api/tests/test_route_school.py`'s search test with
  case-variation cases.

## Likely files to inspect or modify

- `kelvin-api/ucsschool/kelvin/routers/v2/school.py` (modify)
- `kelvin-api/tests/test_route_school.py` (read, for existing test shape —
  actual edits happen in Task 011)

## Open questions / blockers

None.

## Notes for next session

- Once this task is done, update its status here and in `../README.md`.
