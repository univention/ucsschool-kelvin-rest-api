# Copyright (C) 2026 Univention GmbH
#
# SPDX-License-Identifier: AGPL-3.0-only

"""
Architecture boundary tests enforcing the hexagonal layout.

Uses two complementary strategies:

- **AST-based import scanning** for external library checks (``sqlalchemy``, ``fastapi``,
  ``pydantic``, …).
  ``pytestarch`` only graphs project-internal modules, so external edges are invisible to it.
- **pytestarch rules** for internal cross-package boundary checks
  (e.g.  domain must not import adapters, ``database_models`` must not import the domain).

Layer contract for ``ucsschool_objects``:

- ``core.domain`` - pure, persistence-agnostic domain layer.
  Must be free of framework, persistence, and adapter dependencies.
- ``core.domain.ports`` - ``Protocol`` contracts.
  Even tighter: must reference domain types only.
- ``core.adapters`` - concrete adapter implementations.
  May depend on the domain and on ``database_models``; must not be depended upon by the domain.
  Distinct backends must not cross-import.
- ``database_models`` - internal SQLAlchemy ORM.
  May depend on ``sqlalchemy``; must not depend on the domain, adapters, or public API.
- ``ucsschool_objects`` (top-level) - public API surface.
  Re-exports from ``core.domain`` only.
"""

from __future__ import annotations

import ast
from collections.abc import Iterable, Iterator
from pathlib import Path
from typing import Any, ClassVar

import pytest
from pytestarch import Rule, get_evaluable_architecture

ROOT_DIR = Path(__file__).resolve().parents[1]
SRC_DIR = ROOT_DIR / "src"
PACKAGE_DIR = SRC_DIR / "ucsschool_objects"
DOMAIN_DIR = PACKAGE_DIR / "core" / "domain"
PORTS_DIR = DOMAIN_DIR / "ports"
ADAPTERS_DIR = PACKAGE_DIR / "core" / "adapters"
SQLALCHEMY_ADAPTER_DIR = ADAPTERS_DIR / "sqlalchemy"

PKG = "ucsschool_objects"

# External top-level module names that would signal a persistence, web,
# or test-infrastructure dependency leaking into the domain or ports.
_FORBIDDEN_EXTERNALS = [
    "aiosqlite",
    "asyncpg",
    "fastapi",
    "httpx",
    "psycopg",
    "psycopg2",
    "pydantic",
    "sqlalchemy",
    "starlette",
    "testcontainers",
]

# External top-level module names that have no business in the outer layers
# (adapters, database_models). These layers may legitimately import
# ``sqlalchemy`` but must stay free of web frameworks, validation libraries
# unrelated to the ORM, HTTP clients, and test-only infrastructure.
_FORBIDDEN_OUTER_FRAMEWORKS = [
    "fastapi",
    "httpx",
    "pydantic",
    "starlette",
    "testcontainers",
]


# ---------------------------------------------------------------------------
# AST-based import scanning helpers (external library checks)
# ---------------------------------------------------------------------------


def _iter_py_files(directory: Path) -> Iterator[Path]:
    return (p for p in sorted(directory.rglob("*.py")) if p.is_file())


def _current_package_parts(path: Path) -> list[str]:
    """Return the dotted parts of the package that *path* is a member of.

    ``src/foo/bar.py`` → ``["foo"]``.  ``src/foo/__init__.py`` → ``["foo"]``.
    """
    return list(path.relative_to(SRC_DIR).parent.parts)


def _imports_in_file(path: Path) -> Iterator[str]:
    """Yield every fully-qualified module name referenced by *path*.

    Relative imports are resolved against the file's own package.  Level 1
    stays inside the current package; level N steps N-1 packages upward.
    """
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    current_package = _current_package_parts(path)
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                yield alias.name
        elif isinstance(node, ast.ImportFrom):
            if node.level == 0:
                if node.module is not None:
                    yield node.module
                continue
            base = current_package[: len(current_package) - (node.level - 1)]
            if node.module:
                yield ".".join([*base, node.module])
            elif base:
                yield ".".join(base)


def _collect_imports(directory: Path) -> list[tuple[Path, str]]:
    return [(path, module) for path in _iter_py_files(directory) for module in _imports_in_file(path)]


def _top_level(module: str) -> str:
    return module.partition(".")[0]


def _format_violations(layer_name: str, violations: Iterable[tuple[Path, str]]) -> str:
    return f"Architecture violation ({layer_name}):\n" + "\n".join(
        f"  {path.relative_to(ROOT_DIR)}  ->  {module}" for path, module in violations
    )


def _assert_no_external_import(
    layer_name: str,
    imports: Iterable[tuple[Path, str]],
    forbidden: str,
) -> None:
    violations = [(path, module) for path, module in imports if _top_level(module) == forbidden]
    assert not violations, _format_violations(f"{layer_name} -> {forbidden}", violations)


def _assert_no_import_from(
    layer_name: str,
    imports: Iterable[tuple[Path, str]],
    prefix: str,
) -> None:
    """Fail if any file imports *prefix* directly or any of its sub-modules."""
    violations = [
        (path, module) for path, module in imports if module == prefix or module.startswith(f"{prefix}.")
    ]
    assert not violations, _format_violations(f"{layer_name} -> {prefix}", violations)


def _assert_no_top_level_reexport_import(
    layer_name: str,
    imports: Iterable[tuple[Path, str]],
    package: str,
) -> None:
    """Fail if any file does ``import <package>`` or ``from <package> import ...``.

    This is the correct check for "don't route through the public API re-export"
    because the AST scanner yields the exact module name from the import
    statement: ``from ucsschool_objects import X`` yields ``"ucsschool_objects"``
    (exactly *package*), while ``from ucsschool_objects.core.domain.X import Y``
    yields ``"ucsschool_objects.core.domain.X"`` (a sub-module path, not *package*).
    """
    violations = [(path, module) for path, module in imports if module == package]
    assert not violations, _format_violations(
        f"{layer_name} -> {package} (top-level re-export)", violations
    )


# ---------------------------------------------------------------------------
# pytestarch fixture
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def evaluable() -> Any:
    """Evaluable architecture for the ``ucsschool_objects`` package."""
    return get_evaluable_architecture(str(PACKAGE_DIR), str(PACKAGE_DIR))


# ===================================================================
# AST-based: external library bans
# ===================================================================


class TestDomainHasNoExternalFrameworkImports:
    """``core.domain`` must depend only on stdlib.

    pytestarch cannot see edges to external packages, so the ban on
    ``sqlalchemy``/``fastapi``/``pydantic``/… is enforced by scanning
    every file's AST.
    """

    _imports: ClassVar[list[tuple[Path, str]]] = []

    @classmethod
    def setup_class(cls) -> None:
        cls._imports = _collect_imports(DOMAIN_DIR)

    @pytest.mark.parametrize("forbidden", _FORBIDDEN_EXTERNALS)
    def test_no_external_import(self, forbidden: str) -> None:
        _assert_no_external_import("domain", self._imports, forbidden)


class TestPortsHaveNoExternalFrameworkImports:
    """``core.domain.ports`` must depend only on stdlib and domain types."""

    _imports: ClassVar[list[tuple[Path, str]]] = []

    @classmethod
    def setup_class(cls) -> None:
        cls._imports = _collect_imports(PORTS_DIR)

    @pytest.mark.parametrize("forbidden", _FORBIDDEN_EXTERNALS)
    def test_no_external_import(self, forbidden: str) -> None:
        _assert_no_external_import("ports", self._imports, forbidden)


class TestAdaptersHaveNoOuterFrameworkImports:
    """``core.adapters`` may import ``sqlalchemy`` but no web/validation/HTTP frameworks."""

    _imports: ClassVar[list[tuple[Path, str]]] = []

    @classmethod
    def setup_class(cls) -> None:
        cls._imports = _collect_imports(ADAPTERS_DIR)

    @pytest.mark.parametrize("forbidden", _FORBIDDEN_OUTER_FRAMEWORKS)
    def test_no_external_import(self, forbidden: str) -> None:
        _assert_no_external_import("adapters", self._imports, forbidden)


class TestDatabaseModelsHaveNoOuterFrameworkImports:
    """``database_models`` may import ``sqlalchemy`` but no web/validation/HTTP frameworks."""

    _imports: ClassVar[list[tuple[Path, str]]] = []

    @classmethod
    def setup_class(cls) -> None:
        database_models_file = PACKAGE_DIR / "database_models.py"
        cls._imports = [(database_models_file, m) for m in _imports_in_file(database_models_file)]

    @pytest.mark.parametrize("forbidden", _FORBIDDEN_OUTER_FRAMEWORKS)
    def test_no_external_import(self, forbidden: str) -> None:
        _assert_no_external_import("database_models", self._imports, forbidden)


# ===================================================================
# adapter backend isolation (AST-based)
# ===================================================================


class TestAdapterBackendIsolation:
    """Distinct adapter backends under ``core.adapters`` must not cross-import.

    pytestarch has no direct "X under Y but not under Z" predicate, so we
    scan the SQLAlchemy backend's imports and assert that any reference
    into ``core.adapters`` stays within the SQLAlchemy subtree.

    Only the SQLAlchemy backend exists today; this test becomes meaningful
    once a sibling backend (e.g. LDAP or in-memory) is added.
    """

    def test_sqlalchemy_stays_in_its_backend(self) -> None:
        sqlalchemy_pkg = f"{PKG}.core.adapters.sqlalchemy"
        adapter_prefix = f"{PKG}.core.adapters."
        violations = [
            (path, module)
            for path, module in _collect_imports(SQLALCHEMY_ADAPTER_DIR)
            if module.startswith(adapter_prefix)
            and not (module == sqlalchemy_pkg or module.startswith(f"{sqlalchemy_pkg}."))
        ]
        assert not violations, _format_violations("sqlalchemy adapter -> sibling backend", violations)


# ===================================================================
# internal cross-package boundaries (pytestarch)
# ===================================================================


class TestDomainBoundaries:
    """The domain layer must not depend on adapters or ``database_models``."""

    def test_domain_does_not_import_adapters(self, evaluable: Any) -> None:
        rule = (
            Rule()
            .modules_that()
            .are_sub_modules_of(f"{PKG}.core.domain")
            .should_not()
            .import_modules_that()
            .are_sub_modules_of(f"{PKG}.core.adapters")
        )
        rule.assert_applies(evaluable)

    def test_domain_does_not_import_database_models(self, evaluable: Any) -> None:
        rule = (
            Rule()
            .modules_that()
            .are_sub_modules_of(f"{PKG}.core.domain")
            .should_not()
            .import_modules_that()
            .have_name_matching(f"{PKG}.database_models")
        )
        rule.assert_applies(evaluable)

    def test_domain_does_not_import_public_api(self) -> None:
        """Domain code must not route through the top-level re-export.

        pytestarch cannot express "only the __init__.py, not its sub-modules"
        because it always expands a matched module to its full sub-module tree.
        The AST scanner distinguishes ``from ucsschool_objects import X`` (the
        re-export) from ``from ucsschool_objects.core.domain.X import Y``
        (a direct sub-module path).
        """
        _assert_no_top_level_reexport_import("domain", _collect_imports(DOMAIN_DIR), PKG)


class TestPortsBoundaries:
    """Ports must not depend on adapters, ``database_models``, or concrete validators."""

    def test_ports_do_not_import_adapters(self, evaluable: Any) -> None:
        rule = (
            Rule()
            .modules_that()
            .are_sub_modules_of(f"{PKG}.core.domain.ports")
            .should_not()
            .import_modules_that()
            .are_sub_modules_of(f"{PKG}.core.adapters")
        )
        rule.assert_applies(evaluable)

    def test_ports_do_not_import_database_models(self, evaluable: Any) -> None:
        rule = (
            Rule()
            .modules_that()
            .are_sub_modules_of(f"{PKG}.core.domain.ports")
            .should_not()
            .import_modules_that()
            .have_name_matching(f"{PKG}.database_models")
        )
        rule.assert_applies(evaluable)

    def test_ports_do_not_import_validators(self, evaluable: Any) -> None:
        """Port contracts must stay free of concrete validation logic."""
        rule = (
            Rule()
            .modules_that()
            .are_sub_modules_of(f"{PKG}.core.domain.ports")
            .should_not()
            .import_modules_that()
            .have_name_matching(f"{PKG}.core.domain.validators")
        )
        rule.assert_applies(evaluable)

    def test_ports_do_not_import_public_api(self) -> None:
        """Ports must not route through the top-level re-export."""
        _assert_no_top_level_reexport_import("ports", _collect_imports(PORTS_DIR), PKG)


class TestAdaptersBoundaries:
    """Adapters may import the domain and ``database_models``; nothing else internal."""

    def test_adapters_do_not_import_public_api(self) -> None:
        """Adapters should reach for concrete modules, not the re-export."""
        _assert_no_top_level_reexport_import("adapters", _collect_imports(ADAPTERS_DIR), PKG)

    def test_adapters_do_not_import_intermediate_domain_facade(self) -> None:
        """Adapters must reach concrete domain modules, not the ``core.domain`` facade.

        The ``core.domain/__init__.py`` and ``core.domain.ports/__init__.py``
        modules are intentionally empty so that internal callers depend on
        concrete modules (``models``, ``query``, ``ports.manager``, …).
        """
        for facade in (f"{PKG}.core.domain", f"{PKG}.core.domain.ports"):
            _assert_no_top_level_reexport_import("adapters", _collect_imports(ADAPTERS_DIR), facade)


class TestDatabaseModelsBoundaries:
    """``database_models`` must remain an ORM island."""

    def test_database_models_does_not_import_domain(self, evaluable: Any) -> None:
        rule = (
            Rule()
            .modules_that()
            .have_name_matching(f"{PKG}.database_models")
            .should_not()
            .import_modules_that()
            .are_sub_modules_of(f"{PKG}.core.domain")
        )
        rule.assert_applies(evaluable)

    def test_database_models_does_not_import_adapters(self, evaluable: Any) -> None:
        rule = (
            Rule()
            .modules_that()
            .have_name_matching(f"{PKG}.database_models")
            .should_not()
            .import_modules_that()
            .are_sub_modules_of(f"{PKG}.core.adapters")
        )
        rule.assert_applies(evaluable)

    def test_database_models_does_not_import_public_api(self) -> None:
        database_models_file = PACKAGE_DIR / "database_models.py"
        _assert_no_top_level_reexport_import(
            "database_models",
            [(database_models_file, m) for m in _imports_in_file(database_models_file)],
            PKG,
        )


class TestPublicAPISurface:
    """The top-level re-export must expose only the domain layer.

    pytestarch cannot target a single ``__init__.py`` without also pulling in
    all sub-modules (it always expands a matched module to its full sub-module
    tree).  The AST scanner operates on the file directly.
    """

    _imports: ClassVar[list[tuple[Path, str]]] = []

    @classmethod
    def setup_class(cls) -> None:
        init_file = PACKAGE_DIR / "__init__.py"
        cls._imports = [(init_file, m) for m in _imports_in_file(init_file)]

    def test_public_api_does_not_expose_adapters(self) -> None:
        _assert_no_import_from("public API", self._imports, f"{PKG}.core.adapters")

    def test_public_api_does_not_expose_database_models(self) -> None:
        _assert_no_import_from("public API", self._imports, f"{PKG}.database_models")
