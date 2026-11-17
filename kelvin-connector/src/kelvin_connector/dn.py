# SPDX-FileCopyrightText: 2026 Univention GmbH
# SPDX-License-Identifier: AGPL-3.0-only

from typing import cast

import ldap  # pyright: ignore[reportMissingTypeStubs]
import ldap.dn  # pyright: ignore[reportMissingTypeStubs]


def rdns(dn: str) -> list[tuple[str, str]]:
    """The (attribute, value) of each RDN, leaf first (the first one of a multi-valued RDN).

    Raises `ValueError` for a malformed DN.
    """
    try:
        parsed = cast(
            "list[list[tuple[str, str, int]]]",
            ldap.dn.str2dn(dn),  # pyright: ignore[reportUnknownMemberType]
        )
    except ldap.DECODING_ERROR:  # pyright: ignore[reportAttributeAccessIssue, reportUnknownMemberType]
        raise ValueError(f"Malformed DN syntax: {dn!r}") from None
    return [(rdn[0][0], rdn[0][1]) for rdn in parsed]
