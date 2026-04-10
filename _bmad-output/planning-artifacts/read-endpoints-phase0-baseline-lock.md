---
artifactType: phase-baseline
phase: 0
status: complete
date: 2026-04-14
approvedBy: Jan
---

# Phase 0 Baseline Lock

## Objective

Freeze the read-endpoint target contract before implementation work begins.

## Contract Baseline (Read Endpoints Only)

OpenAPI read-path inventory (V2):
- Classes: GET collection, GET item ([openapi-v2.json](openapi-v2.json#L9), [openapi-v2.json](openapi-v2.json#L120))
- Workgroups: GET collection, GET item ([openapi-v2.json](openapi-v2.json#L353), [openapi-v2.json](openapi-v2.json#L464))
- Roles: GET collection, GET item ([openapi-v2.json](openapi-v2.json#L697), [openapi-v2.json](openapi-v2.json#L728))
- Schools: GET collection, GET item, HEAD exists ([openapi-v2.json](openapi-v2.json#L776), [openapi-v2.json](openapi-v2.json#L886), [openapi-v2.json](openapi-v2.json#L935))
- Users: GET collection, GET item ([openapi-v2.json](openapi-v2.json#L982), [openapi-v2.json](openapi-v2.json#L1199))
- Service docs: changelog/readme GET ([openapi-v2.json](openapi-v2.json#L1400), [openapi-v2.json](openapi-v2.json#L1418))

Current router parity for read endpoints:
- classes GET/GET item ([kelvin-api/ucsschool/kelvin/routers/school_class.py](kelvin-api/ucsschool/kelvin/routers/school_class.py#L166), [kelvin-api/ucsschool/kelvin/routers/school_class.py](kelvin-api/ucsschool/kelvin/routers/school_class.py#L202))
- workgroups GET/GET item ([kelvin-api/ucsschool/kelvin/routers/workgroup.py](kelvin-api/ucsschool/kelvin/routers/workgroup.py#L167), [kelvin-api/ucsschool/kelvin/routers/workgroup.py](kelvin-api/ucsschool/kelvin/routers/workgroup.py#L202))
- roles GET/GET item ([kelvin-api/ucsschool/kelvin/routers/role.py](kelvin-api/ucsschool/kelvin/routers/role.py#L128), [kelvin-api/ucsschool/kelvin/routers/role.py](kelvin-api/ucsschool/kelvin/routers/role.py#L147))
- schools GET/GET item/HEAD ([kelvin-api/ucsschool/kelvin/routers/school.py](kelvin-api/ucsschool/kelvin/routers/school.py#L226), [kelvin-api/ucsschool/kelvin/routers/school.py](kelvin-api/ucsschool/kelvin/routers/school.py#L254), [kelvin-api/ucsschool/kelvin/routers/school.py](kelvin-api/ucsschool/kelvin/routers/school.py#L363))
- users GET/GET item ([kelvin-api/ucsschool/kelvin/routers/user.py](kelvin-api/ucsschool/kelvin/routers/user.py#L572), [kelvin-api/ucsschool/kelvin/routers/user.py](kelvin-api/ucsschool/kelvin/routers/user.py#L741))
- changelog/readme GET ([kelvin-api/ucsschool/kelvin/routers/doc.py](kelvin-api/ucsschool/kelvin/routers/doc.py#L146), [kelvin-api/ucsschool/kelvin/routers/doc.py](kelvin-api/ucsschool/kelvin/routers/doc.py#L152))

Current domain read-layer baseline:
- SQLAlchemy readers available: School, Group, User only ([ucsschool-objects/src/ucsschool_objects/core/adapters/sqlalchemy/readers.py](ucsschool-objects/src/ucsschool_objects/core/adapters/sqlalchemy/readers.py#L71), [ucsschool-objects/src/ucsschool_objects/core/adapters/sqlalchemy/readers.py](ucsschool-objects/src/ucsschool_objects/core/adapters/sqlalchemy/readers.py#L106), [ucsschool-objects/src/ucsschool_objects/core/adapters/sqlalchemy/readers.py](ucsschool-objects/src/ucsschool_objects/core/adapters/sqlalchemy/readers.py#L162))
- Wildcard building block exists through LIKE/ILIKE operator support ([ucsschool-objects/src/ucsschool_objects/core/adapters/sqlalchemy/query_filter.py](ucsschool-objects/src/ucsschool_objects/core/adapters/sqlalchemy/query_filter.py#L73))

## Baseline Decisions Locked For Next Phases

1. Only V2 read endpoints are in scope for this readiness stream.
2. Service docs endpoints (changelog/readme) are excluded from domain-read redesign work.
3. Any contract behavior not represented in current domain/readers must be addressed by:
   - domain/read projection updates, and/or
   - explicit API mapping/translation layers.
4. No endpoint implementation starts before completion of readiness Phase 6.

## Known Contract-Sensitivity Items (Accepted As Work Items)

These are not ambiguities; they are accepted backlog for later phases:
- class vs workgroup projection split
- role reader absence
- user filter breadth vs current field map
- wildcard translation policy from API query to SearchQuery
- response shape mapper requirements

## Phase 0 Definition-of-Done Check

- Scope confirmation note approved: yes
- Unresolved contract ambiguities: none (sensitivity items are tracked as explicit work)

Phase 0 result: Complete.
