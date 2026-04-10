---
title: 'Immutable domain models with frozenset collections'
type: 'refactor'
created: '2026-04-16'
status: 'done'
route: 'one-shot'
---

## Superseded Note

This artifact is partially superseded by commit `433b6e0c75d9d351438c522237048b0f16a40dc7`, which intentionally reintroduced mutable relation attributes (`set`) in domain models.

## Spec Change Log

- 2026-04-23: Superseded in part by mutable-relation follow-up (`433b6e0c75d9d351438c522237048b0f16a40dc7`) and subsequent manager/mapping/test alignment.

## Intent

**Problem:** Domain model dataclasses were mutable (`frozen=False`) and used `tuple` for collection fields, meaning callers could accidentally mutate instances or rely on ordering that has no semantic meaning.

**Approach:** Add `frozen=True` to all domain dataclasses and replace every `tuple[X, ...]` collection field with `frozenset[X]`. Replace `@cached_property` (incompatible with frozen dataclasses) with plain `@property`. Update the SQLAlchemy mapping layer, test helpers, and all test files to match.

## Suggested Review Order

1. [models.py](../../ucsschool-objects/src/ucsschool_objects/core/domain/models.py) — core change: frozen dataclasses + frozenset fields, `@property` replaces `@cached_property`
2. [mapping.py](../../ucsschool-objects/src/ucsschool_objects/core/adapters/sqlalchemy/mapping.py) — frozenset constructors replace tuple() calls
3. [model_builders.py](../../ucsschool-objects/tests/core/domain/helpers/model_builders.py) — test helper updated
4. [test_user_model_groups.py](../../ucsschool-objects/tests/core/domain/test_user_model_groups.py) — frozenset literals, `==` equality instead of `is` for property cache test
5. [test_user_model_primary_school.py](../../ucsschool-objects/tests/core/domain/test_user_model_primary_school.py) — frozenset literals
6. [test_school_membership_roles.py](../../ucsschool-objects/tests/core/domain/test_school_membership_roles.py) — frozenset literal
7. [test_user_reader_membership_projections.py](../../ucsschool-objects/tests/core/contracts/test_user_reader_membership_projections.py) — `next(iter(...))` replaces index access
