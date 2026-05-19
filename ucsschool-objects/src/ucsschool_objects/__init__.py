"""ucsschool-objects — public API.

Import domain objects, the query DSL, exceptions, and the Manager port from
this top-level package.  The concrete SQLAlchemy adapter managers live one
level deeper at ``ucsschool_objects.core.adapters.sqlalchemy`` and are
intentionally not promoted here — they are a wiring-time concern.

The ``database_models`` module is *internal*.  It contains the SQLAlchemy ORM
models used by the adapters and is not part of the public API.  Its contents
may change without notice.
"""

from ucsschool_objects.core.adapters.sqlalchemy.dn_mapper import (
    SQLAlchemyDNIDMapper,
    sqlalchemy_mapper_factory,
)
from ucsschool_objects.core.domain import (  # Domain entities; Query DSL; Exceptions
    UNLOADED,
    And,
    CorelibError,
    EmptyAndClause,
    EmptyOrClause,
    Filter,
    FilterInValue,
    FilterScalarValue,
    FilterValue,
    Group,
    InvalidFilter,
    InvalidInFilter,
    InvalidLikeFilter,
    InvalidRangeFilter,
    KelvinStorageSession,
    KelvinStorageSessionFactory,
    LoadSpec,
    Manager,
    Not,
    NotFound,
    Operator,
    Or,
    QueryExpr,
    Role,
    School,
    SchoolMembership,
    SearchQuery,
    SortSpec,
    UnloadedType,
    UnsupportedFilterField,
    UnsupportedFilterOperator,
    UnsupportedOperation,
    UnsupportedSortField,
    User,
)
from ucsschool_objects.core.domain.ports.dn_mapper import DNIDMapper, ObjectType

__all__ = [
    # Domain entities
    "Group",
    "Role",
    "School",
    "SchoolMembership",
    "UNLOADED",
    "UnloadedType",
    "User",
    # Query DSL
    "And",
    "Filter",
    "FilterInValue",
    "FilterScalarValue",
    "FilterValue",
    "LoadSpec",
    "Not",
    "Operator",
    "Or",
    "QueryExpr",
    "SearchQuery",
    "SortSpec",
    # Exceptions
    "CorelibError",
    "EmptyAndClause",
    "EmptyOrClause",
    "InvalidFilter",
    "InvalidInFilter",
    "InvalidLikeFilter",
    "InvalidRangeFilter",
    "NotFound",
    "UnsupportedFilterField",
    "UnsupportedFilterOperator",
    "UnsupportedOperation",
    "UnsupportedSortField",
    # Ports
    "DNIDMapper",
    "KelvinStorageSession",
    "KelvinStorageSessionFactory",
    "Manager",
    "ObjectType",
    # DN mapper adapter
    "SQLAlchemyDNIDMapper",
    "sqlalchemy_mapper_factory",
]
