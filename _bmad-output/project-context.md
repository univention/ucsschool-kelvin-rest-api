---
project_name: 'ucsschool-kelvin-rest-api'
user_name: 'Jan'
date: '2026-04-08T13:55:27+02:00'
sections_completed: ['technology_stack', 'language_rules', 'framework_rules', 'testing_rules', 'quality_rules', 'workflow_rules', 'anti_patterns']
status: 'complete'
rule_count: 127
optimized_for_llm: true
---

# Project Context for AI Agents

_This file contains critical rules and patterns that AI agents must follow when implementing code in this project. Focus on unobvious details that agents might otherwise miss._

---

## Technology Stack & Versions

- Runtime baseline: Python >=3.11 only.
- API framework: FastAPI >=0.95.2,<0.98.0 with Pydantic <2 semantics.
- Serialization and HTTP behavior: ORJSON >=3.11.0, HTTPX <0.28.0.
- Serving stack: Uvicorn >=0.35.0 and Gunicorn >=23.0.0.
- Database and migrations: Psycopg[binary] >=3.3.3 and Alembic >=1.18.4.
- UCS domain dependencies are first-class project dependencies: ucs-school-lib, ucs-school-import, ucsschool-objects.
- Workspace package resolution is intentional via uv workspace members and custom sources; do not replace with unrelated PyPI alternatives.
- Compatibility-sensitive constraints to preserve unless explicitly requested:
	- FastAPI pinned below 0.98.0.
	- Pydantic pinned below 2.
	- HTTPX pinned below 0.28.0.
	- PyJWT pinned below 2.10.

## Critical Implementation Rules

### Language-Specific Rules

- Keep Python code compatible with Python >=3.11 and existing typing style.
- Prefer async endpoint and service functions for I/O-bound operations; keep await chains explicit.
- Use dependency injection through FastAPI Depends for UDM context, auth context, and logger wiring.
- Raise FastAPI HTTPException with explicit status codes and stable detail messages for API-visible errors.
- Preserve Pydantic v1 model patterns already in use:
	- class Config usage on models and mixins.
	- validator and root_validator behavior.
	- parse_obj and dict-based conversion patterns.
- Preserve conversion boundaries between API models and UCS library models:
	- from_lib_model and _from_lib_model_kwargs for read conversion.
	- as_lib_model and _as_lib_model_kwargs for write conversion.
- Keep URL and identifier transformations symmetric using existing helper methods and cache-aware URL utilities.
- Use lru_cache only for stable process-level singletons (logger/factory/importer/config-derived helpers), not request-scoped state.
- Maintain strict school/object name validation rules and existing regex/date validation behavior unless a requirement explicitly changes API semantics.
- Keep ORJSON-compatible payload assumptions in serialization paths.

### Framework-Specific Rules

- Keep the two-version API contract intact:
	- v1 and v2 routers are both mounted and maintained.
	- v2 applies DB compatibility dependency checks at router level.
- Route organization pattern is resource-first:
	- one router module per domain resource under kelvin routers.
	- shared behavior lives in service and base mixin modules, not duplicated per route.
- Preserve app boot sequence in main initialization:
	- create FastAPI app with ORJSON default response class.
	- attach middleware and exception handlers immediately after app creation.
	- include versioned routers and service docs router.
- Keep middleware stack behavior stable:
	- CorrelationIdMiddleware for request tracing.
	- TimingMiddleware with patched route-name resolver for mounted routes.
- Preserve centralized exception mapping:
	- UDM and generic exceptions are normalized by service exception handlers.
	- correlation ID headers must be propagated in error responses.
- Preserve Kelvin docs and OpenAPI architecture:
	- version-aware docs endpoints for v1 and v2.
	- service-level docs endpoint exposing both specs.
	- cached OpenAPI generation keyed by API prefix and version.
- Preserve dependency-injected auth flow:
	- OAuth2 bearer token decode and verify path.
	- active user check and kelvin_admin authorization check as separate dependencies.
- Keep static documentation asset serving mounted at versioned static paths.
- Do not bypass existing helper layers for URL generation, role conversion, or UDM adapter logic when adding endpoints.

### Testing Rules

- Use pytest as the baseline test framework with async support enabled (--asyncio-mode=auto).
- Keep Kelvin tests in kelvin-api/tests and preserve existing naming (test_*.py with resource-focused files like test_route_user.py).
- Reuse shared fixtures from kelvin-api/tests/conftest.py and imported plugin fixtures (pytest_plugins = ["ucsschool.lib.tests.conftest"]) instead of rebuilding setup.
- Preserve API-version coverage pattern:
	- respect the --api-version option (v1, v2, both).
	- write tests that are version-aware where route behavior differs.
- Use @pytest.mark.asyncio for coroutine tests; keep sync HTTP checks with TestClient where appropriate.
- Keep environment-sensitive tests guarded with explicit skip conditions (for container and UCS runtime requirements).
- Prefer parametrized tests for matrix-like behavior (roles, API versions, validation variants) instead of repetitive test bodies.
- Keep cache and global-state tests isolated by clearing caches in autouse fixtures when needed.
- For URL resolution tests, prefer real route setup and URL helper calls instead of monkeypatching route lookup behavior.
- Preserve assertion style:
	- check both status code and semantic payload.
	- validate exception class and message or shape for negative paths.

### Code Quality & Style Rules

- Run and satisfy pre-commit hooks before considering a change complete.
- Formatting and linting baseline:
	- black with line length 105 and target py311.
	- isort (black profile, line length 105, known first-party modules include ucsschool, udm_rest_client, univention).
	- flake8 max-line-length 105 with project-specific ignore set (C901, E203, E231, E266, W503).
- Keep imports grouped and sorted according to existing isort config; avoid ad hoc import ordering.
- Respect repository exclusion patterns (venv, generated/static/vendor-like trees, selected legacy paths) when adding tooling or files.
- Preserve existing module and file naming style:
	- Python modules in snake_case.
	- tests named test_*.py with resource-focused grouping.
- Prefer typed function signatures and explicit model fields on public API-facing code paths.
- Avoid introducing blanket noqa or disabling checks unless there is a documented project-level reason.
- Security checks are part of baseline quality (bandit is active in pre-commit with explicit exclusions); do not introduce patterns that trigger avoidable findings.
- Commit message quality gates are enforced:
	- conventional-pre-commit strict mode on commit-msg stage.
	- commit message must include a required issue reference trailer pattern (Issue ORG/repo#123 or Bug #123).

### Development Workflow Rules

- Use uv as the primary project manager:
	- install and sync dependencies with uv sync.
	- run project commands as uv run <command> when environment coupling matters.
- Prefer repository Makefile workflows for local development tasks:
	- make fetch-vm-data TARGET=<ucs-host>.
	- make dev-server for local containerized Kelvin dev runtime.
	- make alembic-migration for schema migration generation.
- Development runtime assumptions:
	- a reachable UCS instance is required for realistic UDM and LDAP integration behavior.
	- local dev often runs Kelvin via Docker compose with synced source changes.
- CI expectations are GitLab-first and policy-enforced:
	- pre-commit and lint checks are mandatory.
	- unit tests and coverage checks are part of normal pipeline quality gates.
	- docker image build, docs, and release jobs are integrated into CI flow.
- Keep release-related changes consistent with documented checklist flow:
	- changelog updates, tag-based release steps, and smoke and QA verification are expected.
- Preserve docs workflow behavior:
	- docs changes live under doc/docs.
	- production docs publication includes manual pipeline triggering constraints.
- Keep branch-based image tagging assumptions intact for test deployments (branch-$CI_COMMIT_REF_SLUG patterns in release flow docs).
- Treat required commit-msg conventions as workflow-level constraints, not optional style preferences.

### Critical Don't-Miss Rules

- Do not break URL normalization assumptions:
	- URL-to-name conversion expects HTTP-style internal URLs after unscheme conversion.
	- passing HTTPS URLs into internal url_to_name helpers is treated as an error path.
- Preserve correlation and traceability end-to-end:
	- propagate request correlation IDs through UDM request kwargs.
	- keep correlation headers exposed in error responses.
- Do not bypass established auth and permission dependency chains:
	- token decode and validation, active-user checks, and kelvin_admin checks are distinct stages.
- Treat direct LDAP access as a constrained fallback:
	- prefer existing UDM and UCS@school model layers unless direct LDAP is already required by existing design.
- Avoid changing API-visible validation semantics without explicit requirement:
	- school and name and date validation, role parsing, and URL conversion behavior are contract-sensitive.
- Avoid introducing cache misuse:
	- do not store request-scoped or mutable session data in process-level lru_cache and cached singletons.
	- keep cache keys aligned with API version and route context when adding URL helper behavior.
- Security-sensitive handling:
	- never log credentials, secret-file contents, or token-signing material.
	- keep authentication failures generic (no user enumeration details in API errors).
- Performance and correctness guardrails:
	- avoid bypassing versioned routing patterns and DB compatibility checks for v2 paths.
	- avoid duplicating expensive UDM and importer initialization per request when cached provider functions already exist.
- Test and failure-path gotchas:
	- preserve explicit exception types and messages where tests assert them.
	- when changing URL helper behavior, update cache isolation and clearing in tests to avoid cross-test pollution.

---

## Usage Guidelines

**For AI Agents:**

- Read this file before implementing any code.
- Follow all rules exactly as documented.
- When in doubt, prefer the more restrictive option.
- Update this file if new patterns emerge.

**For Humans:**

- Keep this file lean and focused on agent needs.
- Update when technology stack changes.
- Review quarterly for outdated rules.
- Remove rules that become obvious over time.

Last Updated: 2026-04-08
