---
title: 'Fail fast on unloaded domain attribute access'
type: 'refactor'
created: '2026-05-18T00:00:00Z'
status: 'done'
baseline_commit: '48e4e6d71e7149fb29c81ad17a2686a032d10a23'
context: []
---

<frozen-after-approval reason="human-owned intent — do not modify unless human renegotiates">

## Intent

**Problem:** The domain models currently expose unloadable fields as `T | UnloadedType`. Even when a caller intentionally requests a fully loaded object, the public type surface still advertises every unloadable attribute as potentially unloaded, which forces repetitive `cast()` or sentinel checks and weakens the value of the type checker.

**Approach:** Keep partial loading as an internal capability, but change the public domain contract so reading an unloaded attribute raises immediately instead of returning the sentinel. Implement this with explicit public getters per unloadable attribute backed by private unloadable storage, so loaded attributes keep their concrete public types while partial objects remain representable internally for readers, patches, and minimal references.

## Boundaries & Constraints

**Always:** Preserve `LoadSpec` and partial-load behavior at the manager/mapper layer; keep `minimal(public_id)` and other internally partial objects constructible; implement unload checks with explicit per-attribute getters over private backing fields so basedpyright can keep concrete public types; make the failure mode consistent across direct fields and derived properties; keep persistence guards for not-yet-loaded values intact; update tests to assert fail-fast behavior instead of sentinel-return behavior where public attribute access is involved.

**Ask First:** Introducing a new public exception type that downstream packages must explicitly catch; widening this change into Kelvin, `ucs-school-lib`, or `ucs-school-import` if cross-package adaptation is needed; changing write-path semantics beyond what is required to preserve current create/modify behavior.

**Never:** Solve the typing issue by sprinkling casts through callers; replace normal attributes with dynamic `__getattr__` or descriptor-heavy indirection that obscures field types from basedpyright; remove selective loading support; silently coerce unloaded values to `None` or empty collections; break the ability to carry unloaded state internally between mapper and persistence code.

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|--------------|---------------------------|----------------|
| FULLY_LOADED_FIELD | Domain object returned from manager with requested field loaded | Reading the field returns its concrete value type without exposing an unload sentinel | N/A |
| UNLOADED_FIELD_ACCESS | Domain object with an attribute intentionally left unloaded | Reading that public attribute fails immediately | Raise a deterministic domain-level error describing the unloaded attribute |
| DERIVED_PROPERTY_DEPENDS_ON_UNLOADED | `User.primary_school`, `User.groups`, or `User.roles` accessed while memberships are unloaded | Property does not return `UNLOADED`; it fails fast for the missing prerequisite | Raise the same deterministic unloaded-attribute error |
| INTERNAL_WRITE_GUARD | Create/modify path receives a domain object whose required persistence input is still internally unloaded | Existing write guard still rejects the object before persistence | Preserve current validation failure instead of persisting partial data |
| MINIMAL_REFERENCE_OBJECT | `School.minimal(public_id)` / `Role.minimal(public_id)` / similar helper result | Object can still exist for identity/reference purposes | Accessing any unloaded public attribute raises until that attribute is populated |

</frozen-after-approval>

## Code Map

- `ucsschool-objects/src/ucsschool_objects/core/domain/models.py` -- Defines the public domain model surface, unloaded sentinels, minimal object factories, and the property/getter design that will carry the typing change.
- `ucsschool-objects/src/ucsschool_objects/core/adapters/sqlalchemy/mappers/to_domain.py` -- Produces partially loaded domain objects from ORM state and is the main entry point for unloaded attribute population.
- `ucsschool-objects/src/ucsschool_objects/core/adapters/sqlalchemy/mappers/to_orm.py` -- Already rejects unloaded values on persistence and must remain compatible with the new internal representation.
- `ucsschool-objects/src/ucsschool_objects/core/domain/validators.py` -- Reads domain attributes directly and must either rely on the new fail-fast contract or guard explicit partial-object cases.
- `ucsschool-objects/tests/core/domain/helpers/model_builders.py` -- Central test fixture builder for partial and fully loaded domain objects.
- `ucsschool-objects/tests/core/domain/test_user_model_primary_school.py` -- Existing regression coverage for derived user property behavior when memberships are missing.
- `ucsschool-objects/tests/core/domain/test_user_model_groups.py` -- Existing regression coverage for derived group aggregation behavior.
- `ucsschool-objects/tests/core/domain/test_user_model_identity_semantics.py` -- Covers `minimal()` identity semantics and currently asserts sentinel visibility.
- `ucsschool-objects/tests/core/contracts/test_manager_load_spec_projections.py` -- Verifies what is and is not loaded when managers honor `LoadSpec`.
- `ucsschool-objects/tests/core/adapters/test_nested_field_queries.py` -- Covers mapper behavior that currently preserves unloaded relations as sentinels.

## Tasks & Acceptance

**Execution:**
- [x] `ucsschool-objects/src/ucsschool_objects/core/domain/models.py` -- Refactor unloadable domain fields into private backing attributes plus explicit public raising getters so public types stay concrete while internal unloaded state remains representable for mapping and persistence.
- [x] `ucsschool-objects/src/ucsschool_objects/core/adapters/sqlalchemy/mappers/to_domain.py` -- Adapt mapper construction to the new internal unloaded representation without losing `LoadSpec` projection fidelity.
- [x] `ucsschool-objects/src/ucsschool_objects/core/domain/validators.py` and `ucsschool-objects/src/ucsschool_objects/core/adapters/sqlalchemy/mappers/to_orm.py` -- Keep validation and persistence behavior coherent when partially loaded objects are encountered.
- [x] `ucsschool-objects/tests/core/domain/helpers/model_builders.py` and targeted domain/contract/adapter tests -- Rewrite expectations so public unloaded access raises, while manager projection tests still prove which fields were intentionally omitted.
- [x] `ucsschool-objects/src/ucsschool_objects/__init__.py` and `ucsschool-objects/src/ucsschool_objects/core/domain/__init__.py` -- Export any new domain-level error or helper that becomes part of the supported public contract.

**Acceptance Criteria:**
- Given a fully loaded `User`, when code reads scalar fields such as `name`, `firstname`, or `active`, then the public API exposes concrete value types instead of `UnloadedType` unions.
- Given a partially loaded domain object, when code reads an attribute that was intentionally not loaded, then a deterministic domain-level error is raised instead of returning `UNLOADED`.
- Given `User.primary_school`, `User.groups`, or `User.roles`, when their backing memberships are unloaded, then each property raises the same unloaded-access error rather than returning a sentinel.
- Given `LoadSpec` projections, when manager tests run, then requested fields remain readable and omitted fields still behave as omitted without regressing projection behavior.
- Given a create or modify flow that still contains internally unloaded required values, when the object is mapped back toward persistence, then the operation still fails before writing incomplete data.

## Spec Change Log

- 2026-05-18: Review classification completed with patch-only follow-up. Added defensive validation for `domain_asdict()` and `raw_attr_value()`, restored malformed-membership guarding in `to_orm.py`, and replaced string sentinel patch markers with structured sentinel objects to avoid value collisions.

## Design Notes

- The core design goal is to separate internal representation from public access. The mapper layer still needs to remember that some fields were never loaded, but callers should not have to model that state in every public attribute type.
- Preferred implementation shape: store unloadable values in private backing fields such as `_name: str | UnloadedType`, then expose `@property def name(self) -> str` that calls a small typed helper to raise on `UnloadedType`. This keeps the public attribute surface concrete for basedpyright without relying on casts at call sites.
- Keep the implementation intentionally explicit rather than meta-programmed. A small generic helper for `raise-or-return` is fine, but each public getter should remain individually declared so domain model fields stay discoverable, readable, and well-typed.
- Projection tests should continue to prove omission, but they will likely need a helper that asserts unloaded access raises rather than inspecting the public attribute value for `UnloadedType`. If tests need to inspect internal unload state directly, do so only through intentionally private backing fields in narrowly scoped mapper/domain tests.

## Verification

**Commands:**
- `uv run pytest --no-cov ucsschool-objects/tests/core/domain/test_user_model_primary_school.py ucsschool-objects/tests/core/domain/test_user_model_groups.py ucsschool-objects/tests/core/domain/test_user_model_identity_semantics.py` -- expected: domain-level unloaded-access behavior is covered and passes.
- `uv run pytest --no-cov ucsschool-objects/tests/core/contracts/test_manager_load_spec_projections.py ucsschool-objects/tests/core/adapters/test_nested_field_queries.py` -- expected: projection and mapper behavior stay consistent under the new fail-fast contract.