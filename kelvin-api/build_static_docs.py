#!/usr/bin/env python3
"""Render readme.rst and changelog.rst to the static HTML files served by the Kelvin REST API."""

from collections.abc import Mapping, Sequence
from pathlib import Path

from docutils import nodes
from docutils.core import publish_file
from docutils.parsers.rst import roles
from docutils.parsers.rst.states import Inliner

BASE_DIR = Path(__file__).resolve().parent
STATIC_DIR = BASE_DIR / "static"


def _uv_bug_role(
    _name: str,
    rawtext: str,
    text: str,
    _lineno: int,
    _inliner: Inliner,
    _options: Mapping[str, object] | None = None,
    _content: Sequence[str] | None = None,
) -> tuple[list[nodes.reference], list[nodes.reference]]:
    bug_id = text.lstrip("#")
    node = nodes.reference(
        rawtext,
        f"#{bug_id}",
        refuri=f"https://forge.univention.org/bugzilla/show_bug.cgi?id={bug_id}",
    )
    return [node], []


def _spelling_ignore_role(
    _name: str,
    _rawtext: str,
    text: str,
    _lineno: int,
    _inliner: Inliner,
    _options: Mapping[str, object] | None = None,
    _content: Sequence[str] | None = None,
) -> tuple[list[nodes.Text], list[nodes.reference]]:
    return [nodes.Text(text)], []


def _register_sphinx_role_stubs() -> None:
    """
    changelog.rst uses these two Sphinx-only roles; register lightweight
    stand-ins so plain docutils can render the file without them.
    """
    roles.register_local_role(name="uv:bug", role_fn=_uv_bug_role)
    # docutils-stubs' _RoleFn alias narrows the return type to reference nodes only,
    # stricter than the real signature (and other role callables in the same stub);
    # a plain Text node is the correct/intended return here.
    roles.register_local_role(
        name="spelling:ignore",
        role_fn=_spelling_ignore_role,  # pyright: ignore[reportArgumentType]
    )


def _render(source: Path, destination: Path) -> None:
    publish_file(source_path=str(source), destination_path=str(destination), writer_name="html5")


def main() -> None:
    _register_sphinx_role_stubs()
    STATIC_DIR.mkdir(parents=True, exist_ok=True)
    _render(
        source=BASE_DIR / "readme.rst",
        destination=STATIC_DIR / "readme.html",
    )
    _render(
        source=BASE_DIR / "changelog.rst",
        destination=STATIC_DIR / "changelog.html",
    )


if __name__ == "__main__":
    main()
