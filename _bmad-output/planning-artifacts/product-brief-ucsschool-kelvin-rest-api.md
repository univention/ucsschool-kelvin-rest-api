---
title: "Product Brief: ucsschool-kelvin-rest-api"
status: "draft"
created: "2026-04-08T10:18:53+02:00"
updated: "2026-04-08T10:18:53+02:00"
inputs:
  - "AGENTS.md"
  - "doc/dev/architecture.rst"
  - "doc/dev/architecture-decisions.rst"
  - "doc/dev/usecases.rst"
  - "doc/dev/usecases/uc006_coexistence.rst"
  - "doc/dev/requirements/requirements-functional.rst"
  - "doc/dev/requirements/requirements-nonfunctional.rst"
---

# Product Brief: Kelvin V2

## Executive Summary

Kelvin V2 is the modernization of the UCS@school management API from a directory-bound integration layer into a database-backed platform service. Kelvin V1 delivers critical school administration workflows today, but its read and write paths depend directly on LDAP and UDM interactions. That architecture constrains performance, makes large-scale search expensive, and limits how far the product can scale as UCS@school data volumes and customization needs continue to grow.

Kelvin V2 addresses that limit by introducing a relational domain model backed by PostgreSQL and synchronized with Nubus. Instead of querying LDAP and UDM directly for operational API reads, V2 serves data from a school database that is populated and later kept current through synchronization processes. This creates a migration path where V2 can deliver immediate read-performance gains first, then automated synchronization, and finally full write capability until it can replace Kelvin V1 completely.

The first release is intentionally narrow: prove the architecture with read-only access to PostgreSQL backed by a one-time manual sync from Nubus. Subsequent releases automate synchronization and eventually add native V2 write operations. Throughout the transition, Kelvin V2 can reuse proven Kelvin V1 logic where necessary, reducing migration risk while creating a credible path to a more scalable and extensible platform.

## The Problem

Kelvin V1 performs important school-management tasks, but it does so against UCS directory infrastructure that was not optimized for the scale, query flexibility, and evolution Kelvin now needs. Direct LDAP and UDM access increases latency for common operations, especially read-heavy and filtered workloads. It also couples the API tightly to legacy storage and synchronization patterns, making modernization slow and risky.

This becomes more acute as UCS@school deployments grow, extended attributes become more important, and expectations rise for responsive search, predictable behavior at scale, and incremental migration without service interruption. The current architecture can continue to function, but it makes future performance improvements, broader extensibility, and full replacement planning harder than they need to be.

## The Solution

Kelvin V2 introduces a staged architecture transition.

In the target model, Kelvin V2 reads from and ultimately writes to a relational school domain database in PostgreSQL. Nubus remains the authoritative ecosystem peer, but synchronization moves from direct request-time directory dependency toward explicit connector-driven data propagation. That separates API responsiveness from LDAP query cost and gives the product a clearer foundation for indexing, filtered search, data modeling, and future feature growth.

The delivery strategy is phased:

1. Release 1 delivers read-only Kelvin V2 against PostgreSQL, populated by a manual one-time sync from Nubus.
2. Release 2 adds automated synchronization so database content is filled and updated from Nubus continuously.
3. Release 3 adds native Kelvin V2 write operations so V2 can fully replace Kelvin V1.

During the intermediate phases, Kelvin V2 may rely on Kelvin V1 code paths to solve selected tasks. That is a deliberate migration tactic, not a compromise in vision: it reduces transition risk while allowing the platform to ship value before the end-state architecture is complete.

## What Makes This Different

The main differentiator is not a new surface feature set, but a safer and more scalable operating model for UCS@school APIs.

- It shifts read performance away from direct LDAP and UDM dependency toward a relational model better suited for search and scale.
- It supports coexistence with Kelvin V1 instead of forcing a high-risk cutover.
- It creates a clearer foundation for extended attributes, richer data modeling, and future entities.
- It turns modernization into a controlled sequence of releases with measurable value at each step.

This is especially valuable in an education platform context where operational continuity matters as much as architectural progress.

## Who This Serves

Primary stakeholders are the engineering, product, and operations teams responsible for UCS@school API evolution and migration planning. They need a path to improve performance and scalability without breaking existing integrations or forcing a disruptive switchover.

Primary end users are the systems and applications that depend on Kelvin for school data management: administrative interfaces, import tooling, and external school management software. Their success condition is simple: Kelvin remains compatible and dependable while becoming faster, more scalable, and easier to evolve.

## Success Criteria

- Kelvin V2 Release 1 proves that UCS@school objects can be served correctly from PostgreSQL rather than direct LDAP and UDM reads.
- Read-heavy operations that are expensive in Kelvin V1 show materially better responsiveness in Kelvin V2.
- The architecture supports filtered and scalable read access for the existing school domain model and extended attributes.
- Release 2 establishes automated Nubus-to-database synchronization with acceptable operational visibility and recovery behavior.
- Release 3 enables Kelvin V2 to perform native writes and replaces Kelvin V1 for core management workflows.

## Scope

### In Scope

- A database-backed domain model for Kelvin V2.
- PostgreSQL as the operational read store for V2.
- A phased migration path from manual sync, to automated sync, to native V2 writes.
- Coexistence with Kelvin V1 during the transition.
- Reuse of Kelvin V1 logic in intermediate stages where that reduces delivery risk.

### Out of Scope for the First Release

- Full automated synchronization from Nubus.
- Native Kelvin V2 write operations.
- Complete retirement of Kelvin V1.
- Broad new end-user features unrelated to proving the V2 architecture and performance model.

## Vision

If successful, Kelvin V2 becomes the long-term UCS@school API platform: a high-performance, database-backed service that preserves compatibility with the UCS ecosystem while scaling to much larger deployments and more complex data needs. Over time it should provide a cleaner basis for synchronization, extensibility, richer search, and future domain entities without carrying forward the full cost of direct LDAP-centric request handling.

The strategic outcome is not simply “Kelvin, but newer.” It is a controlled transition from an API constrained by legacy infrastructure to one designed for sustainable scale, operational resilience, and full replacement of Kelvin V1.