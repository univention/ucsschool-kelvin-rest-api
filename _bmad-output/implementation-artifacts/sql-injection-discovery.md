# SQL Injection Discovery Report

Date: 2026-04-17
Scope: Targeted static review of selected SQL construction and query execution paths listed below.

## Executive Summary

- No direct SQL injection vulnerability was found in the reviewed user-facing query paths.
- Primary read/query flow in ucsschool-objects uses SQLAlchemy expression construction with typed field maps, not string-built SQL.
- One defense-in-depth hardening was applied in Alembic migration lock SQL to replace string interpolation with bind parameters.

## What Was Reviewed

1. Query expression model and translation:
   - ucsschool-objects/src/ucsschool_objects/core/domain/query.py
   - ucsschool-objects/src/ucsschool_objects/core/adapters/sqlalchemy/query_filter.py
2. SQLAlchemy reader execution paths:
   - ucsschool-objects/src/ucsschool_objects/core/adapters/sqlalchemy/readers.py
3. Raw SQL text usage:
   - alembic/env.py

## What Was Not Reviewed

- Full repository-wide SQL path enumeration outside the files listed in this report.
- Third-party dependencies and generated/vendor content.
- Runtime-only query construction that is not visible in static source paths.

## Findings

### 1. Query filter translation is parameterized by design (No issue)

The search layer builds SQLAlchemy expression trees (`column == value`, `column.in_(...)`, `column.ilike(...)`) from a constrained domain model:

- Allowed filter fields are constrained by explicit `_FIELD_MAP` dictionaries.
- Operators are constrained by `Operator` enum and validated before expression generation.
- User values are passed as expression values, which SQLAlchemy binds as parameters.

Risk rating: Low

### 2. Reader search/get methods execute composed Select statements (No issue)

Readers build `select(...)` statements and apply predicates/sort via helper functions. There is no string concatenation of SQL fragments in these read paths.

Risk rating: Low

### 3. Migration advisory-lock SQL used string interpolation (Hardened)

Alembic lock/unlock previously used `text(f"...")` with an internal numeric lock id. Although input was not user-controlled, this pattern is less robust against future refactors.

Applied change:

- `SELECT pg_try_advisory_lock(:lock_id)` with parameter dict
- `SELECT pg_advisory_unlock(:lock_id)` with parameter dict

Risk rating before change: Low (not user-controlled)
Risk rating after change: Very Low

## Recommended Ongoing Guardrails

- Prefer SQLAlchemy expressions and bound parameters in all database code.
- Treat `text(...)` plus interpolation as a prohibited pattern unless a trusted constant is unavoidable.
- Add or keep static checks in review for `text(f"` and SQL keyword interpolation patterns.

## Conclusion

In the reviewed paths, SQL usage appears safe from practical SQL injection, and the one interpolation hotspot was hardened to parameter binding. This is not an exhaustive repository-wide guarantee.
