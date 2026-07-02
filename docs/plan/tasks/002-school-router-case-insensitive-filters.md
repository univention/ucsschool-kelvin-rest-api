# Task 002 — School router: case-insensitive filters

**Status:** done

## Objective

Make the v2 school-search `name` filter case-insensitive. `school_get`/
`school_exists` are exact-lookup-by-identifier endpoints and stay
case-sensitive and exact — unchanged by this task (see D9).

## Context

See [`../context.md`](../context.md) for full background, and Task 001
(`docs/plan/tasks/001-user-router-case-insensitive-filters.md`) for the
reference `_str_filter` change this task mirrors.

Relevant decisions: [`../decisions.md`](../decisions.md) D1, D5, D9 (school/OU
identifiers, including `school_get`/`school_exists`, stay case-sensitive and
exact — only free-text `name` search becomes case-insensitive).

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
- `school_get`/`school_exists` are **out of scope** (per D9, reversed from an
  earlier direction) — their `Filter(field="name", op=Operator.EQ,
  value=school_name)` construction stays exactly as it is today. No
  `make_wildcard_filter` import is needed in this file for them.

## Non-goals

- Any change to `query_filter.py`/`query.py` — already capable.
- Anything about `School.display_name` or other School fields not in scope
  per `../decisions.md` D2.
- `school_get`/`school_exists` (per D9 — these are exact-lookup-by-identifier
  endpoints, not free-text search, and stay case-sensitive/exact).

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
3. Leave `school_get` and `school_exists` untouched (per D9 — they're
   exact-lookup-by-identifier endpoints, not free-text search).

## Acceptance criteria

- School-name list search is case-insensitive, wildcard behavior preserved
  otherwise.
- `school_get`/`school_exists` remain case-sensitive, exact-match lookups —
  byte-for-byte unchanged from before this story (per D9).

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
