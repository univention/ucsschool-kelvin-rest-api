# Task 014 — Optional: hoist duplicated `_str_filter` into a shared module

**Status:** done (landed early, ahead of Tasks 002-004)

## Objective

(Optional, nice-to-have — not required for this story.) Reduce duplication
by hoisting the now-4-times-duplicated `_str_filter` function (identical in
`user.py`, `school.py`, `workgroup.py`, `school_class.py` after Tasks
001-004) into a single shared module.

## Context

See [`../context.md`](../context.md). `user.py`/`school.py`/`workgroup.py`/
`school_class.py` each define a byte-for-byte identical private `_str_filter`
function today, and Tasks 001-004 each independently add the same
`case_insensitive` parameter to their own copy. This is pre-existing
duplication in the codebase (not introduced by this story), and this task is
purely optional cleanup.

## Scope

- After Tasks 001-004 are complete and their `_str_filter` implementations
  have converged on an identical shape, create a shared module (e.g.
  `kelvin-api/ucsschool/kelvin/routers/v2/_filters.py`) containing a single
  `_str_filter` (or a more appropriately-named public function, since it'd
  now be shared/imported) implementation.
- Update all 4 router files to import from the shared module instead of
  defining their own copy.

## Non-goals

- Any behavior change — this is a pure refactor, zero functional difference.
- Blocking the rest of this story on this task — it is explicitly optional
  and should not delay Tasks 001-013.

## Dependencies

Tasks 001-004 (their implementations must converge first).

## Implementation steps

1. Confirm all 4 `_str_filter` implementations are identical post Tasks
   001-004.
2. Create the shared module with the single implementation.
3. Update imports in all 4 router files; remove the 4 duplicate definitions.
4. Run the full test suite (Tasks 009-011's tests plus any pre-existing
   tests) to confirm zero behavior change.

## Acceptance criteria

- Exactly one `_str_filter` implementation exists in the codebase.
- All existing tests (pre- and post- Tasks 001-013) still pass unchanged.

## Validation / test steps

- Full re-run of the test suites from Tasks 009, 010, 011, 012.

## Likely files to inspect or modify

- New: `kelvin-api/ucsschool/kelvin/routers/v2/_filters.py` (or similar name)
- `kelvin-api/ucsschool/kelvin/routers/v2/user.py`, `school.py`,
  `workgroup.py`, `school_class.py` (remove duplicated function, add import)

## Open questions / blockers

None — purely optional.

## Notes for next session

- **Deviation from plan:** this was done right after Task 001, not after
  Tasks 001-004 as originally planned. It was safe to do early because
  Task 001's `_str_filter(field, value, *, case_insensitive=False)` is a
  strict superset of the old 3-file implementation (default
  `case_insensitive=False` reproduces the old behavior exactly), so hoisting
  it doesn't change behavior for `school.py`/`workgroup.py`/
  `school_class.py`, which still call it without `case_insensitive=True`.
- Shared module: `kelvin-api/ucsschool/kelvin/routers/v2/_filters.py`,
  public function `str_filter`. All 4 router files import it as
  `from ._filters import str_filter as _str_filter` to keep existing
  `_str_filter(...)` call sites unchanged.
- Side effect: the now-unused `make_wildcard_filter` import was removed from
  `school.py`, `workgroup.py`, and `school_class.py` (it's only used inside
  `_filters.py` now). Tasks 002-004 each re-introduce a *direct*
  `make_wildcard_filter` call (for `school_get`/`school_exists` or the
  `school.name` join filter) and will need to re-import it — this is called
  out in each of those task files now.
- Nothing left to do for this task.
