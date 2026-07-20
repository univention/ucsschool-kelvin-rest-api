# SPDX-FileCopyrightText: 2026 Univention GmbH
# SPDX-License-Identifier: AGPL-3.0-only
"""
Test stub for ``univention.appcenter.app``.

The real module ships with the ``univention-appcenter`` package and is only
available on a UCS docker host, not in the CI/dev environment where the bats
tests run. The preinst's provisioning-version check reuses this module's
``LooseVersion`` comparator, so the tests put this stub on ``PYTHONPATH``.

``LooseVersion`` below is a faithful copy of the real implementation
(management/univention-appcenter/python/appcenter/app.py in the ucs repo) so
that the tests exercise the same numeric-vs-lexical ordering the preinst relies
on (e.g. "2.10" >= "2.2"). Keep it in sync if the upstream comparator changes.
"""

from __future__ import annotations

import re
from itertools import zip_longest


class LooseVersion:  # noqa: PLW1641
    RE_COMPONENT_SEPARATOR = re.compile(r"(\d+ | [a-z]+ | [A-Z]+)", re.VERBOSE)

    def __init__(self, version: LooseVersion | str):
        self._version = str(version)
        self._components = []
        self._parse()

    def __str__(self) -> str:
        return self._version

    def __repr__(self) -> str:
        return f"LooseVersion('{self}')"

    def __eq__(self, other: LooseVersion | str) -> bool:
        return (
            self._compare(LooseVersion(other)) == 0
            if isinstance(other, LooseVersion | str)
            else NotImplemented
        )

    def __lt__(self, other: LooseVersion | str) -> bool:
        return (
            self._compare(LooseVersion(other)) < 0
            if isinstance(other, LooseVersion | str)
            else NotImplemented
        )

    def __le__(self, other: LooseVersion | str) -> bool:
        return (
            self._compare(LooseVersion(other)) <= 0
            if isinstance(other, LooseVersion | str)
            else NotImplemented
        )

    def __gt__(self, other: LooseVersion | str) -> bool:
        return (
            self._compare(LooseVersion(other)) > 0
            if isinstance(other, LooseVersion | str)
            else NotImplemented
        )

    def __ge__(self, other: LooseVersion | str) -> bool:
        return (
            self._compare(LooseVersion(other)) >= 0
            if isinstance(other, LooseVersion | str)
            else NotImplemented
        )

    def _parse(self) -> None:
        self._components = [
            self._try_int(obj)
            for obj in self.RE_COMPONENT_SEPARATOR.split(self._version)
            if obj.isalnum()
        ]

    def _compare(self, other: LooseVersion) -> int:
        for i, j in zip_longest(self._components, other._components):
            if not isinstance(i, type(j)) and i is not None and j is not None:
                i = str(i)
                j = str(j)
            if i == j:
                continue
            elif i is None:
                return -1
            elif j is None:
                return 1
            elif i < j:
                return -1
            elif i > j:
                return 1
        return 0

    def _try_int(self, string: str) -> int | str:
        try:
            return int(string)
        except ValueError:
            return string
