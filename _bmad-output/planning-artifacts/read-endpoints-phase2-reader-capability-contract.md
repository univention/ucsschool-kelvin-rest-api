---
artifactType: phase-contract
phase: 2
status: complete
date: 2026-04-14
approvedBy: Jan
---

# Phase 2 Reader Capability Contract

## Goal

Define the reader interface and adapter capability needed to fulfill all V2 read endpoint query and retrieval needs.

## Approved Reader Set

1. SchoolReader
2. SchoolClassReader
3. WorkGroupReader
4. RoleReader
5. UserReader

## Reader Responsibilities

### SchoolReader
- get by stable identifier and by name lookup helper
- search by supported school filters (name and supported scalar fields)

### SchoolClassReader
- get class by school + class name
- search by required school and optional class name wildcard semantics
- provide class membership projection required by API response

### WorkGroupReader
- get workgroup by school + workgroup name
- search by required school and optional workgroup name wildcard semantics
- provide workgroup sender control projections required by API response

### RoleReader
- list available roles
- get role by role name

### UserReader
- get by username and stable identifier
- search with required API filter support:
  - school
  - username/name
  - ucsschool_roles
  - email
  - record_uid
  - source_uid
  - birthday exact
  - expiration_date exact
  - disabled (mapped to active)
  - firstname
  - lastname
  - role combinations per API contract
  - controlled additional query parameters

## Capability Matrix (Endpoint to Reader)

| Endpoint group | Reader contract |
|---|---|
| schools search/get/head | SchoolReader |
| classes search/get | SchoolClassReader |
| workgroups search/get | WorkGroupReader |
| roles search/get | RoleReader |
| users search/get | UserReader |

## Load Strategy Contract

- Readers expose explicit load configuration for relations.
- Relation loading must remain deterministic and opt-in.
- No hidden lazy-load side effects in endpoint serialization path.

## Error Contract

Readers must raise domain-level errors for:
- not found
- unsupported filter field
- unsupported operator
- invalid filter value

No ORM-specific exceptions may cross reader boundaries.

## Phase 2 Definition-of-Done

- Reader set and responsibilities fully specified.
- Endpoint to reader capability matrix complete.
- Error and loading behavior contract locked.

Phase 2 result: Complete.
