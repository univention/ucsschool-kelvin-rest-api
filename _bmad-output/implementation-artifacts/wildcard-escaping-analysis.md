---
status: draft
title: "Wildcard Character Escaping in LIKE Queries — Architecture Analysis"
date: 2026-06-15
---

# Wildcard Character Escaping in LIKE Queries — Architecture Analysis

## Executive Summary

The Kelvin v2 REST API supports SQL `LIKE` wildcard queries via the `*` character in search parameters. Currently, **no escaping is performed on the user input before translation to SQL `%`**, creating a **LIKE pattern injection vector** where unescaped `%` and `_` characters in user input are treated as SQL LIKE metacharacters instead of literal characters.

This analysis identifies the issue, documents current state, and proposes three architecture options for remediation.

---

## Problem Statement

### Current Behavior

Routers in `kelvin-api/routers/v2/` convert user-provided `*` to SQL `%` for wildcard searches:

```python
# kelvin-api/routers/v2/user.py (line 96-98)
def _str_filter(field: str, value: str) -> Filter:
    if "*" in value:
        return Filter(field=field, op=Operator.LIKE, value=value.replace("*", "%"))
    return Filter(field=field, op=Operator.EQ, value=value)
```

**Issue**: If user provides `name="foo%"` or `name="test_bar"`, the `%` and `_` are passed directly to SQL LIKE, where they act as metacharacters:
- `%` matches zero or more characters (wildcard)
- `_` matches exactly one character (single-char wildcard)

### Attack Vector Example

```http
GET /users/?name=50%
```

Expected: Find users named literally "50%"
Actual: Finds users matching "50" followed by ANY characters ("50a", "500", "5000", etc.)

---

## Root Cause Analysis

### 1. Duplicated Implementation (No DRY)

The wildcard transformation logic is duplicated across **4 files**:

| File | Location | Code |
|------|----------|------|
| `school.py` | line 68 | `value.replace("*", "%")` |
| `workgroup.py` | line 87 | `value.replace("*", "%")` |
| `school_class.py` | line 85 | `value.replace("*", "%")` |
| `user.py` | line 98 | `value.replace("*", "%")` |

Additionally, UDM property filters in `user.py` (line 145) duplicate the pattern:

```python
filters.append(Filter(field=field, op=Operator.LIKE, value=value.replace("*", "%")))
```

### 2. No Centralized Escaping Logic

- Core library (`ucsschool-objects/`) has no wildcard escaping function
- Query filter layer (`query_filter.py`, lines 379-380) applies LIKE/ILIKE without escaping
- Each router must independently implement escaping (but none do)

### 3. No Test Coverage for Escaping

Existing LIKE tests in `test_query_contracts.py` use hardcoded patterns like `"alpha%"` but do NOT test:
- User-provided `%` in input
- User-provided `_` in input  
- Edge cases like `"50%"`, `"test_bar"`, `"100%_discount"`

### 4. Explicit TODOs Flagging This

| File | Line | TODO |
|------|------|------|
| `school_class.py` | 83 | `# TODO support * as wildcard and escape %` |
| `user.py` | 125 | `# TODO support * as wildcard` (UDM context) |

---

## Technical Specification of the Issue

### SQL LIKE Metacharacters

In ANSI SQL LIKE pattern matching:
- `%` = matches any sequence of zero or more characters
- `_` = matches exactly one character
- `\` (or other ESCAPE char) = escape character to match `%` or `_` literally

### Standard Escaping Pattern

To match the literal string `"50%"` in SQL, the pattern must be escaped:

```sql
SELECT * FROM users WHERE name LIKE '50\%' ESCAPE '\'
```

SQLAlchemy supports this via the `.like()` method with escape parameter:

```python
column.like('50\\%', escape='\\')
```

However, the current `Filter` dataclass in `ucsschool_objects` does not expose escape configuration.

### Current Vulnerability

```python
user_input = "test_"
pattern = user_input.replace("*", "%")  # → "test_"
# SQLAlchemy generates: WHERE name LIKE 'test_'
# This matches "testa", "testb", "testx", etc. (not just "test_")
```

---

## Current State Assessment

### What Works ✅

- SQLAlchemy expressions prevent SQL injection (values are parameterized)
- Filter construction is type-safe via enums
- LIKE/ILIKE operators are recognized and tested

### What's Broken ❌

- **No escaping** of `%` in user input before LIKE translation
- **No escaping** of `_` in user input before LIKE translation
- **Duplicated code** across 4 routers (not maintainable)
- **No test coverage** for literal `%` or `_` in search values
- **Missing centralization** in core library

---

## Architecture Options

### Option A: Simple Escape Helper in Each Router

**Implementation**: Add escape function to each of the 4 routers.

```python
def escape_like_chars(value: str) -> str:
    """Escape SQL LIKE metacharacters."""
    # Backslash must be escaped first
    return value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")

def _str_filter(field: str, value: str) -> Filter:
    if "*" in value:
        pattern = value.replace("*", "%")
        escaped = escape_like_chars(pattern)
        return Filter(field=field, op=Operator.LIKE, value=escaped)
    return Filter(field=field, op=Operator.EQ, value=value)
```

**Pros**:
- ✅ Simple, explicit, localized change
- ✅ No core library changes
- ✅ Easy to understand

**Cons**:
- ❌ Duplicated across 4 files (violates DRY)
- ❌ Escape logic not in core library where it belongs
- ❌ Hard to maintain (fix in 4 places)
- ❌ Risk of inconsistency if one router missed

---

### Option B: Extend Filter Dataclass with Escape Parameter

**Implementation**: Extend core `Filter` class to support escape configuration.

```python
# ucsschool_objects/core/domain/query.py
@dataclass(frozen=True)
class Filter:
    field: str
    op: Operator
    value: FilterValue
    escape_char: str | None = None  # NEW

# ucsschool_objects/core/adapters/sqlalchemy/query_filter.py
FILTER_OPERATOR_BUILDERS[Operator.LIKE] = lambda column, value, escape: (
    column.like(value, escape=escape) if escape else column.like(value)
)
```

**Pros**:
- ✅ Centralized in core library
- ✅ Explicit escape intent
- ✅ Flexible (routers specify which escape char to use)

**Cons**:
- ❌ Requires changes to Filter dataclass API
- ❌ Requires updates to all Filter creation code
- ❌ More complex signature for LIKE builder
- ❌ May break existing code relying on Filter structure

---

### Option C: Hybrid — Factory Function in Core + Use in Routers (RECOMMENDED)

**Implementation**: Add a factory function in the core library; routers use it consistently.

```python
# ucsschool_objects/core/domain/query.py
def make_wildcard_filter(
    field: str,
    user_value: str,
    escape_char: str = "\\",
) -> Filter:
    """Create a LIKE filter with wildcard support and proper escaping.
    
    - Converts user `*` to SQL `%` wildcard
    - Escapes literal `%` and `_` in the input
    - Returns a Filter ready for SQLAlchemy translation
    
    Args:
        field: Field name to filter on
        user_value: User-provided search value (may contain `*` for wildcard)
        escape_char: Character to use for escaping (default: backslash)
    
    Returns:
        Filter with LIKE operator and properly escaped value
    
    Example:
        >>> f = make_wildcard_filter("name", "test%")
        >>> f.value
        'test\\%'  # Escaped to match literal %
        
        >>> f = make_wildcard_filter("name", "test*")
        >>> f.value
        'test%'  # * replaced with % for SQL wildcard
    """
    # Escape backslash first to avoid double-escaping
    escaped = user_value.replace("\\", "\\\\")
    # Escape literal LIKE metacharacters
    escaped = escaped.replace("%", f"{escape_char}%")
    escaped = escaped.replace("_", f"{escape_char}_")
    # Convert user wildcard to SQL wildcard
    pattern = escaped.replace("*", "%")
    
    return Filter(field=field, op=Operator.LIKE, value=pattern)
```

Usage in routers:

```python
# kelvin-api/routers/v2/user.py
from ucsschool_objects.core.domain.query import make_wildcard_filter

def _str_filter(field: str, value: str) -> Filter:
    return make_wildcard_filter(field, value) if "*" in value else Filter(...)
    
# Or even simpler (always use the factory):
_str_filter = lambda field, value: make_wildcard_filter(field, value)
```

**Pros**:
- ✅ **Centralized** — logic lives in core library where it belongs
- ✅ **DRY** — single implementation, reused by all routers
- ✅ **Testable** — comprehensive unit tests in core library
- ✅ **Non-breaking** — no changes to Filter dataclass
- ✅ **Explicit** — clear intent from function name
- ✅ **Maintainable** — fix in one place
- ✅ **Extensible** — easy to add options (e.g., different escape chars)

**Cons**:
- ⚠️ Requires coordination across multiple routers
- ⚠️ Need to add tests in core library
- ⚠️ Requires minor updates to 4 router files

**Adoption Path**:
1. Add `make_wildcard_filter()` to `ucsschool_objects/core/domain/query.py`
2. Add comprehensive tests to `ucsschool_objects/tests/core/domain/`
3. Update each of 4 routers to use factory (remove local `_str_filter`)
4. Add tests to router tests for integration verification
5. Deprecate local `_str_filter` functions

---

## Comparative Analysis

| Criterion | Option A | Option B | Option C |
|-----------|----------|----------|----------|
| **Centralization** | ❌ Duplicated | ✅ Core | ✅ Core |
| **DRY** | ❌ Not DRY | ✅ DRY | ✅ DRY |
| **Breaking Changes** | ✅ None | ❌ Filter API | ✅ None |
| **Testing** | ⚠️ Router tests only | ✅ Core tests | ✅ Core + router tests |
| **Maintainability** | ❌ Hard (4 places) | ✅ Easy (1 place) | ✅ Easy (1 place) |
| **Ease of Adoption** | ✅ Simple | ❌ Complex | ✅ Simple |
| **Risk** | ⚠️ Inconsistency | ⚠️ API change | ✅ Low |

---

## Recommendation

**Option C (Hybrid Factory)** is the recommended approach because it:

1. **Centralizes logic** in the core library (single source of truth)
2. **Maintains DRY principle** (one implementation, 4 users)
3. **Requires no API changes** (backward compatible)
4. **Enables comprehensive testing** (core library test suite)
5. **Simplifies adoption** (routers just import and use)
6. **Reduces risk** (no breaking changes)
7. **Follows best practice** (business logic in domain layer, not routers)

---

## Proposed Implementation Checklist

- [ ] **Phase 1: Core Library**
  - [ ] Add `make_wildcard_filter()` to `ucsschool_objects/core/domain/query.py`
  - [ ] Add unit tests covering:
    - [ ] Literal `%` in input
    - [ ] Literal `_` in input
    - [ ] Mixed `*` and `%` wildcards
    - [ ] Edge cases (`"%%"`, `"__"`, `"*%*_*"`)
    - [ ] Backslash escaping
  - [ ] Document function with examples

- [ ] **Phase 2: Router Updates**
  - [ ] Update `kelvin-api/routers/v2/user.py`
  - [ ] Update `kelvin-api/routers/v2/school.py`
  - [ ] Update `kelvin-api/routers/v2/workgroup.py`
  - [ ] Update `kelvin-api/routers/v2/school_class.py`
  - [ ] Remove local `_str_filter()` functions
  - [ ] Also update UDM property filter at line 145

- [ ] **Phase 3: Testing**
  - [ ] Add integration tests for each router
  - [ ] Verify existing tests still pass
  - [ ] Test with real escape patterns

- [ ] **Phase 4: Documentation**
  - [ ] Add docstring examples to `make_wildcard_filter()`
  - [ ] Update API documentation if needed
  - [ ] Add changelog entry

---

## Questions for Architect

1. **API Stability**: Is Option C acceptable, or is Option B (extending Filter) preferred for long-term API clarity?

2. **Escape Character**: Should we always use `\` or make it configurable? Current proposal uses `\` (backslash) per ANSI SQL standard.

3. **ILIKE Support**: Should `make_wildcard_filter()` have a parameter to choose between LIKE and ILIKE, or should routers handle that separately?

4. **UDM Properties**: Should we handle the UDM property wildcard context (line 145 in user.py) the same way, or does it need special handling?

5. **Error Handling**: Should we validate/sanitize input (e.g., reject nulls, very long strings), or pass through as-is?

6. **Backward Compatibility**: Can we safely remove the local `_str_filter()` functions, or do we need a deprecation period?

---

## Next Steps

1. **Architect Review**: Present this analysis to Winston (architect) for feedback on recommended approach
2. **Refinement**: Adjust recommendation based on architecture constraints
3. **Implementation**: Create task(s) and implement in sprint
4. **Review**: Code review with focus on test coverage and edge cases
