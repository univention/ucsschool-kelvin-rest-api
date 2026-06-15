"""ucsschool-objects — public API.

Import domain objects, the query DSL, exceptions, and the Manager port from
this top-level package. The concrete SQLAlchemy adapter managers live one
level deeper at ``ucsschool_objects.core.adapters.sqlalchemy`` and are
intentionally not promoted here — they are a wiring-time concern.

The ``database_models`` module is *internal*. It contains the SQLAlchemy ORM
models used by the adapters and is not part of the public API. Its contents
may change without notice.
"""

from ucsschool_objects.core.domain.errors import (
    CorelibError,
    EmptyAndClause,
    EmptyOrClause,
    InvalidFilter,
    InvalidInFilter,
    InvalidJsonFilter,
    InvalidPatternFilter,
    InvalidRangeFilter,
    InvalidUuidFilter,
    NotFound,
    UnsupportedFilterField,
    UnsupportedFilterOperator,
    UnsupportedOperation,
    UnsupportedSortField,
)
from ucsschool_objects.core.domain.load_spec import LoadSpec
from ucsschool_objects.core.domain.models import (
    UNLOADED,
    UNSET,
    Group,
    Role,
    School,
    SchoolMembership,
    UnloadedType,
    UnsetType,
    User,
)
from ucsschool_objects.core.domain.patch import track_changes
from ucsschool_objects.core.domain.ports.dn_mapper import DNIDMapper, ObjectType
from ucsschool_objects.core.domain.ports.manager import Manager
from ucsschool_objects.core.domain.ports.unit_of_work import (
    KelvinStorageSession,
    KelvinStorageSessionFactory,
)
from ucsschool_objects.core.domain.query import (
    And,
    Filter,
    FilterInValue,
    FilterScalarValue,
    FilterValue,
    Not,
    Operator,
    Or,
    QueryExpr,
    SearchQuery,
    SortSpec,
    make_wildcard_filter,
)

__all__ = [
    # Domain entities
    "Group",
    "Role",
    "School",
    "SchoolMembership",
    "track_changes",
    "UNLOADED",
    "UnloadedType",
    "UNSET",
    "UnsetType",
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
    "make_wildcard_filter",
    # Exceptions
    "CorelibError",
    "EmptyAndClause",
    "EmptyOrClause",
    "InvalidFilter",
    "InvalidInFilter",
    "InvalidJsonFilter",
    "InvalidPatternFilter",
    "InvalidRangeFilter",
    "InvalidUuidFilter",
    "NotFound",
    "UnsupportedFilterField",
    "UnsupportedFilterOperator",
    "UnsupportedOperation",
    "UnsupportedSortField",
    # Ports
    "KelvinStorageSession",
    "KelvinStorageSessionFactory",
    "Manager",
    # DN Mapping
    "DNIDMapper",
    "ObjectType",
]
