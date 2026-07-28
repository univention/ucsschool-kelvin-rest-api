# SPDX-FileCopyrightText: 2020-2026 Univention GmbH
# SPDX-License-Identifier: AGPL-3.0-only

import asyncio
import logging
from functools import lru_cache
from typing import Any, Dict, Iterable, Union

import univention.admin.uldap

logger = logging.getLogger(__name__)


@lru_cache(maxsize=1)
def s4_connector_in_domain() -> bool:
    """Whether any system in the domain runs the s4 connector.

    Cached, so the LDAP search runs once per test session. Without an s4 connector
    there is no round trip to wait for, and `wait_for_s4()` would block for its full
    timeout on every object it is handed.
    """
    lo = univention.admin.uldap.getAdminConnection()[0]
    found = bool(lo.searchDn(filter="(univentionService=S4 Connector)"))
    if not found:
        logger.info("No s4 connector in the domain, not waiting for s4 round trips.")
    return found


def ldap_modify_timestamps(dns: Iterable[str]) -> Dict[str, Any]:
    """`modifyTimestamp` of each DN, to be passed to `wait_for_s4()` as a baseline."""
    lo = univention.admin.uldap.getAdminConnection()[0]
    return {dn: lo.get(dn, attr=["modifyTimestamp"]) for dn in dns}


async def wait_for_s4(
    dns: Union[str, Iterable[str], Dict[str, Any]],
    max_time: int = 15,
) -> None:
    """Wait until s4 has written its changes back to LDAP.

    s4 runs every 5 seconds and first modifies the samba entry and then the LDAP entry
    again. Modifying an object before that round trip finished lets s4 overwrite the
    modification with the data from the create event, so everything that creates or
    modifies an object has to wait for it - especially if changes happen to "disabled"
    and "expiration_date".

    Waits until the `modifyTimestamp` of every DN changed, or `max_time` seconds passed.
    `dns` is a DN, a list of DNs, or baselines from `ldap_modify_timestamps()`. Pass
    baselines when the objects were touched a while ago; otherwise the timestamps are
    read now, and a round trip that already finished is indistinguishable from one that
    never happens.
    """
    if not s4_connector_in_domain():
        return
    if isinstance(dns, dict):
        pending = dict(dns)
    else:
        pending = ldap_modify_timestamps([dns] if isinstance(dns, str) else dns)
    lo = univention.admin.uldap.getAdminConnection()[0]
    for _ in range(max_time):
        await asyncio.sleep(1)
        for dn, last_mod in list(pending.items()):
            if lo.get(dn, attr=["modifyTimestamp"]) != last_mod:
                del pending[dn]
        if not pending:
            return
    logger.warning("s4 did not write back to %r within %d seconds.", sorted(pending), max_time)
