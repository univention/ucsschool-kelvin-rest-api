# Task 013 — Performance evaluation evidence

**Status:** not started

## Objective

Produce concrete before/after performance evidence (actual query timings, not
just plan shape) satisfying the ticket's "Query performance is evaluated, for
example with `EXPLAIN ANALYZE`" acceptance criterion — without creating a new
permanent documentation artifact that will go stale.

## Context

See [`../context.md`](../context.md) requirements list and
[`../decisions.md`](../decisions.md) (this isn't a separate architectural
decision, but follows the same "avoid unnecessary permanent artifacts"
instinct applied elsewhere in this plan, e.g. D6/D7's preference for
lightweight mechanisms).

This task deliberately reuses Task 012's seeded dataset and query set rather
than creating a new one from scratch.

## Scope

- Using the same seeded Postgres dataset and representative queries from
  Task 012, manually run `EXPLAIN ANALYZE` (not just `EXPLAIN`) **before**
  the migrations are applied (on a fresh, unindexed schema) and **after**
  (post-migration), capturing actual execution timings for at least the
  worst-case pattern (leading-wildcard `ILIKE` on a large table).
- Paste this before/after comparison into the pull request description as
  narrative evidence, once, during development.
- Task 012's automated `EXPLAIN (FORMAT JSON)` assertions (index-scan
  present, no seq-scan) are the durable, re-runnable proof; this task's
  manual `EXPLAIN ANALYZE` timings are a one-time, human-readable
  illustration of the actual speedup — not committed as a permanent file.

## Non-goals

- A new permanent docs file (e.g. under `docs/`) with performance numbers
  that will drift out of date as data grows — explicitly avoided.
- Automating `EXPLAIN ANALYZE` timing assertions in CI (timings are
  inherently environment-dependent and flaky as a hard test assertion; plan
existence/`Seq Scan` absence, per Task 012, is the right thing to assert in
  CI — actual timings are for human-readable evidence only).

## Dependencies

Task 012 (reuses its seeded dataset/queries).

## Implementation steps

1. Using the same test setup as Task 012 (or a local manual run against
   `dev/docker-compose.yaml`'s Postgres with the same seeded row counts),
   run `EXPLAIN ANALYZE` for a representative leading-wildcard `ILIKE` query
   against, e.g., `user.name`:
   - **Before**: on a schema without the Task 005 migration applied (or with
     the index dropped) — expect a `Seq Scan` with a real elapsed time
     proportional to table size.
   - **After**: with the migration applied — expect a `Bitmap Index Scan`/
     `Index Scan` with a materially lower elapsed time.
2. Capture both `EXPLAIN ANALYZE` outputs (plan + actual timing) verbatim.
3. Include this before/after pair in the pull request description when the
   overall change is submitted for review — not as a new file in the repo.

## Acceptance criteria

- A concrete before/after `EXPLAIN ANALYZE` comparison exists and shows a
  measurable improvement (seq scan → index scan, with a real timing
  reduction) for at least one representative query.
- This evidence is attached to the PR description, not committed as a new
  permanent file.

## Validation / test steps

- No new automated test — this task's "test" is the manual capture described
  above. Task 012's automated assertions remain the durable regression
  protection.

## Likely files to inspect or modify

None (no code changes) — this task only produces evidence to attach to a PR
description, using the same environment/dataset as Task 012.

## Open questions / blockers

Blocked on Task 012 (needs its seeded dataset/migration setup to exist).

## Notes for next session

- If a future reviewer wants this evidence preserved more durably than a PR
  description (e.g. it gets buried after merge), reconsider adding a short,
  clearly-dated note — but default to the PR description per the "avoid
  unnecessary permanent artifacts" instinct unless asked otherwise.
