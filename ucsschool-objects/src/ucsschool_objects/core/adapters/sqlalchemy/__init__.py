"""Client-facing re-exports for the SQLAlchemy backend.

Intended for ``ucsschool_objects`` *clients* (composition roots, FastAPI
wiring, CLI scripts) so they can import managers and session helpers from a
single, stable path.

Do NOT import these symbols from inside the ``ucsschool_objects`` package.
Internal modules must use the deep paths (e.g. ``...managers.group_manager``)
so the package keeps a one-direction dependency graph and the public surface
stays free to change without ripple effects.
"""

from .dn_mapper import SQLAlchemyDNIDMapper, sqlalchemy_mapper_factory
from .managers.group_manager import SQLAlchemyGroupManager
from .managers.role_manager import SQLAlchemyRoleManager
from .managers.school_manager import SQLAlchemySchoolManager
from .managers.user_manager import SQLAlchemyUserManager
from .session import (
    DatabaseSettings,
    KelvinSqlAlchemySession,
    KelvinSqlAlchemySessionFactory,
    build_engine,
    build_kelvin_storage_session_factory,
    build_session_factory,
    build_settings,
)

__all__ = [
    # Managers
    "SQLAlchemyDNIDMapper",
    "SQLAlchemyGroupManager",
    "SQLAlchemyRoleManager",
    "SQLAlchemySchoolManager",
    "SQLAlchemyUserManager",
    # Session / engine helpers
    "build_engine",
    "build_kelvin_storage_session_factory",
    "build_session_factory",
    "build_settings",
    "DatabaseSettings",
    "KelvinSqlAlchemySession",
    "KelvinSqlAlchemySessionFactory",
    # Factory functions
    "sqlalchemy_mapper_factory",
]
