# Story 1.1: Implement the core library with non-ORM dataclasses

Status: ready-for-dev

<!-- Note: Validation is optional. Run validate-create-story for quality check before dev-story. -->

## Story

As a developer,
I can access school objects through a library that abstracts the database,
so that objects are correctly abstracted from the persistence layer for better testability.

## Acceptance Criteria

1. Core library domain models for School, User, and Group are implemented as persistence-agnostic, non-ORM dataclasses.
2. The core library exposes read-by-identifier and search operations for School, User, and Group.
3. Search supports filter composition parity with the current data model, including deterministic ordering and pagination semantics.
4. The core library integrates with the Issue #195 persistence interfaces directly (through ports/adapters) without introducing an extra abstraction layer beyond required port contracts.
5. The core library explicitly does not execute UDM hooks or Kelvin PyHooks, and this behavior is documented.
6. Scope is limited to read/search in this version; write operations are explicitly out of scope.
7. Adapter substitution is validated via tests so domain tests remain unchanged when using PostgreSQL vs in-memory SQLite adapters.
8. Domain-facing contracts return domain objects and domain errors only; SQL/ORM internals do not leak across boundaries.

## Tasks / Subtasks

- [ ] Define core domain contracts and models (AC: 1, 8)
  - [ ] Add non-ORM dataclasses for School, User, and Group in `kelvin-api/ucsschool/kelvin/corelib/domain/models.py`.
  - [ ] Add domain error taxonomy in `kelvin-api/ucsschool/kelvin/corelib/domain/errors.py` (`InvalidFilter`, `UnsupportedOperation`, `NotFound`).
  - [ ] Add query AST in `kelvin-api/ucsschool/kelvin/corelib/domain/query.py` with `Filter`, `And`, `Or`, `Not` and operator support including `gt`, `gte`, `lt`, `lte`.
  - [ ] Add explicit relationship loading contract in `kelvin-api/ucsschool/kelvin/corelib/domain/load_spec.py`.

- [ ] Define reader ports for read/search use-cases (AC: 2, 3, 6)
  - [ ] Add `SchoolReader`, `UserReader`, `GroupReader` protocols in `kelvin-api/ucsschool/kelvin/corelib/ports/readers.py`.
  - [ ] Ensure APIs include get-by-id and search/list with deterministic ordering and pagination inputs.
  - [ ] Ensure interfaces are read/search-only; no write methods in MVP.

- [ ] Implement adapters against Issue #195 persistence baseline (AC: 2, 4, 8)
  - [ ] Implement PostgreSQL adapter readers in `kelvin-api/ucsschool/kelvin/corelib/adapters/postgres/readers.py`.
  - [ ] Implement in-memory SQLite parity adapter readers in `kelvin-api/ucsschool/kelvin/corelib/adapters/sqlite_memory/readers.py`.
  - [ ] Add query translation logic in `kelvin-api/ucsschool/kelvin/corelib/translation/query_to_backend.py`.
  - [ ] Ensure adapter exceptions are mapped to domain errors before crossing port boundaries.

- [ ] Document no-hooks behavior and MVP boundaries (AC: 5, 6)
  - [ ] Add explicit note in corelib docs/README that UDM hooks and Kelvin PyHooks are intentionally not executed.
  - [ ] Add explicit statement that writes and Nubus synchronization are out of scope for this story.

- [ ] Add contract and parity tests (AC: 3, 7, 8)
  - [ ] Add shared contract tests under `kelvin-api/tests/corelib/contracts/` for School, User, and Group readers.
  - [ ] Add tests for numeric/date range operators and negation semantics.
  - [ ] Add deterministic sort/pagination tests with stable tie-break behavior.
  - [ ] Add adapter binding tests under `kelvin-api/tests/corelib/adapters/postgres/` and `kelvin-api/tests/corelib/adapters/sqlite_memory/`.
  - [ ] Add/verify tests that no UDM hooks/PyHooks are executed in read/search path.

## Dev Notes

- This story implements the core business layer using hexagonal architecture with strict domain/port/adapter separation.
- Business logic and domain model code must remain persistence-agnostic.
- Scope is intentionally read/search only.
- No execution of UDM hooks or Kelvin PyHooks is a hard design decision and must remain explicit in docs and tests.
- Persistence integration must align with Issue #195 interface baseline.

### Technical Requirements

- Python baseline: >= 3.11.
- FastAPI/Pydantic ecosystem constraints from project context must remain unchanged (Pydantic v1 semantics).
- Domain layer MUST NOT import ORM classes, SQLAlchemy models, SQL text utilities, or adapter internals.
- Contracts must support:
  - composed filters (`And`, `Or`, `Not`)
  - range operators for numeric and datetime fields (`gt`, `gte`, `lt`, `lte`)
  - deterministic ordering and pagination
  - clear distinction between empty search result and not-found single-object lookup
- Error mapping is mandatory: do not leak SQL/ORM exceptions through domain-facing interfaces.

### Architecture Compliance

- Follow module boundaries described in architecture:
  - Domain: `kelvin-api/ucsschool/kelvin/corelib/domain/`
  - Ports: `kelvin-api/ucsschool/kelvin/corelib/ports/`
  - Adapters: `kelvin-api/ucsschool/kelvin/corelib/adapters/`
  - Translation: `kelvin-api/ucsschool/kelvin/corelib/translation/`
- Keep router/auth behavior in existing Kelvin transport layer; core library assumes authorized caller context.
- Avoid hidden lazy-loading side effects; relationship loading must be explicit through `LoadSpec`.

### Library & Framework Requirements

- Reuse existing project dependencies and repository conventions.
- Do not add alternate ORM stacks or unrelated data-access libraries.
- Keep implementation compatible with existing testing and linting setup (pytest, black, isort, flake8, pre-commit).

### File Structure Requirements

- Primary code targets:
  - `kelvin-api/ucsschool/kelvin/corelib/domain/models.py`
  - `kelvin-api/ucsschool/kelvin/corelib/domain/query.py`
  - `kelvin-api/ucsschool/kelvin/corelib/domain/load_spec.py`
  - `kelvin-api/ucsschool/kelvin/corelib/domain/errors.py`
  - `kelvin-api/ucsschool/kelvin/corelib/ports/readers.py`
  - `kelvin-api/ucsschool/kelvin/corelib/adapters/postgres/readers.py`
  - `kelvin-api/ucsschool/kelvin/corelib/adapters/sqlite_memory/readers.py`
  - `kelvin-api/ucsschool/kelvin/corelib/translation/query_to_backend.py`
- Primary test targets:
  - `kelvin-api/tests/corelib/contracts/test_reader_contract_school.py`
  - `kelvin-api/tests/corelib/contracts/test_reader_contract_user.py`
  - `kelvin-api/tests/corelib/contracts/test_reader_contract_group.py`
  - `kelvin-api/tests/corelib/contracts/test_query_ranges_numeric_datetime.py`
  - `kelvin-api/tests/corelib/contracts/test_query_negation_semantics.py`
  - `kelvin-api/tests/corelib/adapters/postgres/test_postgres_contract_binding.py`
  - `kelvin-api/tests/corelib/adapters/sqlite_memory/test_sqlite_contract_binding.py`

### Testing Requirements

- Use shared contract tests to enforce parity between adapters.
- Validate same domain-observable behavior for PostgreSQL and SQLite adapters without changing domain tests.
- Include negative-path tests for invalid filters and unsupported operations.
- Include regression tests for deterministic ordering and pagination stability.
- Include tests that verify no UDM hooks or Kelvin PyHooks execution in this layer.

### Web / Latest Tech Notes

- No architecture-driven dependency upgrade is required for this story.
- Preserve existing project version constraints from project context and pyproject metadata.

### Project Structure Notes

- This story is additive and should fit existing Kelvin package structure.
- No new service, deployment unit, or runtime process should be introduced.

### References

- [Source: _bmad-output/planning-artifacts/prd.md#Executive Summary]
- [Source: _bmad-output/planning-artifacts/prd.md#Functional Requirements]
- [Source: _bmad-output/planning-artifacts/prd.md#Non-Functional Requirements]
- [Source: _bmad-output/planning-artifacts/architecture.md#Core Architectural Decisions]
- [Source: _bmad-output/planning-artifacts/architecture.md#Project Structure & Boundaries]
- [Source: _bmad-output/planning-artifacts/architecture.md#Architecture Validation Results]
- [Source: _bmad-output/project-context.md#Critical Implementation Rules]

## Dev Agent Record

### Agent Model Used

GPT-5.3-Codex

### Debug Log References

- Create-story workflow executed from `.github/skills/bmad-create-story/workflow.md`.
- Source inputs discovered from `_bmad-output/planning-artifacts/` and `_bmad-output/project-context.md`.

### Completion Notes List

- Story context generated from user-provided request and planning artifacts.
- Since sprint status file was not present, no sprint status update was applied.
- Story status set to `ready-for-dev`.

### File List

- `_bmad-output/implementation-artifacts/1-1-implement-the-core-library-with-non-orm-dataclasses.md`
