#!/usr/share/ucs-test/runner pytest-3 -s -l -v
## -*- coding: utf-8 -*-
## desc: UCR variables copied by the join script match on host and in the Kelvin container
## tags: [ucs_school_kelvin]
## exposure: safe
## packages: []
## bugs: []

# SPDX-FileCopyrightText: 2026 Univention GmbH
# SPDX-License-Identifier: AGPL-3.0-only

import subprocess

import pytest

from univention.config_registry import ucr

APP_ID = "ucsschool-kelvin-rest-api"

# keep in sync with appcenter/includes/inst
SYNCED_UCR_VARIABLES: tuple[str, ...] = (
    "ldap/server/name",
    "ldap/server/port",
    "dhcpd/ldap/base",
    "ucsschool/import/set/netlogon/script/path",
    "ucsschool/import/set/homedrive",
    "ucsschool/import/set/sambahome",
    "ucsschool/singlemaster",
    "ucsschool/import/set/serverprofile/path",
    "ucsschool/validation/logging/backupcount",
    "ucsschool/validation/logging/enabled",
    "ucsschool/validation/username/windows-check",
    "ucsschool/import/generate/share/marktplatz",
    "ucsschool/import/generate/policy/dhcp/searchbase",
    "ucsschool/import/generate/policy/dhcp/dns/set_per_ou",
    "ucsschool/import/generate/import/group",
    "ucsschool/ldap/default/container/exam",
    "groups/default/domainusers",
    "ucsschool/ldap/default/dcs",
    "ucsschool/import/generate/policy/dhcp/dns/clearou",
)


@pytest.fixture(scope="module")
def container_ucr() -> dict[str, str]:
    """All UCR variables set inside the Kelvin Docker container."""
    proc = subprocess.run(  # nosec
        ["univention-app", "shell", APP_ID, "ucr", "dump"],
        check=True,
        stdout=subprocess.PIPE,
        universal_newlines=True,
    )
    result: dict[str, str] = {}
    for line in proc.stdout.splitlines():
        key, sep, value = line.partition(": ")
        if sep:
            result[key] = value
    assert result, "'ucr dump' in the container returned no UCR variables."
    return result


@pytest.mark.parametrize("ucrv", SYNCED_UCR_VARIABLES)
def test_ucr_variable_synced_to_container(ucrv: str, container_ucr: dict[str, str]) -> None:
    """The join script copies the host's UCR variables into the container.

    A variable that is unset on the host is passed to the container as
    ``name=``, which stores an empty value there. Both are normalized to the
    empty string, so "unset on the host" and "empty in the container" compare
    as equal.
    """
    host_value: str = ucr.get(ucrv) or ""
    assert container_ucr.get(ucrv, "") == host_value, (
        f"UCR variable {ucrv!r} differs between host and container. Was the join script"
        f" of the app {APP_ID!r} run successfully?"
    )
