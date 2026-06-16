#!/usr/bin/env python3
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
Count-based replication fence for the Kelvin v2 connector.

The performance tests run against a large, pre-filled LDAP. The Kelvin v2 API
serves from a separate database that the connector populates by consuming the
provisioning queue. Before load-testing v2 we must wait until that database has
caught up with LDAP — there is no queue-depth endpoint to poll, so we compare
object counts instead:

  * expected counts are read directly from LDAP (the source of truth)
  * actual counts are read from the Kelvin v2 REST API (the connector's output)

The fence passes once every school's v2 user count (and the school count itself)
has reached the LDAP count, i.e. the connector has drained its prefill backlog.
It is intentionally dependency-light: it uses the host's system Python (for
``univention.admin.uldap``) and ``requests`` only — NOT the Locust virtualenv.

Run it from the performance-test CI config (``branch_performance_tests.cfg``)
after the Kelvin app has been (re)started, before ``ucs-test`` launches Locust:

    python3 /usr/share/ucs-test/94_ucsschool-kelvin-performance/wait_for_db_full.py

Exit code 0 means the database is full; non-zero means it did not catch up
within the timeout (the test run should then be aborted).
"""

import argparse
import logging
import os
import sys
import time
from typing import Dict, List

import requests

from univention.admin.uldap import getAdminConnection
from univention.config_registry import ConfigRegistry

# Reuse the environment variable names the Locust settings/auth already use, so
# the CI config only has to set the host/credentials once.
KELVIN_HOST_ENV = "UCS_ENV_KELVIN_HOST"
KELVIN_USERNAME_ENV = "UCS_ENV_TEST_KELVIN_USERNAME"
KELVIN_PASSWORD_ENV = "UCS_ENV_TEST_KELVIN_PASSWORD"  # nosec

# The connector always fills the v2 database; v1 reads LDAP directly and needs
# no fence. Kept configurable only for symmetry / future API versions.
API_VERSION = os.environ.get("UCS_ENV_KELVIN_DB_API_VERSION", "v2")

SSL_CERT = "/etc/ssl/certs/ca-certificates.crt"
AUTH_TOKEN_URL = "/ucsschool/kelvin/token"  # nosec

# ucsschoolRole values that correspond to a "user" object, mirroring the role
# set the performance test data fixture (conftest.create_test_data) builds.
USER_ROLES = ("student", "teacher", "staff", "legal_guardian")

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s", stream=sys.stdout
)
logger = logging.getLogger("wait_for_db_full")


def kelvin_host() -> str:
    host = os.environ.get(KELVIN_HOST_ENV)
    if host:
        return host
    ucr = ConfigRegistry()
    ucr.load()
    return ucr.get("ldap/master") or "primary.ucsschool.test"


def _verify():
    return SSL_CERT if os.path.exists(SSL_CERT) else True


def expected_counts_from_ldap() -> Dict[str, int]:
    """Return {school_name: expected_member_count} read straight from LDAP.

    Counts are by *school membership* (``ucsschoolRole=<role>:school:<school>``),
    matching what the Kelvin v2 ``/users/?school=`` filter returns, so the two
    sides are directly comparable even for users that belong to several schools.
    """
    lo, _ = getAdminConnection()
    schools = {
        attrs["ou"][0].decode()
        for _, attrs in lo.search("(&(ou=school*)(ucsschoolRole=school:school*))", attr=("ou",))
    }
    role_filter = "".join(f"(ucsschoolRole={role}:school:*)" for role in USER_ROLES)
    # One scan over all user objects; tally distinct members per school in Python.
    members: Dict[str, set] = {school: set() for school in schools}
    for dn, attrs in lo.search(f"(|{role_filter})", attr=("ucsschoolRole",)):
        for raw_role in attrs.get("ucsschoolRole", []):
            role, _, scope = raw_role.decode().partition(":school:")
            if role in USER_ROLES and scope in members:
                members[scope].add(dn)
    return {school: len(dns) for school, dns in members.items()}


class KelvinClient:
    def __init__(self, host: str, username: str, password: str):
        self.base_url = f"https://{host}/ucsschool/kelvin/{API_VERSION}"
        self._token_url = f"https://{host}{AUTH_TOKEN_URL}"
        self._username = username
        self._password = password
        self._token = ""

    def _fetch_token(self) -> None:
        resp = requests.post(
            self._token_url,
            data={"username": self._username, "password": self._password},
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            verify=_verify(),
            timeout=30,
        )
        resp.raise_for_status()
        body = resp.json()
        self._token = f"{body['token_type']} {body['access_token']}"

    def _get(self, path: str, params: Dict[str, str] = None) -> list:
        if not self._token:
            self._fetch_token()
        for _ in range(2):  # one retry to refresh an expired/invalid token
            resp = requests.get(
                f"{self.base_url}{path}",
                params=params or {},
                headers={"Accept": "application/json", "Authorization": self._token},
                verify=_verify(),
                timeout=300,
            )
            if resp.status_code == 401:
                self._fetch_token()
                continue
            resp.raise_for_status()
            return resp.json()
        resp.raise_for_status()
        return resp.json()

    def school_count(self) -> int:
        return len(self._get("/schools/"))

    def user_count(self, school: str) -> int:
        return len(self._get("/users/", params={"school": school}))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--timeout",
        type=float,
        default=float(os.environ.get("UCS_ENV_DB_FILL_TIMEOUT", "21600")),
        help=(
            "Maximum seconds to wait for the v2 database to catch up (default: 21600 = 6h). "
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
        help="Fraction of expected objects required to pass, per school (default: 1.0).",
    )
    args = parser.parse_args()

    # v1 serves straight from LDAP, so a v1-only run needs no fence. The default
    # (unset) matches the test suite default of "both", which does need it.
    selection = os.environ.get("UCS_ENV_KELVIN_API_VERSION", "both")
    if selection == "v1":
        logger.info("API version selection is 'v1' only — v2 database fence not needed, skipping.")
        return 0

    host = kelvin_host()
    username = os.environ.get(KELVIN_USERNAME_ENV, "Administrator")
    password = os.environ.get(KELVIN_PASSWORD_ENV, "univention")

    logger.info("Reading expected object counts from LDAP...")
    expected = expected_counts_from_ldap()
    expected_total = sum(expected.values())
    logger.info(
        "LDAP has %d schools and %d users. Waiting for the v2 database (%s) to catch up "
        "(timeout=%ds, interval=%ds, min-ratio=%.2f).",
        len(expected),
        expected_total,
        host,
        int(args.timeout),
        int(args.interval),
        args.min_ratio,
    )
    if expected_total == 0:
        logger.warning("LDAP reports 0 users — nothing to wait for.")
        return 0

    client = KelvinClient(host, username, password)
    # Schools that have already reached their target — skip re-querying them.
    done: set = set()
    have_counts: Dict[str, int] = {school: 0 for school in expected}
    start = time.monotonic()
    deadline = start + args.timeout

    while True:
        try:
            actual_schools = client.school_count()
            for school, want in expected.items():
                if school in done:
                    continue
                have_counts[school] = client.user_count(school)
                if have_counts[school] >= max(1, int(want * args.min_ratio)) or want == 0:
                    done.add(school)
        except requests.RequestException as exc:
            logger.warning("Kelvin v2 query failed (%s) — will retry.", exc)
            actual_schools = -1

        pending: List[str] = [s for s in expected if s not in done]
        total_have = sum(have_counts.values())
        elapsed = int(time.monotonic() - start)
        logger.info(
            "Progress after %ds: %d/%d users, %d/%d schools filled "
            "(v2 reports %s schools); %d schools still catching up.",
            elapsed,
            total_have,
            expected_total,
            len(expected) - len(pending),
            len(expected),
            actual_schools if actual_schools >= 0 else "?",
            len(pending),
        )
        if total_have == 0:
            # Expected for a long while: the provisioning service pre-fills its own
            # queue (NATS) before delivering anything to the connector, which can
            # take hours. A flat 0 here is normal, not a hang.
            logger.info(
                "  v2 database still empty — provisioning is likely still pre-filling its "
                "own queue; the connector has not started receiving events yet. This can "
                "take hours; waiting (timeout in %ds).",
                int(deadline - time.monotonic()),
            )

        if not pending and actual_schools >= len(expected):
            logger.info("v2 database is full — connector has caught up with LDAP.")
            return 0

        if time.monotonic() >= deadline:
            sample = ", ".join(sorted(pending)[:10])
            logger.error(
                "Timed out after %ds: %d/%d schools still incomplete (e.g. %s). "
                "The v2 connector did not finish replication.",
                int(args.timeout),
                len(pending),
                len(expected),
                sample or "-",
            )
            return 1

        time.sleep(args.interval)


if __name__ == "__main__":
    sys.exit(main())
