---
artifactType: execution-plan
status: ready-for-review
date: 2026-04-14
---

# Read Endpoints Step-by-Step Execution Plan

## Phase 0: Baseline Lock

Goal: Freeze target contract before code changes.

Tasks:
1. Confirm endpoint scope from openapi-v2 for read paths only.
2. Confirm response fields per endpoint group.
3. Confirm query parameter semantics (`*`, exact date filters, role combinations, extra query params for users).

Definition of Done:
- Scope confirmation note approved.
- No unresolved contract ambiguities.

## Phase 1: Domain Projection Design

Goal: Define read projections needed for class/workgroup distinction and role retrieval.

Tasks:
1. Define SchoolClass projection contract.
2. Define WorkGroup projection contract.
3. Define Role retrieval contract.
4. Decide whether projections are new domain types or typed views over Group.

Definition of Done:
- Projection decisions documented.
- No endpoint depends on ambiguous Group-only semantics.

## Phase 2: Reader Capability Completion

Goal: Close read/query capability gaps in ports and adapters.

Tasks:
1. Add reader capability for roles.
2. Add class/workgroup query strategy.
3. Extend user search filter support for required API behavior.
4. Document load-spec requirements per endpoint model.

Definition of Done:
- Reader interfaces cover all read endpoint groups.
- Capability matrix maps each endpoint query to reader support.

## Phase 3: API Mapper Contract

Goal: Formalize domain -> Kelvin API schema mapping.

Tasks:
1. Define mapping of domain fields to API fields (`disabled`, URL fields, school/group structures).
2. Define URI generation policy.
3. Define default and optional field behavior.
4. Define mapping error handling policy.

Definition of Done:
- Mapper specification complete and reviewed.
- Every required response field has a deterministic source and transform.

## Phase 4: Query Translation Contract

Goal: Centralize translation from HTTP query params to SearchQuery.

Tasks:
1. Define wildcard translation rules.
2. Define exact vs inexact filter behavior by field.
3. Define controlled strategy for additional user query parameters.
4. Define invalid filter error mapping.

Definition of Done:
- Query translation spec approved.
- No endpoint performs ad hoc query translation.

## Phase 5: Test And Validation Gates

Goal: Prevent behavior drift before implementation rollout.

Tasks:
1. Add endpoint-group contract test matrix.
2. Add reader parity tests for query semantics.
3. Add mapper snapshot/shape tests.
4. Add negative tests for invalid filters and unsupported combinations.

Definition of Done:
- All phase gates in test-validation plan pass.
- Residual risk list is explicit and accepted.

## Phase 6: Readiness Review

Goal: Decide whether endpoint implementation can start.

Tasks:
1. Verify all high-priority matrix gaps are resolved.
2. Verify deferred items do not block read endpoint correctness.
3. Publish final readiness statement.

Definition of Done:
- Status set to Ready for implementation.
- Approved implementation kickoff checklist.

## Tracking Board

| Phase | Owner | Status | Blockers | Evidence |
|---|---|---|---|---|
| 0 Baseline lock | Jan + Copilot | Completed | None | read-endpoints-phase0-baseline-lock.md |
| 1 Domain projection design | Jan + Copilot | Completed | None | read-endpoints-phase1-domain-projection-design.md |
| 2 Reader capability completion | Jan + Copilot | Completed | None | read-endpoints-phase2-reader-capability-contract.md |
| 3 API mapper contract | Jan + Copilot | Completed | None | read-endpoints-phase3-api-mapper-contract.md |
| 4 Query translation contract | Jan + Copilot | Completed | None | read-endpoints-phase4-query-translation-contract.md |
| 5 Test and validation gates | Jan + Copilot | Completed | None | read-endpoints-phase5-gates-and-evidence.md |
| 6 Readiness review | Jan + Copilot | Completed | None | read-endpoints-phase6-readiness-review.md |
