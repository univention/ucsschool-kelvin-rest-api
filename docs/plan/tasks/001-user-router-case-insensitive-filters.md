# Task 001 — User router: case-insensitive filters + email wildcard/CI

**Status:** not started

## Objective

Make the v2 user-search filters for `name` (username), `schools.name`
(school), `firstname`, `lastname`, and `email` case-insensitive, and give
`email` wildcard (`*`) support it doesn't currently have — while leaving
`record_uid`/`source_uid` case-sensitive and unchanged.

## Context

See [`../context.md`](../context.md) for full background. This is the
reference implementation Tasks 002-004 mirror in their respective router
files — do this one first and get it right before copying the pattern.

Relevant decisions: [`../decisions.md`](../decisions.md) D1 (why switch to
case-insensitive), D4 (email gets wildcard + CI), D5 (opt-in
`case_insensitive` param, no global flip).

Current code (`kelvin-api/ucsschool/kelvin/routers/v2/user.py`):

```python
def _str_filter(field: str, value: str) -> Filter:
    """Create a string filter with wildcard support and proper escaping."""
    return (
        make_wildcard_filter(field, value)
        if "*" in value
        else Filter(field=field, op=Operator.EQ, value=value)
    )
```

and, in `_build_query` (lines 156-195):

```python
if name:
    clauses.append(_str_filter("name", name))
if school:
    clauses.append(_str_filter("schools.name", school))
if firstname:
    clauses.append(_str_filter("firstname", firstname))
if lastname:
    clauses.append(_str_filter("lastname", lastname))
if email:
    clauses.append(Filter(field="email", op=Operator.EQ, value=email))
if record_uid:
    clauses.append(_str_filter("record_uid", record_uid))
if source_uid:
    clauses.append(_str_filter("source_uid", source_uid))
```

## Scope

- `kelvin-api/ucsschool/kelvin/routers/v2/user.py` only.
- Add an opt-in `case_insensitive: bool = False` parameter to `_str_filter`.
- Update `_build_query` call sites for `name`, `schools.name`, `firstname`,
  `lastname` to pass `case_insensitive=True`.
- Replace the direct `email` `Filter(..., Operator.EQ, ...)` with
  `_str_filter("email", email, case_insensitive=True)`.
- Leave `record_uid`/`source_uid` calls unchanged (no `case_insensitive` arg,
  defaults to `False`).

## Non-goals

- `_udm_property_filters()`'s `CONTAINS`/digit branches — untouched.
- The UDM property **wildcard** branch (line 150,
  `make_wildcard_filter(field, value)`) — **do not touch until Q1 is
  resolved** (see `../context.md` Unresolved questions). If the stakeholder
  confirms it should also become case-insensitive, that's a one-line change
  here (`make_wildcard_filter(field, value, case_insensitive=True)`) but
  treat it as a separate decision, not bundled silently into this task.
- Any change to `query_filter.py`/`query.py` in `ucsschool-objects` — they
  already fully support everything needed here.
- `record_uid`/`source_uid` semantics.

## Dependencies

None (can start immediately). Tasks 002-004 mirror this task's pattern, so
finishing this first (even though there's no hard code dependency) makes
those faster and more consistent.

## Implementation steps

1. Confirm Q1 (UDM property wildcard case-sensitivity) with the stakeholder,
   or explicitly decide to defer it (leave UDM property filters
   case-sensitive) and note that in this task's "Notes for next session"
   section when done.
2. Update `_str_filter`'s signature and body. The critical correctness detail
   (D5): when `case_insensitive=True` and there is **no** `*` in `value`, do
   **not** fall back to `Operator.EQ` — route through `make_wildcard_filter`
   too, since a literal value with no `*` still produces a correctly-escaped
   pattern, and `MATCHES_CI` becomes an ILIKE-exact match. One correct shape:

   ```python
   def _str_filter(field: str, value: str, *, case_insensitive: bool = False) -> Filter:
       """Create a string filter with wildcard support and proper escaping."""
       if case_insensitive:
           return make_wildcard_filter(field, value, case_insensitive=True)
       if "*" in value:
           return make_wildcard_filter(field, value)
       return Filter(field=field, op=Operator.EQ, value=value)
   ```

3. Update the 4 `_str_filter` call sites in `_build_query` to pass
   `case_insensitive=True` (`name`, `schools.name`, `firstname`, `lastname`).
4. Replace the direct `email` filter construction with
   `_str_filter("email", email, case_insensitive=True)`.
5. Leave `record_uid`/`source_uid` calls exactly as they are today.

## Acceptance criteria

- Existing exact-match and wildcard search behavior is preserved for all
  fields except case-sensitivity (i.e., a search that matched before still
  matches, plus now also matches regardless of case).
- `email` search now accepts `*` wildcards and is case-insensitive.
- `record_uid`/`source_uid` filters are byte-for-byte unchanged in behavior.
- The no-wildcard + `case_insensitive=True` path produces `Operator.MATCHES_CI`
  (not `Operator.EQ`) — verified by Task 010's unit test.

## Validation / test steps

- Task 010 (`kelvin-api/tests/test_route_v2_filters.py`) unit-tests
  `_str_filter`/`_build_query` directly — run once that task exists.
- Task 011 extends the real E2E `test_search_filter` test in
  `kelvin-api/tests/test_route_user.py` with case-variation and email-wildcard
  cases — the load-bearing proof this actually works against Postgres.
- Manual smoke check: `uv run pytest ucsschool-objects/ --cov-config=ucsschool-objects/pyproject.toml`
  should still pass unchanged (this task doesn't touch that package).

## Likely files to inspect or modify

- `kelvin-api/ucsschool/kelvin/routers/v2/user.py` (modify)
- `kelvin-api/ucsschool/kelvin/routers/v2/school.py`,
  `workgroup.py`, `school_class.py` (read only, for the mirrored pattern in
  Tasks 002-004)

## Open questions / blockers

- **Q1** (see `../context.md`): whether `_udm_property_filters()`'s wildcard
  branch should also become case-insensitive. Default: leave untouched.

## Notes for next session

- If Q1 gets resolved as "yes, make it case-insensitive too", that's a
  one-line follow-up in `_udm_property_filters()` (line 150) — do it as part
  of finishing this task, not a separate task.
- Once this task is done, update its status here and in `../README.md`, then
  move to Task 002 (or start it in parallel — no hard dependency).
