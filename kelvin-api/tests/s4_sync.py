# SPDX-FileCopyrightText: 2026 Univention GmbH
# SPDX-License-Identifier: AGPL-3.0-only

"""
Waiting for the Samba4 (S4) connector.

The S4 connector replicates a user from OpenLDAP to Samba, and from there it may write changes back to
OpenLDAP. Tests that assert the state after that round trip wait for the change to arrive in Samba and
then for one more S4 poll cycle. When no S4 connector replicates the user (e.g. in a multi-server
domain for an OU without a real school server), there is nothing to wait for.
"""

import asyncio
import logging
import ssl
import time
from collections.abc import Callable

from ldap3 import SUBTREE, Connection, Server, Tls
from uldap3 import escape_filter_chars

from ucsschool.lib.models.utils import env_or_ucr, uldap_admin_read_primary

logger = logging.getLogger(__name__)

S4_POLL_INTERVAL = 5
ADMIN_PASSWORD = "univention"
CA_CERTS_FILE = "/etc/ssl/certs/ca-certificates.crt"
UF_ACCOUNTDISABLE = 0x2
SCHOOL_SERVER_CONTAINER = "cn=dc,cn=server,cn=computers,"
SambaEntry = dict[str, list[bytes]]


def s4_connectors() -> dict[str, str | None]:
    """
    FQDNs of the hosts running an S4 connector, mapped to the DN suffix of the school OU they
    replicate, or to None for a connector on the Primary/Backup, which replicates everything.
    """
    ldap_base = env_or_ucr("ldap/base").lower()
    hosts = uldap_admin_read_primary().search(
        "(&(objectClass=univentionHost)(univentionService=S4 Connector))",
        attributes=["cn", "associatedDomain"],
    )
    result: dict[str, str | None] = {}
    for host in hosts:
        fqdn = f"{host['cn'].value}.{host['associatedDomain'].value}"
        container = host.entry_dn.split(",", 1)[1].lower()
        if container == f"cn=dc,cn=computers,{ldap_base}":
            result[fqdn] = None
        elif container.startswith(SCHOOL_SERVER_CONTAINER):
            result[fqdn] = container[len(SCHOOL_SERVER_CONTAINER) :]
    return result


def responsible_s4_connector(dn: str) -> str | None:
    """FQDN of the host whose S4 connector replicates `dn`, or None."""
    for fqdn, school_suffix in s4_connectors().items():
        if school_suffix is None or dn.lower().endswith(f",{school_suffix}"):
            return fqdn
    return None


def get_samba_user(host: str, username: str) -> SambaEntry | None:
    server = Server(
        host,
        port=636,
        use_ssl=True,
        tls=Tls(ca_certs_file=CA_CERTS_FILE, validate=ssl.CERT_REQUIRED),
    )
    with Connection(
        server,
        user=f"Administrator@{env_or_ucr('domainname')}",
        password=ADMIN_PASSWORD,
        auto_bind=True,
        auto_referrals=False,
    ) as conn:
        conn.search(
            env_or_ucr("ldap/base"),
            f"(sAMAccountName={escape_filter_chars(username)})",
            SUBTREE,
            attributes=["distinguishedName", "userAccountControl", "accountExpires"],
        )
        entries = [entry for entry in conn.response or [] if entry.get("type") == "searchResEntry"]
    return entries[0]["raw_attributes"] if entries else None


def get_ldap_user_attr(username: str, attr: str) -> str:
    results = uldap_admin_read_primary().search(
        f"(uid={escape_filter_chars(username)})", attributes=[attr]
    )
    assert len(results) == 1
    return str(results[0][attr].value)


def samba_disabled(entry: SambaEntry) -> bool:
    return bool(int(entry["userAccountControl"][0]) & UF_ACCOUNTDISABLE)


def samba_dn(entry: SambaEntry) -> str:
    return entry["distinguishedName"][0].decode()


async def wait_for_s4_sync(
    dn: str,
    username: str,
    check: Callable[[SambaEntry], bool] = lambda entry: True,
    timeout: float = 60,
) -> SambaEntry | None:
    """
    Wait until the Samba entry of `username` satisfies `check`, then for one more S4 poll cycle.

    Returns the Samba entry, or None if no S4 connector replicates `dn`.
    Fails if the change doesn't arrive in Samba within `timeout` seconds.
    """
    host = responsible_s4_connector(dn)
    if not host:
        logger.debug("No S4 connector replicates %r, not waiting.", dn)
        return None
    t0 = time.monotonic()
    entry = None
    while time.monotonic() - t0 < timeout:
        entry = get_samba_user(host, username)
        if entry and check(entry):
            break
        await asyncio.sleep(1)
    else:
        raise AssertionError(
            f"S4 connector on {host!r} did not replicate {dn!r} within {timeout}s: {entry!r}"
        )
    logger.debug("Samba on %r in sync for %r after %.1fs.", host, dn, time.monotonic() - t0)
    await asyncio.sleep(S4_POLL_INTERVAL + 1)
    return entry
