# -*- coding: utf-8 -*-
#
# Copyright 2026 Univention GmbH
#
# http://www.univention.de/
#
# All rights reserved.
#
# The source code of this program is made available
# under the terms of the GNU Affero General Public License version 3
# (GNU AGPL V3) as published by the Free Software Foundation.
#
# Binary versions of this program provided by Univention to you as
# well as other copyrighted, protected or trademarked materials like
# Logos, graphics, fonts, specific documentations and configurations,
# cryptographic keys etc. are subject to a license agreement between
# you and Univention and not subject to the GNU AGPL V3.
#
# In the case you use this program under the terms of the GNU AGPL V3,
# the program is provided in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
# GNU Affero General Public License for more details.
#
# You should have received a copy of the GNU Affero General Public
# License with the Debian GNU/Linux or Univention distribution in file
# /usr/share/common-licenses/AGPL-3; if not, see
# <http://www.gnu.org/licenses/>.

"""
Wait until the v2 connector has replicated LDAP into the Kelvin v2 database.

The v2 API serves from a database that the connector fills asynchronously by
consuming the provisioning queue. With a large, pre-filled LDAP that database is
empty at first and catches up over a long time (the provisioning service even
pre-fills its own queue first, which can take hours) — and there is no
queue-depth endpoint to poll. This module instead compares object counts:

  * expected: ucsschool user objects in LDAP (the source of truth)
  * actual:   user rows in the v2 database (the connector's output)

and blocks until they match (or a timeout is hit). It is meant to run INSIDE the
Kelvin container, where it can reuse Kelvin's own LDAP and database access — for
example during golden-image creation, so the finished image already has a full
v2 database and no waiting is needed at test time:

    univention-app shell ucsschool-kelvin-rest-api \\
        python3 -m ucsschool.kelvin.wait_for_db_full

Exit code 0 means the v2 database is full; non-zero means it did not catch up
within the timeout.
"""

import argparse
import asyncio
import logging
import os
import sys
import time

from sqlalchemy import func, select
from ucsschool_objects.core.adapters.sqlalchemy.session import (
    build_engine,
    build_session_factory,
    build_settings,
)
from ucsschool_objects.database_models import User

from ucsschool.lib.models.utils import env_or_ucr, uldap_admin_read_local

# objectClasses that the connector turns into a v2 "user" row.
USER_OBJECT_CLASSES = (
    "ucsschoolStudent",
    "ucsschoolTeacher",
    "ucsschoolStaff",
    "ucsschoolLegalGuardian",
    "ucsschoolAdministrator",
)

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s", stream=sys.stdout
)
logger = logging.getLogger("wait_for_db_full")


def expected_user_count() -> int:
    """Count ucsschool user objects in LDAP, per school OU to bound memory."""
    ldap_base = env_or_ucr("ldap/base")
    uldap = uldap_admin_read_local()
    schools = uldap.search(
        search_filter="(&(ou=school*)(ucsschoolRole=school:school*))",
        attributes=["ou"],
        search_base=ldap_base,
    )
    oc_filter = "".join(f"(objectClass={oc})" for oc in USER_OBJECT_CLASSES)
    total = 0
    for entry in schools:
        ou = entry["ou"].value
        found = uldap.search(
            search_filter=f"(|{oc_filter})",
            attributes=["uid"],
            search_base=f"ou={ou},{ldap_base}",
        )
        total += len(found)
    return total


async def _actual_user_count() -> int:
    engine = build_engine(build_settings())
    try:
        session_factory = build_session_factory(engine)
        async with session_factory() as session:
            result = await session.execute(select(func.count()).select_from(User))
            return int(result.scalar_one())
    finally:
        await engine.dispose()


def actual_user_count() -> int:
    """Count user rows in the v2 database (synchronous wrapper)."""
    return asyncio.run(_actual_user_count())


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--timeout",
        type=float,
        default=float(os.environ.get("UCS_ENV_DB_FILL_TIMEOUT", "43200")),
        help=(
            "Maximum seconds to wait for the v2 database to catch up (default: 43200 = 12h). "
            "Must be generous: the provisioning service first pre-fills its own queue, which "
            "can take HOURS, during which the connector receives nothing and the count stays 0."
        ),
    )
    parser.add_argument(
        "--interval",
        type=float,
        default=float(os.environ.get("UCS_ENV_DB_FILL_INTERVAL", "30")),
        help="Seconds between polls (default: 30).",
    )
    parser.add_argument(
        "--min-ratio",
        type=float,
        default=float(os.environ.get("UCS_ENV_DB_FILL_MIN_RATIO", "1.0")),
        help="Fraction of the expected user count required to pass (default: 1.0).",
    )
    args = parser.parse_args()

    logger.info("Counting expected ucsschool users in LDAP...")
    expected = expected_user_count()
    if expected == 0:
        logger.warning("LDAP reports 0 ucsschool users — nothing to wait for.")
        return 0
    target = max(1, int(expected * args.min_ratio))
    logger.info(
        "LDAP has %d users. Waiting for the v2 database to reach %d (timeout=%ds, interval=%ds).",
        expected,
        target,
        int(args.timeout),
        int(args.interval),
    )

    start = time.monotonic()
    deadline = start + args.timeout
    while True:
        try:
            actual = actual_user_count()
        except Exception as exc:  # noqa: BLE001 - DB may not be ready yet; keep polling
            logger.warning("Could not read the v2 user count (%s) — will retry.", exc)
            actual = -1

        elapsed = int(time.monotonic() - start)
        if actual >= 0:
            logger.info(
                "Progress after %ds: v2 has %d/%d users (%.1f%%).",
                elapsed,
                actual,
                expected,
                100.0 * actual / expected,
            )
            if actual == 0:
                # Normal for a long while: provisioning is still pre-filling its own
                # queue, so the connector has not received anything yet.
                logger.info(
                    "  v2 database still empty — provisioning is likely still pre-filling its "
                    "own queue; this can take hours (timeout in %ds).",
                    int(deadline - time.monotonic()),
                )
            if actual >= target:
                logger.info("v2 database is full — connector has caught up with LDAP.")
                return 0

        if time.monotonic() >= deadline:
            logger.error(
                "Timed out after %ds: v2 has %d of %d expected users. "
                "The connector did not finish replication.",
                int(args.timeout),
                actual,
                expected,
            )
            return 1

        time.sleep(args.interval)


if __name__ == "__main__":
    sys.exit(main())
