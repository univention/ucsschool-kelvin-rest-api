# Copyright 2026 Univention GmbH
#
# http://www.univention.de/
#
# All rights reserved.
#
# The source code of this program is made available
# under the terms of the GNU AGPL V3.

from ucsschool_objects import Filter, Operator, make_wildcard_filter


def str_filter(field: str, value: str, *, case_insensitive: bool = False) -> Filter:
    """Create a string filter with wildcard support and proper escaping."""
    if case_insensitive:
        return make_wildcard_filter(field, value, case_insensitive=True)
    if "*" in value:
        return make_wildcard_filter(field, value)
    return Filter(field=field, op=Operator.EQ, value=value)
