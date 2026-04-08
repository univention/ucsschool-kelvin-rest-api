from __future__ import annotations


class CorelibError(Exception):
    """Base exception for core library domain errors."""


class InvalidFilter(CorelibError):
    """Raised when a query filter is invalid for a resource or operator."""


class UnsupportedOperation(CorelibError):
    """Raised when a caller requests unsupported read/search behavior."""


class NotFound(CorelibError):
    """Raised when a requested object is not found."""
