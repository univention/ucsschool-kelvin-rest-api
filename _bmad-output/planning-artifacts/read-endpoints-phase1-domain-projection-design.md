---
artifactType: phase-design
phase: 1
status: complete
date: 2026-04-14
approvedBy: Jan
---

# Phase 1 Domain Projection Design

## Goal

Define domain-level read projections that remove ambiguity between classes and workgroups and provide explicit role retrieval support.

## Design Drivers

1. OpenAPI has distinct class and workgroup resources and response contracts.
2. Current domain has a generic Group abstraction.
3. Reader layer currently ships School, Group, User readers only.
4. We need clear separation that keeps persistence details out of domain objects.

## Candidate Strategies

### Strategy A: New explicit domain projections (recommended)

Introduce dedicated read projections:
- SchoolClass
- WorkGroup
- Role

Characteristics:
- Each projection has endpoint-specific semantics and fields.
- Reader interfaces become explicit and easier to test against endpoint contracts.
- Mapping layer is straightforward because intent is encoded in type.

Trade-offs:
- Adds new domain types and adapter mapping code.
- Slightly larger initial refactor footprint.

### Strategy B: Keep Group as canonical domain type, add typed views

Keep Group and add typed wrappers or discriminator-based mapping.

Characteristics:
- Smaller type surface.
- Reuses more existing code paths.

Trade-offs:
- Higher long-term ambiguity in API mapping.
- More conditional behavior in reader and mapper code.
- Harder contract tests (resource intent not explicit in type system).

## Recommendation

Use Strategy A.

Rationale:
- Best fit for API contract clarity.
- Lowest ambiguity in class/workgroup split.
- Cleaner future maintenance and test readability.

## Proposed Projection Contracts (Draft)

### SchoolClass (read projection)

Required fields:
- identity: public_id, name, school reference
- metadata: description, has_share/create_share equivalent
- membership: users
- extension: udm_properties and ucsschool_roles (or mapped source fields)

### WorkGroup (read projection)

Required fields:
- identity: public_id, name, school reference
- metadata: description, email, has_share/create_share equivalent
- membership: users
- sender controls: allowed_email_senders_users, allowed_email_senders_groups
- extension: udm_properties and ucsschool_roles (or mapped source fields)

### Role (read projection)

Required fields:
- identity: public_id, name
- presentation: display_name
- endpoint mapping support: URL-ready identifier input

## Reader Contract Changes (Phase-2 input)

Proposed reader interfaces:
- SchoolReader (existing)
- UserReader (existing, extended filters)
- SchoolClassReader (new)
- WorkGroupReader (new)
- RoleReader (new)

Alternative (if minimizing new interfaces):
- GroupReader with explicit resource_type parameter and strict contract subsets.
- Not preferred due to type ambiguity.

## Approved Decisions

1. Strategy A approved: explicit SchoolClass and WorkGroup domain projections.
2. Separate RoleReader approved.
3. Separate SchoolClassReader and WorkGroupReader approved over Group discriminator mode.

## Definition-of-Done Check

- Projection strategy documented: yes
- Role retrieval strategy documented: yes
- Ambiguity removed from class/workgroup intent: yes

Phase 1 result: Complete.
