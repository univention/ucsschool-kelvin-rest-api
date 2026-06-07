# Copyright 2026 Univention GmbH
#
# http://www.univention.de/
#
# All rights reserved.
#
# The source code of this program is made available
# under the terms of the GNU AGPL V3.

from ...config import UDM_MAPPING_CONFIG


def mapped_udm_properties(stored: dict[str, object], entity: str) -> dict[str, object]:
    """The configured subset of an object's cached UDM properties.

    The cache stores the full UDM properties of an object; the API serves
    only the configured mapped properties. Properties the cache has not
    (yet) seen default to None — mirroring v1, which returns every
    configured property.
    """
    configured: list[str] = getattr(UDM_MAPPING_CONFIG, entity)
    return {prop: stored.get(prop) for prop in configured}
