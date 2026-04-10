---
artifactType: gap-matrix
status: ready-for-execution
date: 2026-04-14
---

# Read Endpoints Gap Matrix

## Endpoint Contract Coverage

| Endpoint group | Contract source | Current domain/read readiness | Gap level | Main gaps |
|---|---|---|---|---|
| Schools (search/get/head) | openapi-v2 schools | Partial-ready | Medium | API mapping for response shape (`dn`, `url`, `ucsschool_roles`), display_name conversion policy |
| Roles (search/get) | openapi-v2 roles | Partial | Medium | No explicit RoleReader in current reader set, role retrieval contract not formalized |
| Classes (search/get) | openapi-v2 classes | Not ready | High | No explicit SchoolClass domain projection; class/workgroup split missing at domain level |
| Workgroups (search/get) | openapi-v2 workgroups | Partial | High | Group base exists but workgroup-specific projection fields and query behavior need explicit contract |
| Users (search/get) | openapi-v2 users | Partial | High | Query filter contract broader than current field map; API-shape mapping and school/group projection transforms needed |
| Changelog/readme | openapi-v2 docs endpoints | Ready | Low | No domain dependency; keep current behavior |

## Domain And Reader Gaps

| Area | Current state | Required target |
|---|---|---|
| Domain entities | School, Role, Group, User | Add explicit SchoolClass and WorkGroup read projections (or typed projection strategy with same clarity) |
| Reader set | School, Group, User readers | Add Role reader and typed group/class query paths |
| User query filters | Basic scalar fields | Add school, roles, ucsschool_roles, and approved additional property filter strategy |
| Load behavior | LoadSpec relation includes exist | Keep, plus explicit mapping behavior per endpoint response contract |
| Mapping layer | Domain mapping exists | Add API mapper layer for Kelvin response models and URI composition |

## Semantics Gaps

| Topic | Required by API | Current support | Action |
|---|---|---|---|
| Wildcard search | `*` in search params | LIKE exists in query layer | Add translator from API query input to canonical SearchQuery |
| User extra filter params | Additional query parameters | Not represented in current user field map | Define controlled allowlist and translation strategy |
| Disabled vs active | API uses `disabled` | Domain uses `active` | Add deterministic inversion mapping policy |
| Class/workgroup naming scope | School-scoped resource names | Generic group model only | Define typed resource normalization strategy |

## Priority Order

1. Classes/workgroups projection split
2. Users search contract completion
3. Role reader introduction
4. API mapper and URI contract
5. Wildcard/extra-filter translator hardening
