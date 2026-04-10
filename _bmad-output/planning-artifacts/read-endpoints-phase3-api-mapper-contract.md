---
artifactType: phase-contract
phase: 3
status: complete
date: 2026-04-14
approvedBy: Jan
---

# Phase 3 API Mapper Contract

## Goal

Define deterministic transformation from domain projections to Kelvin API response schemas.

## Mapper Boundary

- Input: domain projection objects from readers.
- Output: API response models compatible with openapi-v2 schema.
- Mapper owns URL composition and API-only field shaping.
- Domain layer remains storage and business focused.

## Required Mapping Rules

1. Identity and URL fields
- Map domain identifiers to API URL and name fields.
- URL generation is centralized and route-aware.

2. Active and disabled semantics
- domain active true maps to API disabled false
- domain active false maps to API disabled true

3. School classes and workgroups in user payload
- map membership relations to API dictionary structure keyed by school name

4. Role fields
- map role names and display values to role resource shape

5. Optional field behavior
- include required fields always
- optional fields follow API defaults and nullable behavior

6. UDM and extension properties
- udm_properties and ucsschool_roles mapping is explicit and consistent by resource

## Mapper Components

1. SchoolMapper
2. SchoolClassMapper
3. WorkGroupMapper
4. RoleMapper
5. UserMapper

Shared helper modules:
- URL composer
- relation flattener
- enum/value normalizer

## Error Handling Rules

- mapper failures produce explicit mapping errors with context
- no silent drops of required fields
- unsupported projection combinations fail fast

## Phase 3 Definition-of-Done

- Every response field has a deterministic source and transform.
- Disabled and membership mapping policy is locked.
- URL strategy and optional field behavior are locked.

Phase 3 result: Complete.
