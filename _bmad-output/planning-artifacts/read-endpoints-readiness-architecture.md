---
workflowType: architecture
artifactType: addendum
status: complete
project_name: ucsschool-kelvin-rest-api
user_name: Jan
date: 2026-04-14
inputDocuments:
  - _bmad-output/planning-artifacts/architecture.md
  - _bmad-output/planning-artifacts/prd.md
  - _bmad-output/project-context.md
  - openapi-v2.json
  - ucsschool-objects/src/ucsschool_objects/core/domain/models.py
  - ucsschool-objects/src/ucsschool_objects/core/adapters/sqlalchemy/readers.py
---

# Read Endpoint Readiness Architecture Addendum

## Purpose

This addendum defines the architecture preparation needed to implement Kelvin V2 read endpoints on top of current ucsschool-objects domain/read models, while keeping behavior contract-safe.

## Scope

In scope:
- Read endpoint contract readiness for: schools, roles, classes, workgroups, users, changelog, readme.
- Domain model and reader capability alignment.
- API mapping and contract-test preparation.

Out of scope:
- Endpoint implementation.
- Write/update/delete behavior.
- Runtime optimization beyond what is required for read contract fidelity.

## Working Method

We will execute findings in ordered phases with explicit gates:
1. Domain shape and projections
2. Reader capability completion
3. API mapping contract
4. Query semantics translator
5. Contract and parity tests
6. Endpoint integration readiness review

Each phase is complete only when its Definition of Done is met in the execution plan.

## Architectural Decisions For This Scope

1. Keep persistence-agnostic domain boundaries.
2. Introduce explicit read projections for SchoolClass and WorkGroup (or typed Group projections with equivalent clarity).
3. Add Role reader capability rather than keeping role reads implicit.
4. Treat API shape conversion as a dedicated mapper layer, not domain responsibility.
5. Enforce wildcard and filter semantics through a single translator module.
6. Use contract tests against openapi-v2 response/query behavior as the release gate.

## Artifact Set

Primary execution artifacts:
- read-endpoints-gap-matrix.md
- read-endpoints-execution-plan.md
- read-endpoints-test-validation-plan.md

How to use:
1. Start with gap matrix to confirm scope and ownership.
2. Execute phases in execution plan in order.
3. Use test/validation plan as phase gate checklist.

## Exit Criteria

This architecture addendum is considered complete when:
- All gaps in the matrix are either marked Resolved or explicitly Deferred with rationale.
- Every phase gate in execution plan is passed.
- Contract-test suite covers all read endpoint groups and required filters.

## Completion Note

Approved by Jan on 2026-04-14 for implementation kickoff.
