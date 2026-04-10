---
title: 'Refresh BMAD Context for Database Model Changes'
type: 'chore'
created: '2026-05-11T00:00:00Z'
baseline_commit: '117c4fa83a39ecfc03abc20728f49668842cd471'
status: 'done'
context:
  - '{project-root}/_bmad-output/project-context.md'
  - '{project-root}/ucsschool-objects/src/ucsschool_objects/database_models.py'
  - '{project-root}/ucsschool-objects/src/ucsschool_objects/core/domain/models.py'
  - '{project-root}/alembic/versions'
  - '{project-root}/kelvin-connector/src/kelvin_connector/database_models.py'
---

<frozen-after-approval reason="human-owned intent — do not modify unless human renegotiates">

## Intent

**Problem:** The BMAD context used by implementation agents is stale relative to the current database/domain model. It still centers on earlier model assumptions and misses recent persistence shape changes (expanded entity graph, relationship semantics, and membership modeling), which increases the risk of incorrect agent-generated code and tests.

**Approach:** Reconcile BMAD context against the live code by updating project-context rules with verified database-model and domain-model facts. Keep updates factual and constrained to what is currently implemented (plus clearly labeled near-term constraints), so agents can plan and implement without relying on outdated model assumptions.

## Boundaries & Constraints

**Always:**
- Use code as source of truth, not prior BMAD prose.
- Capture only verified model behavior from current files and migrations.
- Keep guidance implementation-focused: architecture boundaries, model invariants, and testing implications.
- Preserve existing project-context sections and style; update in place rather than rewriting unrelated guidance.
- Keep all new statements scoped to this repository state as of the update date.

**Ask First:**
- Reframing product-level requirements in planning artifacts (PRD/architecture) beyond minimal consistency corrections.
- Expanding scope from BMAD context refresh into code refactors or schema changes.
- Removing existing guidance that still applies but appears loosely worded.

**Never:**
- Invent model fields, constraints, or lifecycle behavior not present in code/migrations.
- Convert this task into a data-model redesign or migration-authoring effort.
- Rewrite unrelated BMAD artifacts for style-only changes.
- Alter runtime code or tests as part of this context-only refresh.

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|--------------|---------------------------|----------------|
| HAPPY_PATH | Current SQLAlchemy and domain model files are readable and consistent | BMAD context is updated with accurate entity/relationship and constraint guidance | N/A |
| PARTIAL_STALENESS | Only parts of BMAD context are stale | Only stale statements are replaced; unrelated valid rules remain unchanged | N/A |
| AMBIGUOUS_SIGNAL | Documentation and code appear to diverge | Context prefers code-backed facts and calls out ambiguity conservatively | Preserve existing text unless evidence is clear |

</frozen-after-approval>

## Code Map

- `_bmad-output/project-context.md` -- Primary BMAD context artifact to refresh.
- `ucsschool-objects/src/ucsschool_objects/database_models.py` -- Canonical SQLAlchemy model, constraints, and relationship loading behavior.
- `ucsschool-objects/src/ucsschool_objects/core/domain/models.py` -- Canonical domain dataclass shape and relation semantics for agents.
- `kelvin-connector/src/kelvin_connector/database_models.py` -- DN/public-id mapping tables relevant to cross-system synchronization context.
- `alembic/versions/f1c5bf519a40_init_tables.py` -- Baseline schema creation facts.
- `alembic/versions/e8b27dd51414_add_mapping_tables.py` -- Mapping-table evolution facts.
- `alembic/versions/a3f9c12e8b01_seed_default_roles.py` -- Seeded role model evolution facts.

## Tasks & Acceptance

**Execution:**
- [x] `_bmad-output/project-context.md` -- Add/update database-domain rules to reflect current SQLAlchemy entities (School, Group, User, Role, SchoolMembership, key association tables), uniqueness constraints, and relationship loading conventions -- Prevent stale model assumptions in future agent output.
- [x] `_bmad-output/project-context.md` -- Update domain-model guidance to reflect current dataclass semantics (UNLOADED/UNSET sentinels, mutable relation containers where present, membership dictionary keyed by school public_id) -- Align generated code/tests with current domain contracts.
- [x] `_bmad-output/project-context.md` -- Add migration-awareness notes tied to current Alembic revisions and DN/public-id mapping-table introduction -- Keep agent plans aligned with actual schema evolution.
- [x] `_bmad-output/project-context.md` -- Update test guidance with model-specific guardrails (primary-school constraint behavior, relation loading expectations, and avoiding persistence leakage through ports) -- Reduce regressions caused by incorrect test assumptions.
- [x] `_bmad-output/project-context.md` -- Refresh Last Updated metadata and preserve all unrelated existing sections -- Keep the artifact maintainable and traceable.

**Acceptance Criteria:**
- Given current model files, when an agent reads BMAD project context, then it can correctly infer that Role and SchoolMembership are first-class persisted/domain concepts and not omitted edge entities.
- Given user membership handling, when an agent designs or tests user relations, then it treats school memberships according to current dictionary-based semantics rather than obsolete set/frozenset assumptions.
- Given schema evolution context, when an agent plans changes touching synchronization mappings, then it sees DN/public-id mapping tables and related migration facts explicitly documented.
- Given preserved architecture boundaries, when an agent implements features, then generated plans continue to enforce domain/persistence separation and avoid ORM leakage across port boundaries.

## Spec Change Log

## Verification

**Commands:**
- `rg -n "SchoolMembership|Role|mapping table|UNLOADED|UNSET|school_memberships|Last Updated" _bmad-output/project-context.md` -- expected: updated context contains refreshed model guidance and metadata.
- `rg -n "class (School|Group|User|Role|SchoolMembership)" ucsschool-objects/src/ucsschool_objects/database_models.py` -- expected: code-map entities remain source-aligned.
- `rg -n "school_memberships: dict|UNLOADED|UNSET" ucsschool-objects/src/ucsschool_objects/core/domain/models.py` -- expected: domain semantics referenced by context are verifiable in source.

## Suggested Review Order

**Model Truth Alignment**

- Start with the core context insertions that capture current persistence shape.
  [`project-context.md:24`](../project-context.md#L24)

- Confirm domain contract bullets for sentinels and first-class dataclasses.
  [`project-context.md:39`](../project-context.md#L39)

- Validate membership semantics and adapter translation guidance.
  [`project-context.md:56`](../project-context.md#L56)

**Invariants and Evolution Guardrails**

- Review primary-school invariant coverage and expected error-path testing.
  [`project-context.md:104`](../project-context.md#L104)

- Verify migration-chain guidance for current schema evolution checkpoints.
  [`project-context.md:140`](../project-context.md#L140)

- Inspect ORM invariant and loading-strategy guardrails for adapter safety.
  [`project-context.md:176`](../project-context.md#L176)

- Confirm metadata freshness marker used by future context refreshes.
  [`project-context.md:210`](../project-context.md#L210)

**Spec Provenance**

- Check frozen intent and scope constraints used to drive this update.
  [`spec-refresh-bmad-context-for-db-model-changes.md:17`](./spec-refresh-bmad-context-for-db-model-changes.md#L17)

- Verify completed execution checklist and acceptance criteria traceability.
  [`spec-refresh-bmad-context-for-db-model-changes.md:63`](./spec-refresh-bmad-context-for-db-model-changes.md#L63)
