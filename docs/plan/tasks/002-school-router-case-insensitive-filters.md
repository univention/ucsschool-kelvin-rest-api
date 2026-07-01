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
- **Update (Task 014 landed early):** `_str_filter` is no longer defined
  locally in this file. It's imported as
  `from ._filters import str_filter as _str_filter` from the new shared
  module `kelvin-api/ucsschool/kelvin/routers/v2/_filters.py`, and already
  has the `case_insensitive` parameter (added as part of Task 001). Skip the
  "copy `_str_filter`" step below — only the call-site changes remain.
- Update `search()`'s call site to pass `case_insensitive=True`.
- Switch `school_get` and `school_exists`'s direct `Filter(..., EQ, ...)` to
  `make_wildcard_filter("name", school_name, case_insensitive=True)` (needs
  `make_wildcard_filter` imported from `ucsschool_objects` again in this
  file — it was removed when the local `_str_filter` that used it was
  hoisted out).

## Non-goals

- Any change to `query_filter.py`/`query.py` — already capable.
- Anything about `School.display_name` or other School fields not in scope
  per `../decisions.md` D2.

## Dependencies

None functionally, but do Task 001 first for a consistent reference pattern.

## Implementation steps

1. ~~Copy Task 001's updated `_str_filter` into this file verbatim (same
   signature/body).~~ Already done — see Scope note above. Just re-import
   `make_wildcard_filter` from `ucsschool_objects` for steps 2-3 below.
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
