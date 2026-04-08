"""Hexagonal read/search core for Kelvin V2 school objects.

This package intentionally does not execute UDM hooks or Kelvin PyHooks.
"""

from ucsschool_objects.core.domain import UNLOADED, Group, LoadSpec, School, UnloadedType, User
from ucsschool_objects.core.ports import GroupReader, SchoolReader, UserReader
from ucsschool_objects.core.query import And, Filter, Operator, Or, SearchQuery, SortSpec

__all__ = [
    "And",
    "Filter",
    "Group",
    "GroupReader",
    "LoadSpec",
    "Operator",
    "Or",
    "School",
    "SchoolReader",
    "SearchQuery",
    "SortSpec",
    "UNLOADED",
    "UnloadedType",
    "User",
    "UserReader",
]
