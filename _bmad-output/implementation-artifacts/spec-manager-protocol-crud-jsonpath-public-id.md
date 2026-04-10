---
title: 'Extend Manager Protocol with create/modify/delete'
type: 'feature'
created: '2026-04-22T00:00:00Z'
status: 'done'
baseline_commit: 'c18ec4806c8f805c525a357caeeafebd442aee2f'
context: []
---

<frozen-after-approval reason="human-owned intent - do not modify unless human renegotiates">

## Intent

**Problem:** The current Manager contract is read-only and cannot express object lifecycle operations required by downstream layers.

**Approach:** Extend the domain Manager protocol to define create, modify, and delete operations, with modify expressed via JSONPath patches and target resolution by public UUID.

## Boundaries & Constraints

**Always:** Keep the initial change at the protocol layer first; keep async signatures; keep object identification by public_id for modify/delete; type annotate JSONPath-based modification inputs clearly; preserve existing get/search behavior unchanged.

**Ask First:** Changing concrete SQLAlchemy manager implementations in this step if protocol-only expansion is insufficient for your immediate branch goals.

**Never:** Introduce persistence-specific details into the domain port; introduce mutation semantics that bypass public_id targeting; replace JSONPath with field-name-only patch semantics.

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|--------------|---------------------------|----------------|
| CREATE_HAPPY_PATH | Valid domain object instance | Manager.create returns created domain object | N/A |
| MODIFY_HAPPY_PATH | Existing public_id + one or more JSONPath patch operations | Manager.modify returns updated domain object reflecting all valid patches | Concrete adapters raise domain errors on invalid operations |
| DELETE_HAPPY_PATH | Existing public_id | Manager.delete completes successfully | N/A |
| MODIFY_MISSING_OBJECT | Unknown public_id + patch operations | No updated object returned | Concrete adapters raise NotFound |
| MODIFY_INVALID_JSONPATH | Existing public_id + invalid JSONPath expression | No partial silent mutation | Concrete adapters raise domain-level validation error |

</frozen-after-approval>

## Code Map

- `ucsschool-objects/src/ucsschool_objects/core/domain/ports/manager.py` -- Primary protocol contract to extend.
- `ucsschool-objects/tests/core/contracts/test_manager_contracts.py` -- Contract-level verification of manager `get`/`search` behavior across all manager implementations.
- `ucsschool-objects/tests/core/domain/helpers/model_builders.py` -- Domain model fixtures used by equality/hash tests; updated for explicit required `Group` attributes.
- `ucsschool-objects/tests/core/domain/test_model_validation.py` -- Validation helper constructors updated for explicit required relation attributes.
- `ucsschool-objects/tests/core/domain/test_user_model_identity_semantics.py` -- Identity/hash semantics tests updated for explicit required `Group`/`User` relation attributes.

## Tasks & Acceptance

**Execution:**
- [x] `ucsschool-objects/src/ucsschool_objects/core/domain/ports/manager.py` -- Typed async `create`, `modify`, and `delete` methods are present with JSONPath operations and `public_id` targeting.
- [x] `ucsschool-objects/tests/core/contracts/test_manager_contracts.py` -- Contract tests continue to verify unchanged `get`/`search` behavior for all SQLAlchemy managers.
- [x] `ucsschool-objects/tests/core/domain/helpers/model_builders.py` -- Added explicit `Group` relation attributes (`allowed_email_senders_users`, `allowed_email_senders_groups`, `member_roles`, `school`) to reflect required constructor fields after c18 model changes.
- [x] `ucsschool-objects/tests/core/domain/test_model_validation.py` -- Added explicit relation attributes (`UNLOADED` where intentional) for `_group` and `_user` helper constructors.
- [x] `ucsschool-objects/tests/core/domain/test_user_model_identity_semantics.py` -- Updated direct `Group`/`User` constructions to pass explicit required relation attributes.

**Acceptance Criteria:**
- Given the Manager protocol, when reading method definitions, then create/modify/delete are present with async signatures.
- Given modify, when providing a target object identifier, then the identifier parameter is public_id (UUID).
- Given modify semantics, when defining patch input, then patches are represented as JSONPath-based operations rather than ad hoc flat field updates.
- Given existing read behavior, when running contract-related tests, then get/search behavior remains unchanged.

## Spec Change Log

- 2026-04-22: Port signature aligned to domain-model-based `create(data: ManagerT) -> None` in `manager.py` (commit `fdde626f834c8b85a72cc8ed2eab7b15b0acf2ee`).
- 2026-04-22: Follow-up for domain model required-field changes from `c18ec4806c8f805c525a357caeeafebd442aee2f` completed by updating domain test helpers and identity tests to pass explicit required relation attributes and keep intentional unloaded relations explicit via `UNLOADED`.
- 2026-04-23: Group manager sender resolution switched from name-based lookup to `public_id`-based lookup for `allowed_email_senders_users` and `allowed_email_senders_groups`; create-contract failures extended with missing sender user/group coverage.

## Design Notes

- Architectural direction: keep read and write semantics unified temporarily in Manager because the request explicitly asks to extend this existing contract first.
- JSONPath patch model should be transport-agnostic at the port boundary, so adapters can map it to SQL/ORM updates without leaking infrastructure concerns into domain contracts.

## Verification

**Commands:**
- `uv run pytest -q ucsschool-objects/tests/core/contracts/test_manager_contracts.py` -- expected: manager contract checks pass.
- `uv run pytest -q ucsschool-objects/tests` -- expected: full `ucsschool-objects` suite passes with explicit required domain constructor attributes.

## Suggested Review Order

**Domain Test Fixture Alignment**

- Establishes explicit required `Group` constructor values after default removal.
	[`model_builders.py:34`](../../ucsschool-objects/tests/core/domain/helpers/model_builders.py#L34)

- Aligns workgroup fixture with required relation fields while preserving existing semantics.
	[`model_builders.py:51`](../../ucsschool-objects/tests/core/domain/helpers/model_builders.py#L51)

**Validation Baselines**

- Ensures validation helper `Group` instances always supply required relation attributes.
	[`test_model_validation.py:44`](../../ucsschool-objects/tests/core/domain/test_model_validation.py#L44)

- Ensures validation helper `User` instances include explicit unloaded relationship defaults.
	[`test_model_validation.py:62`](../../ucsschool-objects/tests/core/domain/test_model_validation.py#L62)

**Identity Semantics Regression Guard**

- Updates direct `User` constructions to remain valid with required relationship fields.
	[`test_user_model_identity_semantics.py:43`](../../ucsschool-objects/tests/core/domain/test_user_model_identity_semantics.py#L43)

- Updates direct `Group` constructions used for equality-by-public-id assertions.
	[`test_user_model_identity_semantics.py:86`](../../ucsschool-objects/tests/core/domain/test_user_model_identity_semantics.py#L86)

**Story Artifact Synchronization**

- Captures baseline, completed tasks, and verification commands for this follow-up.
	[`spec-manager-protocol-crud-jsonpath-public-id.md:1`](./spec-manager-protocol-crud-jsonpath-public-id.md#L1)
