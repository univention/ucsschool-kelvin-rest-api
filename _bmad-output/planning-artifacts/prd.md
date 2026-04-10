---
stepsCompleted:
  - step-01-init
  - step-02-discovery
  - step-02b-vision
  - step-02c-executive-summary
  - step-03-success
  - step-04-journeys
  - step-05-domain
  - step-06-innovation
  - step-07-project-type
  - step-08-scoping
  - step-09-functional
  - step-10-nonfunctional
  - step-11-polish
  - step-12-complete
visionInsights:
  coreInsight: "Separation of concerns architecture where Kelvin handles efficient school domain operations in relational database while Nubus remains authoritative for IAM/access control; changes sync bidirectionally so entire ecosystem stays current."
  differentiator: "Hexagonal architecture ensures core library is persistence-agnostic, enabling testability, port flexibility, and future database migration without rewriting business logic."
  scalingGoal: "Handle millions of users efficiently by localizing school domain operations to relational database optimized for those queries, moving away from request-time LDAP/UDM queries."
inputDocuments:
  - _bmad-output/planning-artifacts/product-brief-ucsschool-kelvin-rest-api.md
  - _bmad-output/project-context.md
  - user-provided-story-issue-195
workflowType: prd
documentCounts:
  briefCount: 1
  researchCount: 0
  brainstormingCount: 0
  projectDocsCount: 1
classification:
  projectType: api_backend
  domain: edtech
  complexity: medium
  projectContext: brownfield
---

# Product Requirements Document - ucsschool-kelvin-rest-api

**Author:** Jan
**Date:** 2026-04-08

## Executive Summary

The Kelvin V2 core library implements the domain-driven application layer for school operations (students, schools, groups, classes) using hexagonal architecture to separate business logic from persistence concerns. Nubus remains authoritative for access and identity management; Kelvin V2 owns the school domain and operates it in a relational model designed for scale and efficiency. By decoupling domain objects and business rules from persistence implementation, the library enables high-performance query execution and bi-directional synchronization with Nubus so the broader UCS ecosystem benefits from normalized, current school data.

### What Makes This Special

**Hexagonal architecture decouples business logic from persistence.** The core library uses ports and adapters to isolate domain objects and business rules from ORM or database details. Changing the persistence layer or underlying database type affects only the adapter implementation, not the domain core. This enables testability (mock ports instead of databases), flexibility (swap persistence implementations), and future migrations without business logic refactoring.

**Efficient scale for school operations.** Rather than querying LDAP/UDM at request time—which does not scale for millions of school-related objects—Kelvin V2 operates school domain data from a relational database optimized for those operations. Changes are synchronized back to Nubus in the background, allowing both systems to remain authoritative in their respective domains while keeping the broader ecosystem current.

**Read-only foundation for proven architecture.** The initial release supports read and search access only, proving the hexagonal architecture and synchronization strategy before adding writes. This reduces delivery risk and allows value to ship incrementally: prove the model, automate synchronization, then add native writes.

## Project Classification

- **Project Type:** API Backend
- **Domain:** EdTech (Educational Infrastructure)
- **Complexity:** Medium
- **Project Context:** Brownfield (Enhancement to existing Kelvin V2 foundation)

## Success Criteria

### User Success

**API Clarity:** Domain library exports are self-documenting; developers understand available operations without consulting reference docs. School, User, and Group object interfaces are intuitive and match domain terminology.

**Port Ease of Mocking:** Test fixtures can inject mock persistence adapters without modifying business logic. Tests verify domain behavior in isolation from any database technology.

**Performance Predictability:** Query operations return results within acceptable latency; performance characteristics are explicit in the API contract.

### Business Success

**Zero Persistence Knowledge Leakage:** 100% of domain classes contain zero ORM, database, SQL, or persistence-specific code. Audit: grep the codebase for ORM imports, SQL patterns, database-specific annotations and find none in the domain layer.

**Proven Architecture:** Developers can replace the PostgreSQL adapter with an in-memory adapter, run the complete test suite unchanged, and all tests pass.

**Foundation for Evolution:** The library structure supports adding write operations and Nubus synchronization capabilities without domain refactoring.

### Technical Success

**Complete Coverage of Defined Domain Model:** All objects and query operations defined in `ucsschool-objects/src/ucsschool_objects/database_models.py` are available through the core library with full parity for read/search access, including query filtering.

**Explicit Ports and Adapters:** The library defines clear port interfaces (for example, SchoolRepository, UserRepository, GroupRepository) with adapters that implement SQL-backed read/search access. Adapter changes do not ripple into domain code.

**No UDM Hooks or PyHooks Execution:** The core library intentionally does not execute UDM hooks or Kelvin PyHooks during read and search operations, and this is documented.

### Measurable Outcomes

- **100% domain classes persistence-agnostic:** Automated checks confirm zero persistence-related imports or patterns in all domain modules.
- **Adapter swap test passes:** Complete test suite passes when PostgreSQL adapter is replaced with an in-memory implementation; no domain test changes required.
- **Query API completeness:** Every filter operation available in the ORM/data model is available through the library API.

## Product Scope

### MVP - Minimum Viable Product

**Core Objects:** School, User, Group as defined in `ucsschool-objects/src/ucsschool_objects/database_models.py`.

**Operations:** Read by identifier and search with filtering (all filter operations from the data model), including list/pagination where applicable.

**Ports:** Repository ports for School, User, Group with PostgreSQL adapter support.

**Testing:** Unit test coverage for domain operations; adapter swappability proven with in-memory adapter.

**Documentation:** Core library API reference, port contracts, and explicit statement that UDM hooks/PyHooks are not executed in this layer.

### Growth Features (Post-MVP)

- Native write operations (create, update, delete) through the core library.
- Additional domain objects beyond the initial User/Group/School focus.
- Advanced query composition and optimization.

### Vision (Future)

- Nubus synchronization as the next major expansion after read/search parity.
- Extended domain-model evolution without core business layer rewrites.

## User Journeys

### Journey 1: Domain Developer (Primary Success Path)

A backend developer implements school-domain features using the core library only. They retrieve School, User, and Group domain objects through read/search APIs and apply business rules without touching ORM types. They validate behavior using mocked repository ports. The value moment is when business tests run without database setup and remain stable across adapter changes.

### Journey 2: Domain Developer (Primary Edge Path)

The same developer handles edge cases such as empty search results, invalid filters, and not-found lookups. The library returns consistent domain-level outcomes and errors, so application logic can recover gracefully without persistence-specific branching.

### Journey 3: Adapter Developer (Operations/Platform User)

An adapter developer implements and maintains the PostgreSQL adapter for repository ports. They map model/query capabilities from `database_models.py` into SQL/ORM queries while keeping all persistence code inside adapters. Success is zero leakage into domain classes and stable contract behavior for the core layer.

### Journey 4: Test Engineer (Support/Troubleshooting User)

A test engineer runs the same domain test suite against PostgreSQL and an in-memory adapter. No test logic changes are required. If results diverge, the issue is isolated to adapter behavior rather than business logic.

### Journey 5: API Integration Developer (API/Integration User)

An API-layer developer integrates Kelvin endpoints with the new core library for read/search only. They consume domain objects via ports and avoid direct persistence access. This keeps endpoint code focused on transport/auth concerns while domain behavior stays centralized.

### Journey Requirements Summary

- Clear, persistence-agnostic domain API for read/search operations.
- Full query/filter parity with `database_models.py` for in-scope objects.
- Consistent domain-level error semantics for edge cases.
- Strict ports-and-adapters boundary with no ORM leakage into domain classes.
- Adapter swappability proven by unchanged domain tests.
- Scope explicitly limited to SQL read/search; Nubus sync is out of scope for this iteration.

## Domain-Specific Requirements

### Compliance & Regulatory

- Read-only handling of school-domain data must align with applicable education privacy expectations (for example FERPA/COPPA context where relevant to deployment).
- Data exposure through read/search operations must follow least-privilege and existing Kelvin authorization boundaries.

### Technical Constraints

- Core library remains strictly read/search only for this release.
- No execution of UDM hooks or Kelvin PyHooks in this core business layer.
- Query/filter semantics must be deterministic and aligned with `ucsschool-objects/src/ucsschool_objects/database_models.py`.

### Integration Requirements

- Core library ports/adapters must integrate with the SQL persistence layer introduced in Issue #195.
- No additional abstraction layer is introduced between core library and the existing persistence interfaces beyond required port contracts.

### Risk Mitigations

- Prevent persistence leakage by enforcing zero ORM/database dependencies in domain classes.
- Maintain contract tests to verify adapter parity for read/search behavior and filter support.
- Include regression tests for key filter combinations and edge cases (empty results, not-found, invalid filters).

## API Backend Specific Requirements

### Project-Type Overview

This increment is an API-backend-adjacent core library delivery. The artifact is not a new public HTTP API; it is an internal business-domain library consumed by Kelvin API layers. Therefore, API-backend concerns are interpreted as service contracts, repository ports, and compatibility boundaries rather than endpoint design.

### Technical Architecture Considerations

- Core layer provides domain-centric read/search contracts for School, User, and Group.
- Authentication and authorization remain in Kelvin API transport layer; core library assumes authorized caller context.
- Domain contracts are Python dataclass/domain-model oriented; ORM entities remain adapter-internal.
- Rate limiting is out of scope for the core library and remains at API gateway/router layers.
- Library API and port interfaces follow semantic versioning; breaking port changes require major version increments.

### Endpoint/Interface Specification Mapping

- HTTP endpoints: Not in scope for this PRD increment.
- Core interfaces in scope: repository/service methods for read by identifier, search with filters, and list/pagination where applicable.
- Filter contracts must align with capabilities defined in `ucsschool-objects/src/ucsschool_objects/database_models.py`.

### Data Contract Requirements

- Expose persistence-agnostic domain models only.
- Preserve deterministic serialization/conversion boundaries when integrated into Kelvin API models.
- Do not leak SQL/ORM exceptions directly through core-domain interfaces; map to domain-level errors.

### Implementation Considerations

- No external SDK is required; usage is via internal Python package interfaces.
- Provide concise developer examples for adapter wiring and in-memory test adapter substitution.
- Document explicitly that UDM hooks and Kelvin PyHooks are intentionally not executed in this core layer.

## Project Scoping & Phased Development

### MVP Strategy & Philosophy

**MVP Approach:** Problem-solving MVP focused on proving architectural decoupling, domain correctness, and developer productivity for read/search use cases.

**Resource Requirements:** Small focused backend team with domain expertise, persistence adapter expertise, and strong automated testing capability.

### MVP Feature Set (Phase 1)

**Core User Journeys Supported:**
- Domain developer read/search workflow on School, User, Group.
- Adapter developer implementation and validation workflow.
- Test engineer adapter-swap verification workflow.

**Must-Have Capabilities:**
- Read/search support for User, Group, School aligned to `database_models.py`.
- Query filtering parity with the defined data model.
- Strict ports-and-adapters architecture with zero persistence leakage in domain layer.
- PostgreSQL production adapter plus in-memory SQLite adapter for tests.
- Release gate: unchanged domain test suite passes when swapping PostgreSQL adapter with in-memory SQLite adapter.
- Explicit exclusion of write operations and Nubus sync in this phase.

### Post-MVP Features

**Phase 2 (Post-MVP Growth):**
- Broaden object coverage and deepen read/search capabilities while preserving persistence-agnostic domain boundaries.
- Improve developer ergonomics, diagnostics, and performance characteristics for large datasets.

**Phase 3 (Expansion):**
- Introduce Nubus synchronization capabilities as the next major platform expansion.

### Risk Mitigation Strategy

**Technical Risks:**
- Risk: hidden ORM/persistence coupling in domain layer.
- Mitigation: architectural checks plus adapter contract tests and code reviews focused on leakage prevention.

**Market/Product Risks:**
- Risk: MVP perceived as incomplete due to no write/sync support.
- Mitigation: clear phase communication and explicit success criteria proving architectural value early.

**Resource Risks:**
- Risk: over-scoping beyond read/search parity.
- Mitigation: strict phase gates tied to MVP completion criteria before any sync/write expansion.

## Functional Requirements

### Domain Object Access

- FR1: Domain developers can retrieve a School domain object by identifier.
- FR2: Domain developers can retrieve a User domain object by identifier.
- FR3: Domain developers can retrieve a Group domain object by identifier.
- FR4: Domain developers can retrieve collections of School domain objects.
- FR5: Domain developers can retrieve collections of User domain objects.
- FR6: Domain developers can retrieve collections of Group domain objects.
- FR7: Domain developers can receive domain-model representations that are independent from ORM entity types.

### Search and Filtering

- FR8: Domain developers can search School objects using the filters defined by the data model.
- FR9: Domain developers can search User objects using the filters defined by the data model.
- FR10: Domain developers can search Group objects using the filters defined by the data model.
- FR11: Domain developers can combine supported filters in a single search request.
- FR12: Domain developers can request paginated search results where applicable.
- FR13: Domain developers can request deterministic ordering behavior for list and search results.
- FR14: Domain developers can distinguish between empty-result responses and not-found single-object lookups.

### Domain Contract Integrity

- FR15: Domain developers can use a core API that exposes only business-domain concepts and operations.
- FR16: Domain developers can rely on core-library behavior that does not execute UDM hooks.
- FR17: Domain developers can rely on core-library behavior that does not execute Kelvin PyHooks.
- FR18: Domain developers can consume documented read/search contracts for School, User, and Group operations.

### Port and Adapter Interoperability

- FR19: Adapter developers can implement repository ports for School read/search operations.
- FR20: Adapter developers can implement repository ports for User read/search operations.
- FR21: Adapter developers can implement repository ports for Group read/search operations.
- FR22: Runtime configuration can use a PostgreSQL adapter implementation for production read/search workloads.
- FR23: Runtime configuration can use an in-memory SQLite adapter implementation for test workloads.

### Error and Result Semantics

- FR24: Consumers can receive consistent domain-level error outcomes for invalid filter input.
- FR25: Consumers can receive consistent domain-level error outcomes for unsupported operations.
- FR26: Consumers can receive consistent domain-level outcomes for not-found object queries.

### Testability and Adapter Substitution

- FR27: Test engineers can execute unchanged domain test suites against different adapter implementations.
- FR28: Test engineers can validate that domain behavior remains equivalent when swapping PostgreSQL and in-memory SQLite adapters.
- FR29: Test engineers can verify read/search behavior without requiring direct database setup in pure domain tests.

### Documentation and Consumer Usability

- FR30: Developers can access documentation describing supported read/search capabilities and filter contracts.
- FR31: Developers can access documentation that explicitly states write operations are out of scope for this release.
- FR32: Developers can access documentation that explicitly states Nubus synchronization is out of scope for this release.

## Non-Functional Requirements

### Performance

- NFR1: DB point lookup operations for read-by-identifier workloads should meet SERVER_MEDIUM draft targets of p95 <= 20 ms and p99 <= 50 ms under warm-cache assumptions.
- NFR2: DB range/query operations for indexed, bounded read/search workloads should meet SERVER_MEDIUM draft targets of p95 <= 100 ms and p99 <= 300 ms.
- NFR3: Performance targets apply only to interactive workloads with selective predicates and bounded result sets; unbounded scans and exploratory queries are explicitly out of scope.
- NFR4: Pagination behavior must be deterministic with stable ordering for identical request inputs.

### Security

- NFR5: The core library must operate in authorized caller context and must not implement or bypass Kelvin API-layer authentication/authorization controls.
- NFR6: Domain-facing contracts must not expose persistence internals such as SQL text, ORM-specific exceptions, or connection details.
- NFR7: Returned domain data must follow least-privilege exposure expectations for school-domain and identity-adjacent attributes.
- NFR8: UDM hooks and Kelvin PyHooks must not execute in this release and this behavior must be documented and test-covered.

### Scalability

- NFR9: Domain contracts for read/search must remain stable across growth from development-scale to large production-scale datasets.
- NFR10: Increasing dataset size must not require changes to domain-level caller contracts for supported read/search operations.
- NFR11: Adapter and domain implementations must avoid mutable global request state that would block horizontal API-layer scaling.

### Integration

- NFR12: Production runtime must support the PostgreSQL adapter with full parity for in-scope read/search contracts.
- NFR13: Test runtime must support an in-memory SQLite adapter with equivalent domain-observable read/search behavior.
- NFR14: Query/filter semantics must align with capabilities defined in `ucsschool-objects/src/ucsschool_objects/database_models.py`.
- NFR15: Adapter substitution between PostgreSQL and in-memory SQLite must require no domain-test modifications.

### Reliability

- NFR16: Not-found, empty-result, and invalid-filter outcomes must be consistent across adapter implementations.
- NFR17: Unsupported operations must fail predictably with domain-level error semantics.
- NFR18: Read/search contract behavior must remain backward compatible within a major library version.

### Compatibility and Maintainability

- NFR19: Core library versioning must follow semantic versioning for published domain and port contracts.
- NFR20: Contract tests must verify parity across adapters for all in-scope read/search operations and supported filters.
- NFR21: Developer documentation must include port contracts, adapter wiring patterns, and explicit out-of-scope declarations for writes and Nubus sync.

### Out of Scope for This Release

- NFR22: No write-operation latency or throughput SLOs are defined in this increment.
- NFR23: No Nubus synchronization propagation, throughput, or outtake/error-handling SLOs are defined in this increment.
