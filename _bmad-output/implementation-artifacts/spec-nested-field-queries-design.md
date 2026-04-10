---
status: ready-for-dev
epic: read-endpoints
story: nested-field-queries
date_created: 2026-04-19
author: Jan (with Winston's architectural guidance)
---

# Nested Field Query Support — Specification

## Problem Statement

The current query filter system only supports scalar field constraints. Users cannot query for:
- All users in a specific group: `Filter("groups.public_id", Operator.EQ, group_uuid)`
- All users at a specific school: `Filter("schools.public_id", Operator.EQ, school_uuid)`
- All groups in a specific school: `Filter("schools.public_id", Operator.EQ, school_uuid)` on GroupReader

This blocks use cases like "find me all users in this group" and "find all groups at this school."

## Solution Overview

Implement **dot-notation nested field queries** with an extensible registry-based architecture. The same syntax supports both:
- **Agnostic queries**: "Get users in group X (any school)" → `Filter("groups.public_id", EQ, uuid)`
- **Explicit intersection**: "Get users in group X at school Y" → `And([Filter("schools.public_id", EQ, school_uuid), Filter("groups.public_id", EQ, group_uuid)])`

## Design Decisions

### 1. Dot Notation Syntax ✓

**Choice:** Support dot notation (e.g., `"groups.public_id"`, `"school.name"`)

**Why:**
- Intuitive, matches REST/GraphQL conventions
- Extensible without code changes (registry-driven)
- Natural composition with AND/OR for complex queries

**Examples:**
```python
# Query all users in a group (any school)
Filter("groups.public_id", Operator.EQ, uuid)

# Query all users in a group at a specific school (intersection)
And([
    Filter("schools.public_id", Operator.EQ, school_uuid),
    Filter("groups.public_id", Operator.EQ, group_uuid)
])

# Query all groups at a school (GroupReader)
Filter("school.public_id", Operator.EQ, school_uuid)
```

### 2. Registry-Based Field Resolution ✓

**Architecture:**

Each reader (UserReader, GroupReader, RoleReader) defines a `_NESTED_FIELD_REGISTRY` that maps relationship names to join specifications.

```python
# SQLAlchemyUserReader._NESTED_FIELD_REGISTRY
_NESTED_FIELD_REGISTRY: dict[str, JoinSpec] = {
    "groups": JoinSpec(
        relation_name="groups",
        target_model=GroupModel,
        join_path=(SchoolMembership, GroupModel),
        join_type="left_outer",  # User may have no groups
        exposed_fields=_get_exposed_fields(GroupModel)  # All first-level Group fields
    ),
    "roles": JoinSpec(
        relation_name="roles",
        target_model=RoleModel,
        join_path=(SchoolMembership, RoleModel),
        join_type="left_outer",  # User may have no roles
        exposed_fields=_get_exposed_fields(RoleModel)  # All first-level Role fields
    ),
    "schools": JoinSpec(
        relation_name="schools",
        target_model=SchoolModel,
        join_path=(SchoolMembership, SchoolModel),
        join_type="left_outer",  # User may have no school memberships
        exposed_fields=_get_exposed_fields(SchoolModel)  # All first-level School fields
    ),
}

# SQLAlchemyGroupReader._NESTED_FIELD_REGISTRY
_NESTED_FIELD_REGISTRY: dict[str, JoinSpec] = {
    "school": JoinSpec(
        relation_name="school",
        target_model=SchoolModel,
        join_path=(SchoolModel,),
        join_type="left_outer",  # Group may not have a school (edge case)
        exposed_fields=_get_exposed_fields(SchoolModel)  # All first-level School fields
    ),
}

# SQLAlchemyRoleReader._NESTED_FIELD_REGISTRY
# Currently empty (Role is typically a leaf node), but structure is ready for future expansion
# e.g., if Role gains relationships in the future, add JoinSpecs here
_NESTED_FIELD_REGISTRY: dict[str, JoinSpec] = {}
```

**Field Map Generation:**

The reader generates a flat `_FIELD_MAP` that includes nested fields for **all queryable first-level fields** on related models:

```python
# Scalar fields
"public_id": UserModel.public_id,
"name": UserModel.name,
# ...

# Nested fields (auto-generated from registry + target model columns)
# All first-level fields on related models are exposed
"groups.public_id": GroupModel.public_id,
"groups.record_uid": GroupModel.record_uid,
"groups.source_uid": GroupModel.source_uid,
"groups.name": GroupModel.name,
"groups.display_name": GroupModel.display_name,
"groups.create_share": GroupModel.create_share,
"groups.group_type": GroupModel.group_type,
"groups.email": GroupModel.email,
# ... all other Group fields

"roles.public_id": RoleModel.public_id,
"roles.name": RoleModel.name,
"roles.display_name": RoleModel.display_name,

"schools.public_id": SchoolModel.public_id,
"schools.record_uid": SchoolModel.record_uid,
"schools.source_uid": SchoolModel.source_uid,
"schools.name": SchoolModel.name,
"schools.display_name": SchoolModel.display_name,
"schools.educational_servers": SchoolModel.educational_servers,
"schools.administrative_servers": SchoolModel.administrative_servers,
"schools.class_share_file_server": SchoolModel.class_share_file_server,
"schools.home_share_file_server": SchoolModel.home_share_file_server,
```

**Dynamic Field Discovery:**

The registry supports **automatic field discovery** — exposed_fields can be generated from the target model's queryable columns:

```python
def _get_exposed_fields(model: type) -> frozenset[str]:
    """Extract queryable first-level column names from a model."""
    # Skip relationships and unloaded fields
    fields = set()
    for attr_name in dir(model):
        attr = getattr(model, attr_name)
        if isinstance(attr, InstrumentedAttribute) and hasattr(attr.property, 'columns'):
            fields.add(attr_name)
    return frozenset(fields)
```

### 3. Join Injection Strategy ✓

**Detection & Injection:**

When a Filter or SortSpec references a nested field (contains `"."`), the query builder:

1. **Detects** the root relationship name (part before the dot)
2. **Looks up** the JoinSpec in the registry
3. **Injects** the necessary joins before building the WHERE clause
4. **Applies** DISTINCT if multiple joins are needed (prevents N:M duplicates)

**Example Flow:**

```python
# Input query
Filter("groups.public_id", Operator.EQ, group_id)

# Detection: root = "groups"
# Lookup: registry["groups"] → JoinSpec with join_path=(SchoolMembership, GroupModel)

# Generated SQL
SELECT DISTINCT users.*
FROM users
LEFT OUTER JOIN school_membership ON users.id = school_membership.user_id
LEFT OUTER JOIN "group" ON school_membership.id = group_membership.school_membership_id
WHERE "group".public_id = ?
LIMIT 50
```

### 4. Join Type Resolution ✓

**Rule:**

- **LEFT OUTER JOIN (default):** Used when the nested relationship is optional (user may have no groups, groups may not have schools)
- **INNER JOIN (when filtering):** Automatically promoted for filter expressions to exclude non-matching records (user MUST have this group)
- **Registry override:** Caller can specify `join_type` explicitly if needed

**Implementation:**

```python
def apply_nested_joins(
    stmt: Select[tuple[T]],
    required_joins: dict[str, JoinSpec],
    registry: dict[str, JoinSpec]
) -> Select[tuple[T]]:
    """Apply necessary joins and return DISTINCT-wrapped statement if N:M detected."""
    for join_name, spec in required_joins.items():
        join_type = spec.join_type  # "left_outer" or "inner"
        for join_model in spec.join_path:
            isouter = (join_type == "left_outer")
            stmt = stmt.join(join_model, isouter=isouter)

    # DISTINCT if multiple joins (N:M prevention)
    if len(required_joins) > 1:
        stmt = stmt.distinct()

    return stmt
```

### 5. Validation & Error Handling ✓

**Parse-Time Validation in `query_filter.py`:**

```python
def _get_filter_column(
    filter_expr: Filter,
    field_map: Mapping[str, FieldColumn],
    registry: dict[str, JoinSpec] | None = None
) -> FieldColumn:
    """Resolve filter field to column, with nested field support."""

    # Fast path: scalar field in map
    if filter_expr.field in field_map:
        return field_map[filter_expr.field]

    # Nested field: validate against registry
    if "." in filter_expr.field and registry:
        root, _, field_part = filter_expr.field.partition(".")
        if root not in registry:
            raise UnsupportedNestedField(
                nested_field=filter_expr.field,
                root_relation=root,
                allowed_relations=list(registry.keys())
            )

        spec = registry[root]
        if field_part not in spec.exposed_fields:
            raise UnsupportedNestedField(
                nested_field=filter_expr.field,
                reason=f"Field '{field_part}' not supported on relation '{root}'",
                supported_fields=list(spec.exposed_fields)
            )

        # Re-check in field_map (should be there after registry build)
        if filter_expr.field in field_map:
            return field_map[filter_expr.field]

    raise UnsupportedFilterField(filter_expr.field)
```

**New Exception with Rich Error Messages:**

```python
class UnsupportedNestedField(CorelibError):
    """Raised when a nested field is not supported or exposed."""
    def __init__(
        self,
        nested_field: str,
        root_relation: str = "",
        allowed_relations: list[str] | None = None,
        reason: str = "",
        supported_fields: list[str] | None = None,
    ):
        self.nested_field = nested_field
        self.root_relation = root_relation
        self.allowed_relations = allowed_relations or []
        self.reason = reason
        self.supported_fields = supported_fields or []

        msg = f"Unsupported nested field: {nested_field}"
        if reason:
            msg += f" ({reason})"

        if supported_fields:
            msg += f". Supported fields: {', '.join(supported_fields)}"

        if root_relation and allowed_relations:
            msg += f". Unknown relation '{root_relation}'. Allowed: {', '.join(allowed_relations)}"

        super().__init__(msg)
```

### 6. Extensibility Pattern ✓

**Adding new nested paths is data-driven:**

To support `Group → school`, `Group → member_roles`, etc., you only need to:

1. Add entry to `_NESTED_FIELD_REGISTRY` in the relevant reader
2. Optionally update `_FIELD_MAP` exposed fields
3. Write tests

**No code changes required** in `query_filter.py` or join logic.

## Implementation Scope

### Phase 1: MVP (2–3 days)

**Goal:** Support nested field queries on all three readers (User, Group, Role) with full field coverage.

**Files to modify:**

1. **Domain layer (`core/domain/`):**
   - Add `UnsupportedNestedField` exception to `errors.py`
   - Export in `__init__.py`

2. **SQLAlchemy adapter (`adapters/sqlalchemy/`):**
   - Add `JoinSpec` dataclass to a new `join_spec.py` module (or inline in readers)
   - Add `_get_exposed_fields()` helper to dynamically discover queryable fields on a model
   - Modify `SQLAlchemyUserReader`:
     - Define `_NESTED_FIELD_REGISTRY` for groups, roles, schools (all first-level fields exposed)
     - Generate `_FIELD_MAP` from scalar fields + registry
     - Update `get()` and `search()` to use registry-aware logic
   - Modify `SQLAlchemyGroupReader`:
     - Define `_NESTED_FIELD_REGISTRY` for school (all first-level fields exposed)
     - Generate `_FIELD_MAP` from scalar + registry
     - Update `get()` and `search()` similarly
   - Modify `SQLAlchemyRoleReader`:
     - Define empty `_NESTED_FIELD_REGISTRY` (Role has no relationships; placeholder for future)
     - Generate `_FIELD_MAP` from scalars only

3. **Query filter (`query_filter.py`):**
   - Add `_get_required_joins()` to detect nested field names
   - Add `apply_nested_joins()` to inject join chains
   - Modify `_get_filter_column()` to validate against registry
   - Modify `_build_filter_expression()` to inject joins before filtering
   - Modify `build_expression()` and `apply_search_query()` to handle registry parameter
   - Modify `apply_sort()` similarly for sort-by nested fields

4. **Tests (`tests/`):**
   - `test_query_filter.py`: nested field detection, validation, join injection
   - `test_readers.py`:
     - `test_user_search_by_groups_any_school()` — core use case
     - `test_user_search_by_school_and_group()` — intersection with And()
     - `test_group_search_by_school()` — GroupReader test
     - `test_nested_query_distinct_results()` — duplicate prevention
     - `test_unsupported_nested_field_raises_error()` — validation with helpful message
     - `test_sort_by_nested_field()` — sorting on nested fields

**Scope Rationale:**
- UserReader, GroupReader, RoleReader all follow the same registry pattern (consistency)
- RoleReader has empty registry now, but demonstrates extensibility for future
- All **first-level fields** are exposed dynamically (not curated list)
- Full field coverage makes the solution immediately useful for queries

**Not in Phase 1:**
- Deeper nesting (Group → school → administrative_servers)
- Non-filter operations that might use nested data (Load/relationship optimization)
- Schema/ORM-level query building (e.g., hybrid properties)

### Phase 2: Extended (future sprint)

- Add `Role` nested paths (if needed)
- Add `Group → member_roles` and deeper nesting
- Performance tuning and indexing audit

## Acceptance Criteria

**Domain & Errors:**
- [ ] `UnsupportedNestedField` exception exists and is exported

**User Reader:**
- [ ] `_NESTED_FIELD_REGISTRY` defined with groups, roles, schools
- [ ] Field map includes all nested fields (e.g., `groups.public_id`)
- [ ] `search()` with `Filter("groups.public_id", EQ, uuid)` returns correct users
- [ ] `search()` with `And([Filter("schools.public_id", ...), Filter("groups.public_id", ...)])` returns intersection
- [ ] Multiple nested joins produce DISTINCT results (no duplicates)
- [ ] Sort by nested field works: `SortSpec("groups.name", ascending=True)`
- [ ] Invalid nested field raises `UnsupportedNestedField` with helpful message

**Group Reader:**
- [ ] `_NESTED_FIELD_REGISTRY` defined with school
- [ ] Field map includes nested fields
- [ ] `search()` with `Filter("school.public_id", EQ, uuid)` returns correct groups

**Query Filter:**
- [ ] Join detection works for dot-notation fields
- [ ] `apply_nested_joins()` injects correct join chain
- [ ] DISTINCT is applied when N:M joins present
- [ ] Field validation rejects unknown nested relations and fields
- [ ] Error messages guide users on allowed paths

**Tests:**
- [ ] Unit tests: join detection, validation, operator compatibility
- [ ] Integration tests: search by group, search by school, intersection queries
- [ ] Edge cases: duplicate handling, invalid nested fields, sort by nested

## Code Map

```
ucsschool-objects/src/ucsschool_objects/core/
├── domain/
│   ├── errors.py                 ← Add UnsupportedNestedField
│   └── __init__.py               ← Export UnsupportedNestedField
├── adapters/sqlalchemy/
│   ├── join_spec.py              ← NEW: JoinSpec dataclass (or inline in readers)
│   ├── readers.py                ← Modify all three reader classes
│   └── query_filter.py           ← Add join detection, injection, validation
└── tests/
    ├── test_query_filter.py      ← Add nested field tests
    └── test_readers.py           ← Add reader integration tests
```

## Design Notes

### Cardinality & Semantics

- `Filter("groups.public_id", EQ, uuid)` alone → ALL users in that group **across all schools**
- To filter by group AND school explicitly: use `And([Filter("schools.public_id", ...), Filter("groups.public_id", ...)])`
- DISTINCT prevents duplicates from N:M relationships (user in same group via multiple school memberships)

### Join Type Strategy

- **LEFT OUTER (default):** Relationship is optional (user may have no groups)
- **INNER (automatic for filters):** When a filter condition is present, we only want matches
- Readers can override via `JoinSpec.join_type` if domain rules require otherwise

### Extensibility

Future work (Group → member_roles, Role → school, etc.) requires only:
1. Add `JoinSpec` to reader's `_NESTED_FIELD_REGISTRY`
2. Update tests
3. No changes to `query_filter.py` or infrastructure

### Performance

- **SQL generation:** Standard SQLAlchemy patterns, leverages query optimizer
- **Index assumptions:** Foreign keys in SchoolMembership, GroupMembership relationships should be indexed (should already exist)
- **DISTINCT overhead:** Minor for typical queries (<=3 nests); acceptable trade-off for correctness
- **Future:** Index strategies and query hints can be added to `JoinSpec` if needed
