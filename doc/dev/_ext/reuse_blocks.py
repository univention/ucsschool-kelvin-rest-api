# SPDX-FileCopyrightText: 2026 Univention GmbH
#
# SPDX-License-Identifier: AGPL-3.0-only

from __future__ import annotations

from typing import Any

from docutils import nodes
from docutils.parsers.rst import Directive
from sphinx.util.logging import getLogger

logger = getLogger(__name__)


class DefineBlockDirective(Directive):
    """Define a named content block that can be reused elsewhere.

    The directive renders its content in-place and also registers the parsed
    nodes under the given name.

    Usage::

        .. define-block:: some_name

           Some *rich* content.
    """

    required_arguments = 1
    optional_arguments = 0
    has_content = True

    def run(self) -> list[nodes.Node]:
        name = self.arguments[0].strip()
        container = nodes.container()
        container["reuse_block_def"] = name
        self.state.nested_parse(self.content, self.content_offset, container)
        return [container]


class ReuseBlockDirective(Directive):
    """Insert a previously defined named block."""

    required_arguments = 1
    optional_arguments = 0
    has_content = False

    def run(self) -> list[nodes.Node]:
        name = self.arguments[0].strip()
        placeholder = nodes.container()
        placeholder["reuse_block_use"] = name
        return [placeholder]


def doctree_read(app: Any, doctree: nodes.document) -> None:
    docname = app.env.docname
    definitions: dict[str, list[nodes.Node]] = {}

    for node in doctree.traverse(nodes.container):
        name = node.get("reuse_block_def")
        if not name:
            continue
        if name in definitions:
            logger.warning("Duplicate define-block name '%s' in '%s'.", name, docname)
            continue
        definitions[name] = [child.deepcopy() for child in node.children]

    for node in list(doctree.traverse(nodes.container)):
        name = node.get("reuse_block_use")
        if not name:
            continue
        if name not in definitions:
            logger.warning("Unknown reuse-block name '%s' in '%s'.", name, docname)
            continue
        node.replace_self([child.deepcopy() for child in definitions[name]])


def setup(app: Any) -> dict[str, Any]:
    app.add_directive("define-block", DefineBlockDirective)
    app.add_directive("reuse-block", ReuseBlockDirective)
    app.connect("doctree-read", doctree_read)

    return {
        "version": "1.0",
        "parallel_read_safe": True,
        "parallel_write_safe": True,
    }
