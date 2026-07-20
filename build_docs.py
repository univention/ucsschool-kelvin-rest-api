#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 Univention GmbH
# SPDX-License-Identifier: AGPL-3.0-only
"""Render the Kelvin REST API's readme and changelog from reStructuredText.

A single Sphinx build produces every HTML artifact the project needs, so the
App Center changelog and the pages served by the running API can never drift:

* ``changelog.html`` -- the changelog as a bare content fragment, uploaded to
  the App Center listing (see the ``build_changelog_html`` CI job).
* ``kelvin-api/static/{changelog,readme}.html`` -- self-contained, styled pages
  served by the API at ``/ucsschool/kelvin/v1/{changelog,readme}``.

Sphinx (rather than plain docutils) is used so the Univention-specific roles in
``changelog.rst`` -- ``:uv:bug:`` and ``:spelling:ignore:`` -- render exactly as
they do in the published documentation, without re-implementing them here.
"""

import subprocess
import tempfile
from pathlib import Path

from lxml import html

REPO_ROOT = Path(__file__).resolve().parent
KELVIN_API_DIR = REPO_ROOT / "kelvin-api"
STATIC_DIR = KELVIN_API_DIR / "static"

CHANGELOG_HTML = "changelog.html"
README_HTML = "readme.html"

# A throwaway Sphinx project with only the two extensions that provide the roles
# used in changelog.rst -- no theme extras, intersphinx, or bibtex. It is fast
# and needs no network, so it runs unchanged in CI and in the Docker image build.
CONF_PY = """\
project = "UCS@school Kelvin REST API"
extensions = ["univention_sphinx_extension", "sphinxcontrib.spelling"]
html_theme = "basic"
exclude_patterns = ["_build"]
"""

INDEX_RST = """\
:orphan:

.. toctree::

   changelog
   readme
"""

# Compact, self-contained styling for the API-served pages, so each renders as a
# tidy standalone document without referencing any external asset.
PAGE_CSS = """\
:root { color-scheme: light dark; }
body {
    font-family: system-ui, -apple-system, "Segoe UI", Roboto, sans-serif;
    line-height: 1.6;
    max-width: 50rem;
    margin: 2rem auto;
    padding: 0 1.25rem;
    color: #1a1a1a;
    background: #ffffff;
}
h1, h2, h3, h4 { line-height: 1.25; margin-top: 2rem; }
h1 { font-size: 1.9rem; }
a { color: #0b5ed7; text-decoration: none; }
a:hover { text-decoration: underline; }
code, pre {
    font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
    background: #f4f4f4;
    border-radius: 4px;
}
code { padding: 0.1em 0.3em; font-size: 0.9em; }
pre { padding: 0.8rem 1rem; overflow-x: auto; }
pre code { background: none; padding: 0; }
ul, ol { padding-left: 1.4rem; }
img { max-width: 100%; }
.headerlink { visibility: hidden; margin-left: 0.3rem; text-decoration: none; }
h1:hover .headerlink, h2:hover .headerlink,
h3:hover .headerlink, h4:hover .headerlink { visibility: visible; }
@media (prefers-color-scheme: dark) {
    body { color: #e6e6e6; background: #1a1a1a; }
    a { color: #6ea8fe; }
    code, pre { background: #2b2b2b; }
}
"""

PAGE_TEMPLATE = """\
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{title}</title>
<style>
{css}</style>
</head>
<body>
{body}</body>
</html>
"""


def _build_sphinx(srcdir: Path, outdir: Path) -> None:
    (srcdir / "conf.py").write_text(CONF_PY)
    (srcdir / "index.rst").write_text(INDEX_RST)
    for rst in ("changelog.rst", "readme.rst"):
        (srcdir / rst).write_text((KELVIN_API_DIR / rst).read_text())
    subprocess.run(
        ["sphinx-build", "--builder", "html", str(srcdir), str(outdir)],
        check=True,
    )


def _extract(page: Path, xpath: str) -> str:
    """Return the HTML of the element matched by ``xpath`` in a built page.

    Raise if docutils rendered any error node -- an unknown role or malformed
    markup surfaces as a ``system-message``/``problematic`` node, so this fails
    the build loudly instead of shipping a broken page.
    """
    tree = html.fromstring(page.read_text())
    broken = tree.xpath("//*[contains(@class, 'system-message')] | //*[contains(@class, 'problematic')]")
    if broken:
        raise ValueError(f"{page.name} contains {len(broken)} docutils error node(s)")
    matches = tree.xpath(xpath)
    if not matches:
        raise ValueError(f"no element matched {xpath!r} in {page.name}")
    return html.tostring(matches[0], encoding="unicode", pretty_print=True)


def _write_page(destination: Path, title: str, body: str) -> None:
    destination.write_text(PAGE_TEMPLATE.format(title=title, css=PAGE_CSS, body=body))


def main() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        srcdir = Path(tmp) / "src"
        outdir = Path(tmp) / "out"
        srcdir.mkdir()
        _build_sphinx(srcdir, outdir)

        changelog = _extract(outdir / CHANGELOG_HTML, "//*[@id='changelog']")
        readme = _extract(outdir / README_HTML, "//div[@class='body']/section")

    # App Center changelog: bare content fragment (unchanged output contract).
    (REPO_ROOT / CHANGELOG_HTML).write_text(f"<div>\n{changelog}\n</div>")

    # API-served pages: self-contained, styled, standalone documents.
    STATIC_DIR.mkdir(parents=True, exist_ok=True)
    _write_page(STATIC_DIR / CHANGELOG_HTML, "Changelog", changelog)
    _write_page(STATIC_DIR / README_HTML, "UCS@school Kelvin REST API", readme)


if __name__ == "__main__":
    main()
