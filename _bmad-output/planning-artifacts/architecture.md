---
stepsCompleted:
  - step-01-init
  - step-02-context
  - step-03-starter
  - step-04-decisions
  - step-05-patterns
  - step-06-structure
  - step-07-validation
  - step-08-complete
inputDocuments:
  - _bmad-output/planning-artifacts/prd.md
  - _bmad-output/planning-artifacts/product-brief-ucsschool-kelvin-rest-api.md
  - _bmad-output/project-context.md
  - user-provided-notes-core-library-scope
workflowType: architecture
project_name: ucsschool-kelvin-rest-api
user_name: Jan
date: 2026-04-08
lastStep: 8
status: complete
completedAt: 2026-04-08
---

# Architecture Decision Document

_This document builds collaboratively through step-by-step discovery. Sections are appended as we work through each architectural decision together._

## Project Context Analysis

### Requirements Overview

**Functional Requirements:**
The core library must provide read/search operations for School, User, and Group with strict persistence isolation. Query capabilities must reach parity with the existing data model, including composable filters, deterministic ordering, pagination, empty-vs-not-found distinction, and:

- numeric range operators (gt, gte, lt, lte)
- date/time range operators (gt, gte, lt, lte)
- logical negation support in query expressions

Architecturally, this implies a typed, composable query AST contract in the domain boundary, with adapter-specific translation isolated behind ports.

**Non-Functional Requirements:**
The primary NFR drivers are:

- zero ORM/persistence leakage in domain classes
- adapter swappability (PostgreSQL and in-memory SQLite) without changing domain tests
- deterministic semantics across adapters
- stable read/search contracts under growing dataset size
- explicit non-execution of UDM hooks and Kelvin PyHooks
- domain-level error mapping (no raw SQL/ORM exception leakage)

These push the design toward strict contracts, typed operators, explicit field capability mapping, and contract-test enforcement.

**Scale & Complexity:**

- Primary domain: backend core library (API-adjacent)
- Complexity level: medium-high for this increment due to parity plus dual-adapter consistency requirements
- Estimated architectural components: 8-10
  - domain models
  - query AST
  - load specification
  - reader ports (3)
  - adapter implementations
  - domain error model
  - contract test suite

### Technical Constraints & Dependencies

- Scope is read/search only; writes/transactions/patching are intentionally deferred.
- Must integrate directly with Issue #195 persistence interfaces, without layering additional indirection beyond required ports.
- Issue #195 persistence interfaces are defined as the implementation shipped in commit range 84d35dae8e2a53843e0c80d499d02386c8197637 through 63ca088983e9955c74a658d338fe7681ac9feb7e.
- Must align query/filter semantics with ucsschool-objects/src/ucsschool_objects/database_models.py.
- Must support both PostgreSQL (production) and in-memory SQLite (test parity).
- Must keep explicit relationship loading behavior (no implicit lazy-loading side effects).

### Cross-Cutting Concerns Identified

- Query semantics consistency:
  - handling of NOT across simple and compound clauses
  - handling range operators for both numeric and date/time types
  - timezone-normalized date/time comparison behavior
  - null-handling semantics for comparisons and negation
- Validation and safety:
  - fail-fast invalid filter behavior
  - object-field-operator capability validation at core boundary
- Deterministic behavior:
  - stable sort and pagination ordering across adapters
  - contradiction policy for incompatible clause combinations
- Error standardization:
  - uniform domain-level exceptions for invalid filters, unsupported operations, and not-found
- Test architecture:
  - shared adapter conformance suite to prevent behavioral drift
  - mandatory conformance cases for range and negation semantics

## Starter Template Evaluation

### Primary Technology Domain

API/backend in a brownfield monorepo with established FastAPI and Python conventions.

### Starter Options Considered

- External backend starter template: rejected for this task because it would conflict with existing project conventions, CI gates, and package layout.
- Internal core-library mini-template inside the repository: viable as folder patterns only.
- No external starter (selected): use current repository conventions as the baseline and add the core library in place.

### Selected Starter

No external starter template. Use the repository itself as the architectural foundation.

### Rationale for Selection

- This is a brownfield enhancement, not a greenfield app.
- Introducing a generic starter would add migration noise with low delivery value.
- Existing project constraints already define the architecture defaults.
- This keeps space for creative design while preserving implementation compatibility.

### Initialization Approach for This Story

- Create core-library module boundaries directly in the current codebase.
- Introduce read/search reader ports and typed query AST (numeric/date ranges plus negation).
- Implement PostgreSQL adapter and in-memory SQLite parity adapter behind the same contracts.
- Add adapter conformance tests and domain-level error mapping.

## Core Architectural Decisions

### Decision Priority Analysis

**Critical Decisions (Block Implementation):**

- Read-side only boundary for MVP (Reader ports, no writer).
- Typed query AST with And, Or, Not, and filter operators.
- Range support for numeric and date/time fields (gt, gte, lt, lte).
- Explicit relationship loading (LoadSpec), no implicit lazy loading.
- Domain dataclasses are persistence-agnostic (no ORM types/imports).
- Adapter parity contract across PostgreSQL and SQLite.

**Important Decisions (Shape Architecture):**

- Fail-fast invalid filter behavior with domain-level errors.
- Field/operator capability matrix per object and field type.
- Deterministic ordering and stable pagination semantics.
- Explicit null and contradiction semantics for query evaluation.
- Timezone normalization policy for date/time filter comparisons.

**Deferred Decisions (Post-MVP):**

- Transactions and unit-of-work.
- Batch write operations.
- JSON Patch write contract.
- Complex mutation application services (for example school-year advancement).

### Data Architecture

- Domain model shape: School, User, Group as frozen non-ORM dataclasses.
- Repository ports: SchoolReader, UserReader, GroupReader.
- Search model: typed AST with Filter(field, op, value), And(clauses), Or(clauses), Not(clause).
- Operators: equality/set/text operators from model parity, plus range operators gt/gte/lt/lte for numeric and date/time fields.
- Relationship loading: LoadSpec defines explicitly loaded relationships; unloaded relationships are explicit sentinel state.
- Adapter strategy: PostgreSQL-backed adapter for production and in-memory SQLite adapter for parity tests; both implement identical reader-port contracts.

### Authentication & Security

- Core library does not implement auth.
- Core library assumes authorized caller context from Kelvin API layer.
- Domain interfaces must not leak SQL/ORM exceptions.
- UDM hooks and Kelvin PyHooks are not executed in the core read/search path.

### API & Communication Patterns

- Internal package API only (not a public HTTP API surface).
- Error contract includes InvalidFilter, UnsupportedOperation, NotFound (single lookup), and empty result for search/list.
- Deterministic sort contract requires stable tie-break behavior (for example public_id) for pagination stability.

### Infrastructure & Deployment

- No new runtime platform is required for this story.
- Reuse existing repository tooling and CI quality gates.
- Adapter conformance test suite is mandatory in CI for behavior parity.

### Decision Impact Analysis

**Implementation Sequence:**

- Define domain dataclasses and query AST.
- Define reader ports, error contracts, and load spec.
- Implement PostgreSQL adapter mapping.
- Implement SQLite parity adapter mapping.
- Build shared adapter conformance test suite.
- Integrate with Kelvin API layer read/search call sites.

**Cross-Component Dependencies:**

- Query AST decisions drive adapter translation logic.
- Sort/pagination semantics drive both adapter queries and conformance tests.
- Error taxonomy drives API-layer mapping behavior.
- LoadSpec design drives relationship mapping in domain conversion.

## Implementation Patterns & Consistency Rules

### Pattern Categories Defined

**Critical Conflict Points Identified:**

- Query AST structure and operator naming
- Domain model naming and file placement
- Error type taxonomy and mapping rules
- Relationship loading semantics
- Pagination and sorting behavior
- Adapter conformance test structure

### Naming Patterns

**Database Naming Conventions:**

- Reuse existing persistence naming from Issue #195 without reinterpretation.
- New read-side abstractions use domain-centric names (School, User, Group), not table names.

**API Naming Conventions:**

- Reader ports only for this phase: SchoolReader, UserReader, GroupReader.
- Query AST node names are canonical: Filter, And, Or, Not.
- Range operators are canonical lowercase: gt, gte, lt, lte.

**Code Naming Conventions:**

- Python modules and files use snake_case.
- Domain classes and exceptions use PascalCase.
- Public methods on readers use get and search only in MVP.

### Structure Patterns

**Project Organization:**

- Domain layer: dataclasses, query AST, load spec, domain errors.
- Port layer: reader protocols/interfaces.
- Adapter layer: PostgreSQL adapter and SQLite in-memory adapter.
- Test layer: shared adapter conformance tests plus domain unit tests.

**File Structure Patterns:**

- Keep tests resource-focused and aligned with existing repository conventions.
- Keep adapter-specific test setup in dedicated fixtures and shared behavior assertions centralized.

### Format Patterns

**API Response Formats:**

- Core library returns domain objects or domain errors only.
- No ORM entities and no SQL/ORM exceptions cross the port boundary.

**Data Exchange Formats:**

- Date/time filters use timezone-aware comparison rules.
- Null comparison semantics are explicit and adapter-consistent.
- Search ordering is deterministic with stable tie-break behavior.

### Communication Patterns

**Event System Patterns:**

- No eventing changes in current scope.
- No implicit lazy-load side effects; relationship loading is explicit via LoadSpec.

**State Management Patterns:**

- No mutable global request state in adapters or domain services.
- Reader invocations remain side-effect free for read/search semantics.

### Process Patterns

**Error Handling Patterns:**

- Invalid filter input fails fast with InvalidFilter.
- Unsupported operations fail with UnsupportedOperation.
- Not-found single-object lookup uses NotFound semantics; search returns empty result sets.

**Loading State Patterns:**

- No hidden I/O from attribute access.
- Contradictory filter combinations follow one canonical policy across adapters.

### Enforcement Guidelines

**All AI Agents MUST:**

- Keep domain modules persistence-agnostic.
- Implement query semantics once via shared contract tests, then satisfy in each adapter.
- Preserve deterministic sort/pagination behavior in all adapters.
- Treat Issue #195 interfaces as source-of-truth persistence baseline.

**Pattern Enforcement:**

- Adapter conformance suite is required in CI.
- Pattern violations are fixed at port and test-contract level before endpoint integration.

### Pattern Examples

**Good Examples:**

- Not(Filter(field="school_year", op="lt", value=2024))
- And(Filter(field="birth_date", op="gte", value=...), Filter(field="birth_date", op="lt", value=...))
- Reader search with explicit sort and limit/offset plus deterministic tie-break

**Anti-Patterns:**

- Accessing unloaded relationships triggers implicit DB fetch.
- Returning ORM models from reader interfaces.
- Adapter-specific exception types leaking into domain callers.
- Divergent operator handling between PostgreSQL and SQLite.

## Project Structure & Boundaries

### Complete Project Directory Structure

```text
ucsschool-kelvin-rest-api/
├── kelvin-api/
│   ├── ucsschool/
│   │   └── kelvin/
│   │       ├── corelib/
│   │       │   ├── __init__.py
│   │       │   ├── domain/
│   │       │   │   ├── __init__.py
│   │       │   │   ├── models.py
│   │       │   │   ├── query.py
│   │       │   │   ├── load_spec.py
│   │       │   │   └── errors.py
│   │       │   ├── ports/
│   │       │   │   ├── __init__.py
│   │       │   │   └── readers.py
│   │       │   ├── adapters/
│   │       │   │   ├── __init__.py
│   │       │   │   ├── postgres/
│   │       │   │   │   ├── __init__.py
│   │       │   │   │   ├── mapping.py
│   │       │   │   │   └── readers.py
│   │       │   │   └── sqlite_memory/
│   │       │   │       ├── __init__.py
│   │       │   │       ├── mapping.py
│   │       │   │       └── readers.py
│   │       │   └── translation/
│   │       │       ├── __init__.py
│   │       │       └── query_to_backend.py
│   │       └── routers/
│   │           └── ...
│   └── tests/
│       ├── corelib/
│       │   ├── domain/
│       │   │   ├── test_query_ast.py
│       │   │   ├── test_load_spec.py
│       │   │   └── test_errors.py
│       │   ├── contracts/
│       │   │   ├── test_reader_contract_school.py
│       │   │   ├── test_reader_contract_user.py
│       │   │   ├── test_reader_contract_group.py
│       │   │   ├── test_query_ranges_numeric_datetime.py
│       │   │   └── test_query_negation_semantics.py
│       │   ├── adapters/
│       │   │   ├── postgres/
│       │   │   │   └── test_postgres_contract_binding.py
│       │   │   └── sqlite_memory/
│       │   │       └── test_sqlite_contract_binding.py
│       │   └── fixtures/
│       │       ├── corelib_contract_data.py
│       │       └── adapter_factories.py
│       └── ...
├── ucsschool-objects/
│   └── src/ucsschool_objects/database_models.py
└── _bmad-output/planning-artifacts/architecture.md
```

### Architectural Boundaries

**API Boundaries:**

- Kelvin routers call corelib reader ports, not ORM entities directly for new read/search paths.
- Auth/authz remains in Kelvin transport layer before corelib invocation.

**Component Boundaries:**

- `domain/*` contains no ORM imports.
- `ports/*` defines contracts only.
- `adapters/*` contains persistence specifics only.
- `translation/*` centralizes query AST translation behavior.

**Service Boundaries:**

- Read/search behavior is side-effect free.
- Write concerns (transactions, patching) are excluded from MVP boundaries.

**Data Boundaries:**

- Core returns only domain dataclasses.
- Adapter exceptions are translated to domain errors.
- Relationship loading only via explicit load spec.

### Requirements to Structure Mapping

**Feature/Epic Mapping:**

- FR1-FR7 (domain object access) -> corelib/domain/models.py, corelib/ports/readers.py, adapters/*/readers.py
- FR8-FR14 (search/filter/ranges/negation/pagination) -> corelib/domain/query.py, corelib/translation/query_to_backend.py, contract tests
- FR24-FR26 (error semantics) -> corelib/domain/errors.py, adapter mapping, router-level mappings
- FR27-FR29 (adapter substitution) -> tests/corelib/contracts/*, adapter binding tests

**Cross-Cutting Concerns:**

- No UDM/PyHooks execution enforced in adapter/readers and covered in tests.
- Deterministic ordering enforced via shared contract tests.
- Timezone and null semantics enforced by translation plus contract conformance.

### Integration Points

**Internal Communication:**

- Routers -> reader ports -> concrete adapter wiring via DI.
- Query AST built by service/router layer and passed unchanged through ports.

**External Integrations:**

- Issue #195 persistence interfaces (commit range 84d35dae8e2a53843e0c80d499d02386c8197637 to 63ca088983e9955c74a658d338fe7681ac9feb7e) are consumed by adapter layer only.

**Data Flow:**

- Request validated/authenticated in router.
- Reader call with query/load spec enters port.
- Adapter translates AST to backend filter/query.
- Persistence results are mapped to dataclasses.
- Domain objects are returned to router for response conversion.

### File Organization Patterns

**Configuration Files:**

- Reuse existing repository config (`pyproject.toml`, lint/test configs); avoid new top-level toolchains.

**Source Organization:**

- New code is additive under `kelvin-api/ucsschool/kelvin/corelib/`.
- Existing router/service modules integrate via explicit import boundaries.

**Test Organization:**

- Shared contract tests live in `kelvin-api/tests/corelib/contracts/`.
- Adapter-specific setup lives in `kelvin-api/tests/corelib/adapters/...`.

**Asset Organization:**

- Not applicable for backend scope; no new static asset structures required.

### Development Workflow Integration

**Development Server Structure:**

- Corelib is importable in existing Kelvin dev runtime with no separate service process.

**Build Process Structure:**

- Existing lint/test/pytest flows pick up new modules and tests.
- Contract tests act as gate for adapter parity.

**Deployment Structure:**

- No additional deployment artifact; changes ship within existing Kelvin package/deployment process.

## Architecture Validation Results

### Coherence Validation

**Decision Compatibility:**

- Read-only scope is consistent with Reader-only ports.
- Query AST decisions (Filter/And/Or/Not) align with adapter translation boundaries.
- Numeric and date/time range operators align with parity goals and contract-test approach.
- Explicit LoadSpec plus no implicit lazy loading preserves deterministic behavior and avoids hidden I/O.

**Pattern Consistency:**

- Naming patterns align with Python style and repository conventions.
- Error taxonomy aligns with API integration constraints (domain errors, no ORM leakage).
- Deterministic sorting/pagination patterns align with parity and CI conformance strategy.

**Structure Alignment:**

- Domain/ports/adapters separation supports hexagonal boundaries.
- Test structure includes contract-first parity validation.
- Integration points are explicit between routers, ports, and adapters.

### Requirements Coverage Validation

**Functional Requirements Coverage:**

- FR1-FR7 covered by domain models plus Reader ports.
- FR8-FR14 covered by query AST, translation layer, and adapter implementations.
- FR24-FR26 covered by domain error contracts.
- FR27-FR29 covered by shared adapter conformance suite and adapter binding tests.

**Non-Functional Requirements Coverage:**

- NFR6/NFR16/NFR17 covered by domain-level error mapping and adapter parity tests.
- NFR12-NFR15 covered by dual-adapter strategy and unchanged-domain-test substitution goal.
- NFR4 covered by deterministic ordering and tie-break rule.
- NFR8 covered by explicit no-hook execution boundary with test coverage.

### Implementation Readiness Validation

**Decision Completeness:**

- Critical and important decisions are documented and scoped.
- Deferred items are explicit (transactions, patching, write-side services).

**Structure Completeness:**

- Concrete module tree and boundary mapping are defined.
- Requirements-to-structure traceability is explicit.

**Pattern Completeness:**

- Conflict points are enumerated.
- Enforcement mechanism is defined (CI conformance tests).
- Good examples and anti-patterns are documented.

### Gap Analysis Results

**Critical Gaps:**

- None identified that block implementation kickoff.

**Important Gaps:**

- Contradiction policy should be finalized explicitly as either fail-fast InvalidFilter or canonical empty-result semantics.
- Null semantics should be specified per operator class (eq/ne/range/set/text) for both adapters.
- Date/time normalization policy should explicitly define timezone behavior for naive values.

**Nice-to-Have Gaps:**

- Add a short glossary for query AST and load semantics for onboarding.
- Add one end-to-end example from router request to query AST to reader call.

### Validation Issues Addressed

- Issue #195 reference is anchored to commit range 84d35dae8e2a53843e0c80d499d02386c8197637 to 63ca088983e9955c74a658d338fe7681ac9feb7e.
- Range support for numeric/date-time plus negation is represented consistently across context, decisions, and patterns.
- Pattern enforcement and project structure both point to adapter conformance strategy.

### Architecture Completeness Checklist

**Requirements Analysis**

- [x] Project context analyzed
- [x] Constraints and dependencies identified
- [x] Cross-cutting concerns mapped

**Architectural Decisions**

- [x] Critical decisions documented
- [x] Domain boundaries and adapter strategy defined
- [x] Error and query semantics modeled

**Implementation Patterns**

- [x] Naming and structure rules established
- [x] Process/error patterns documented
- [x] Anti-patterns identified

**Project Structure**

- [x] Directory and boundary design defined
- [x] Requirement mapping to structure completed
- [x] Integration points documented

### Architecture Readiness Assessment

**Overall Status:** READY FOR IMPLEMENTATION

**Confidence Level:** HIGH

**Key Strengths:**

- Tight scope control for MVP read/search boundary.
- Strong hexagonal separation with explicit contract tests.
- Explicit parity strategy across PostgreSQL and SQLite.

**Areas for Future Enhancement:**

- Writer-side architecture (UnitOfWork, JSON Patch, transactional batching).
- Additional domain object coverage beyond School/User/Group.
- Performance tuning guidance once production data profiles are available.

### Implementation Handoff

**AI Agent Guidelines:**

- Follow documented Reader-only boundary.
- Keep domain modules persistence-agnostic.
- Implement adapter behavior to satisfy shared conformance tests first.
- Preserve deterministic sort/pagination and explicit load behavior.

**First Implementation Priority:**

- Create corelib/domain and corelib/ports plus query/error contracts.
- Add conformance tests that encode agreed range/negation semantics.
- Bind PostgreSQL and SQLite adapters to the same contracts.
