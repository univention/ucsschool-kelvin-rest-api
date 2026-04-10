---
title: 'Discover SQL Injection Exposure'
type: 'chore'
created: '2026-04-17T00:00:00Z'
status: 'done'
route: 'one-shot'
---

# Discover SQL Injection Exposure

## Intent

**Problem:** We need a concrete assessment of SQL injection exposure in the repository, focused on real query execution paths.

**Approach:** Review SQL construction patterns and execution boundaries, then harden any interpolation hotspots with parameter binding.

## Suggested Review Order

- See the exact hardening where SQL text now uses bind parameters.
  [env.py:39](../../alembic/env.py#L39)

- Confirm lock release path was hardened consistently.
  [env.py:60](../../alembic/env.py#L60)

- Read the complete discovery evidence and risk rationale.
  [sql-injection-discovery.md:1](sql-injection-discovery.md#L1)
