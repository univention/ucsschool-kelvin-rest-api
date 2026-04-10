---
title: 'Extend Manager Protocol with create/modify/delete'
type: 'feature'
created: '2026-04-22'
status: 'in-review'
baseline_commit: 'c94eed051d5d1ff27fcb58044685a74e39fbecf7'
context: []
---

<frozen-after-approval reason="human-owned intent - do not modify unless human renegotiates">

## Intent

**Problem:** The current Manager port only supports read-side operations and cannot express create, modify, and delete behavior needed by upcoming use cases.

**Approach:** Extend the existing Manager protocol contract by adding create, modify, and delete methods, with modify represented as JSONPath-based operations and target object resolution by public_id.

## Boundaries & Constraints

**Always:** Keep this change protocol-first; keep method contracts async; keep modify and delete target identification via public_id; represent object modification using JSONPath operations.

**Ask First:** Implementing concrete adapter logic for these write methods in this same change if protocol extension alone is not enough.

**Never:** Leak persistence-layer details into the domain port; model modification as flat field assignment that bypasses JSONPath semantics; change get/search behavior.

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|--------------|---------------------------|----------------|
| CREATE_HAPPY_PATH | Valid domain object payload | create returns created domain object | N/A |
| MODIFY_HAPPY_PATH | Existing public_id + JSONPath operations | modify returns updated domain object with operations applied | Adapter raises domain errors if operation cannot be applied |
| DELETE_HAPPY_PATH | Existing public_id | delete completes for targeted object | N/A |
| MODIFY_UNKNOWN_ID | Unknown public_id + JSONPath operations | object is not modified | Adapter raises NotFound |
| MODIFY_INVALID_JSONPATH | Existing object + malformed/unsupported JSONPath | object is not modified | Adapter raises domain validation error |

</frozen-after-approval>

## Code Map

- `ucsschool-objects/src/ucsschool_objects/core/domain/ports/manager.py` -- Manager protocol contract to extend.
- `ucsschool-objects/src/ucsschool_objects/core/adapters/sqlalchemy/mapping.py` -- Domain mapping aligned with mutable set-based relation fields.
- `ucsschool-objects/src/ucsschool_objects/core/adapters/sqlalchemy/managers/user_manager.py` -- Membership build path aligned to `set[SchoolMembership]` inputs.
- `ucsschool-objects/src/ucsschool_objects/core/adapters/sqlalchemy/mapping.py` -- `to_user` now emits keyed membership dictionaries (`dict[school_public_id, SchoolMembership]`).
- `ucsschool-objects/src/ucsschool_objects/core/adapters/sqlalchemy/managers/user_manager.py` -- User create path validates that each `school_memberships` key matches the related membership school's `public_id`.
- `ucsschool-objects/tests/core/test_ports.py` -- Protocol signature tests.
- `ucsschool-objects/tests/core/domain/` -- Domain model tests updated from `frozenset` to `set` relation expectations.
- `ucsschool-objects/tests/core/contracts/test_manager_create_contracts.py` -- Manager create contract fixtures aligned to set-based relation payloads.
- `ucsschool-objects/tests/core/contracts/contract_test_support.py` -- Optional local protocol helpers used by tests.

## Tasks & Acceptance

**Execution:**
- [x] `ucsschool-objects/src/ucsschool_objects/core/domain/ports/manager.py` -- Add async create/modify/delete to Manager protocol; define modify input as JSONPath-based operations and identify target object by public_id -- Establishes write-side contract boundary.
- [x] `ucsschool-objects/tests/core/test_ports.py` -- Add type-level assertions for new Manager methods -- Prevents signature drift.
- [x] `ucsschool-objects/tests/core/contracts/contract_test_support.py` -- Align any helper protocols only if needed for typing parity -- Reviewed; no local manager protocol remains in this file, so no parity update was required.
- [x] `ucsschool-objects/src/ucsschool_objects/core/adapters/sqlalchemy/mapping.py` and `ucsschool-objects/src/ucsschool_objects/core/adapters/sqlalchemy/managers/user_manager.py` -- Refactor `User.school_memberships` flow from set-based handling to keyed dictionary semantics and enforce key-to-school `public_id` consistency.
- [x] `ucsschool-objects/tests/core/contracts/test_manager_create_contracts.py`, `ucsschool-objects/tests/core/contracts/test_manager_load_spec_projections.py`, `ucsschool-objects/tests/core/domain/test_user_model_groups.py`, `ucsschool-objects/tests/core/domain/test_user_model_roles.py`, `ucsschool-objects/tests/core/domain/test_user_model_primary_school.py`, `ucsschool-objects/tests/core/domain/helpers/model_builders.py` -- Update fixtures/assertions/types to keyed membership dictionaries.

**Acceptance Criteria:**
- Given the Manager protocol, when inspecting its API surface, then create, modify, and delete methods exist.
- Given modify input, when targeting an object, then public_id is used as identifier.
- Given modify semantics, when describing update operations, then operations are JSONPath-based.
- Given existing readers, when running current read/search tests, then no read behavior regresses.

## Spec Change Log

- 2026-04-23: Follow-up to commit `433b6e0c75d9d351438c522237048b0f16a40dc7` (mutable relation attributes) applied. SQLAlchemy mapping and user manager membership typing were updated from `frozenset` to `set`, domain relation hashing was normalized via `frozenset(...)` in `SchoolMembership.__hash__`, and affected domain/contract tests were migrated to set-based fixtures/assertions.
- 2026-04-23: Verification rerun completed with requested commands: `uv run pytest ucsschool-objects/ --cov-config=ucsschool-objects/pyproject.toml` and `uv run mypy ucsschool-objects`.
- 2026-04-23: Follow-up to commit `568342257d6565c6059078dbb2af9312c62999a1` completed. Manager/mapping/test paths were aligned to `User.school_memberships: dict[UUID, SchoolMembership]`, with explicit invariant that dictionary keys are the related school `public_id`.
- 2026-04-23: Verification rerun after keyed-membership refactor: `uv run mypy ucsschool-objects` passed; `uv run pytest ucsschool-objects/ --cov-config=ucsschool-objects/pyproject.toml` executed with 401 passing tests but still fails repository coverage gate (`fail-under=100`, measured 98.66%).

## Design Notes

- Keep mutation representation transport-agnostic at the port boundary so adapters can implement JSONPath application internally.
- This spec intentionally defines contract shape first; implementation strategy in adapters can be phased.

## Verification

**Commands:**
- `uv run pytest -q ucsschool-objects/tests/core/test_ports.py` -- expected: Manager protocol type assertions pass.
- `uv run pytest -q ucsschool-objects/tests/core/contracts/test_manager_contracts.py` -- expected: read/search contract tests still pass.
- `uv run pytest ucsschool-objects/ --cov-config=ucsschool-objects/pyproject.toml` -- expected: full `ucsschool-objects` suite passes.
- `uv run mypy ucsschool-objects` -- expected: no type errors.

**Latest Run Results (2026-04-23):**
- `uv run mypy ucsschool-objects` -- passed (`Success: no issues found in 50 source files`).
- `uv run pytest ucsschool-objects/ --cov-config=ucsschool-objects/pyproject.toml` -- functional tests passed (`401 passed`), but overall command exits non-zero due to configured coverage gate: `Required test coverage of 100.0% not reached. Total coverage: 98.66%`.
