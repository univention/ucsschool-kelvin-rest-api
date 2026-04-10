---
artifactType: phase-contract
phase: 4
status: complete
date: 2026-04-14
approvedBy: Jan
---

# Phase 4 Query Translation Contract

## Goal

Define a single translation layer from HTTP query parameters to canonical search query objects.

## Translation Principles

1. One translator module per resource family.
2. No ad hoc query parsing in endpoint handlers.
3. Explicit allowlist for user additional query parameters.
4. Validation first, translation second.

## Wildcard Policy

- API wildcard character is star.
- Translator converts star semantics into LIKE/ILIKE-compatible pattern values.
- Fields requiring exact match bypass wildcard conversion.

## Field Semantics

### Exact-only fields
- birthday
- expiration_date
- strict identity values where required by contract

### Wildcard-capable fields
- name-like text fields for search endpoints
- other approved text fields as explicitly listed per resource

### Boolean and inversion
- disabled query value maps to inverse active condition in domain filter

## User Additional Query Parameters

- Translator uses controlled allowlist source.
- Unknown extra parameters are rejected with domain-level filter errors.
- Supported extra parameters map to explicit field names in filter map.

## Validation and Error Mapping

Translator must surface:
- unsupported fields
- unsupported operators
- invalid input types
- invalid value shape for list and wildcard use

Errors are mapped to stable API error responses at endpoint boundary.

## Translator Output Contract

- Output is canonical search query object plus sort and paging directives.
- Output is independent of transport-layer types.

## Phase 4 Definition-of-Done

- Wildcard and exact semantics documented by field category.
- Disabled and extra-parameter behavior locked.
- Error behavior contract locked.

Phase 4 result: Complete.
