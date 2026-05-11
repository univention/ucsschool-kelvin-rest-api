from __future__ import annotations


class CorelibError(Exception):
    """Base exception for core library domain errors."""


class InvalidFilter(CorelibError):
    """Base exception for invalid query filter and sort expressions."""


class UnsupportedFilterField(InvalidFilter):
    """Raised when a filter references a field that the manager does not support."""

    def __init__(self, field: str) -> None:
        self.field = field
        super().__init__(f"Unsupported field: {field!r}")


class UnsupportedSortField(InvalidFilter):
    """Raised when sorting is requested on an unsupported field."""

    def __init__(self, field: str) -> None:
        self.field = field
        super().__init__(f"Unsupported sort field: {field!r}")


class InvalidInFilter(InvalidFilter):
    """Raised when an IN filter receives a non-iterable value."""

    def __init__(self, field: str, value: object) -> None:
        self.field = field
        self.value = value
        super().__init__(f"IN operator requires an iterable value for field {field!r}; got {value!r}")


class InvalidLikeFilter(InvalidFilter):
    """Raised when a LIKE filter receives a non-string value."""

    def __init__(self, field: str, value: object) -> None:
        self.field = field
        self.value = value
        super().__init__(f"LIKE operator requires a string value for field {field!r}; got {value!r}")


class InvalidRangeFilter(InvalidFilter):
    """Raised when a range operator is used with an unsupported field or value."""

    def __init__(self, field: str, operator: object, value: object) -> None:
        self.field = field
        self.operator = operator
        self.value = value
        operator_name = str(operator)
        if hasattr(operator, "name"):
            operator_name = str(operator.name)
        super().__init__(
            f"{operator_name} operator requires a numeric or date-like field and non-null value "
            f"for field {field!r}; got {value!r}"
        )


class UnsupportedFilterOperator(InvalidFilter):
    """Raised when a filter uses an operator the backend does not support."""

    def __init__(self, field: str, operator: object) -> None:
        self.field = field
        self.operator = operator
        super().__init__(f"Unsupported operator {operator!r} for field {field!r}")


class UnsupportedNestedField(InvalidFilter):
    """Raised when a nested field query references an unsupported relationship or field."""

    def __init__(
        self,
        nested_field: str,
        root_relation: str = "",
        allowed_relations: list[str] | None = None,
        reason: str = "",
        supported_fields: list[str] | None = None,
    ) -> None:
        self.nested_field = nested_field
        self.root_relation = root_relation
        self.allowed_relations = allowed_relations or []
        self.reason = reason
        self.supported_fields = supported_fields or []

        msg = f"Unsupported nested field: {nested_field!r}"
        if reason:
            msg += f" ({reason})"

        if supported_fields:
            msg += f". Supported fields: {', '.join(supported_fields)}"

        if root_relation and allowed_relations:
            msg += f". Unknown relation '{root_relation}'. Allowed: {', '.join(allowed_relations)}"

        super().__init__(msg)


class EmptyAndClause(InvalidFilter):
    """Raised when an And expression contains no clauses."""

    def __init__(self) -> None:
        super().__init__("AND query requires at least one clause")


class EmptyOrClause(InvalidFilter):
    """Raised when an Or expression contains no clauses."""

    def __init__(self) -> None:
        super().__init__("OR query requires at least one clause")


class UnsupportedOperation(CorelibError):
    """Raised when a caller requests unsupported read/search behavior."""


class NotFound(CorelibError):
    """Raised when a requested object is not found."""

    def __init__(self, object_type: str, public_id: str) -> None:
        self.object_type = object_type
        self.public_id = public_id
        super().__init__(f"{object_type} with public_id={public_id!r} was not found.")
