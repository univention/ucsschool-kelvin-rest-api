#!/usr/bin/env python3
"""Render readme.rst and changelog.rst to the static HTML files served by the Kelvin REST API."""

from pathlib import Path

from docutils import nodes
from docutils.core import publish_file
from docutils.parsers.rst import roles

BASE_DIR = Path(__file__).resolve().parent
STATIC_DIR = BASE_DIR / "static"


def _uv_bug_role(name, rawtext, text, lineno, inliner, options=None, content=None):
    bug_id = text.lstrip("#")
    node = nodes.reference(
        rawtext,
        f"#{bug_id}",
        refuri=f"https://forge.univention.org/bugzilla/show_bug.cgi?id={bug_id}",
    )
    return [node], []


def _spelling_ignore_role(name, rawtext, text, lineno, inliner, options=None, content=None):
    return [nodes.Text(text)], []


def _register_sphinx_role_stubs():
    # changelog.rst uses these two Sphinx-only roles; register lightweight
    # stand-ins so plain docutils can render the file without them.
    roles.register_local_role("uv:bug", _uv_bug_role)
    roles.register_local_role("spelling:ignore", _spelling_ignore_role)


def _render(source, destination):
    publish_file(source_path=str(source), destination_path=str(destination), writer_name="html5")


def main():
    _register_sphinx_role_stubs()
    STATIC_DIR.mkdir(parents=True, exist_ok=True)
    _render(BASE_DIR / "readme.rst", STATIC_DIR / "readme.html")
    _render(BASE_DIR / "changelog.rst", STATIC_DIR / "changelog.html")


if __name__ == "__main__":
    main()
