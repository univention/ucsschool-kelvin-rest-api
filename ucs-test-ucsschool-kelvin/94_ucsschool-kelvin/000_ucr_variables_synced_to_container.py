#!/usr/share/ucs-test/runner pytest-3 -s -l -v
## -*- coding: utf-8 -*-
## desc: Kelvin-relevant host UCR variables are synced into the Kelvin container on every start
## tags: [ucs_school_kelvin]
## exposure: dangerous
## packages: []
## bugs: []

# SPDX-FileCopyrightText: 2026 Univention GmbH
# SPDX-License-Identifier: AGPL-3.0-only

import subprocess
import time
import uuid
from collections.abc import Iterator

import pytest

from univention.config_registry import handler_set, handler_unset, ucr

APP_ID = "ucsschool-kelvin-rest-api"
PROTECTED_UCR_VARIABLES = ("ldap/hostdn", "server/role", "hostname")
HEALTH_CHECK = "import urllib.request; urllib.request.urlopen('http://localhost:8911/health')"


def app_shell(*args: str, check: bool = True) -> subprocess.CompletedProcess[str]:
    return subprocess.run(  # nosec
        ["univention-app", "shell", APP_ID, *args],
        check=check,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        universal_newlines=True,
    )


def container_ucr() -> dict[str, str]:
    result: dict[str, str] = {}
    for line in app_shell("ucr", "dump").stdout.splitlines():
        key, sep, value = line.partition(": ")
        if sep:
            result[key] = value
    assert result, "'ucr dump' in the container returned no UCR variables."
    return result


def synced_keys() -> list[str]:
    keys = app_shell("kelvin-sync-host-ucr", "--list").stdout.split()
    assert "ucsschool/singlemaster" in keys
    return keys


def restart_app() -> None:
    subprocess.run(["univention-app", "restart", APP_ID], check=True)  # nosec
    deadline = time.monotonic() + 300
    while app_shell("python3", "-c", HEALTH_CHECK, check=False).returncode != 0:
        assert time.monotonic() < deadline, "Kelvin did not become healthy after the restart."
        time.sleep(2)


def assert_synced() -> None:
    ucr.load()
    container = container_ucr()
    for key in synced_keys():
        assert container.get(key) == ucr.get(key), (
            f"UCR variable {key!r} differs between host and container"
        )


@pytest.fixture
def host_ucr_change() -> Iterator[tuple[str, str]]:
    key = f"ucsschool/import/ucs-test/{uuid.uuid4().hex}"
    value = uuid.uuid4().hex
    handler_set([f"{key}={value}"])
    try:
        yield key, value
    finally:
        handler_unset([key])
        if key in container_ucr():
            restart_app()


def test_list_excludes_protected_variables() -> None:
    keys = synced_keys()
    for key in PROTECTED_UCR_VARIABLES:
        assert key not in keys
    assert not [key for key in keys if key.startswith(("ucsschool/kelvin/", "ldap/server/"))]


def test_ucr_variables_synced_to_container() -> None:
    assert_synced()


def test_host_change_synced_on_restart(host_ucr_change: tuple[str, str]) -> None:
    key, value = host_ucr_change
    before = container_ucr()
    assert key not in before

    restart_app()

    after = container_ucr()
    assert after.get(key) == value
    assert_synced()
    for protected in PROTECTED_UCR_VARIABLES:
        assert after.get(protected) == before.get(protected)
    assert {k: v for k, v in after.items() if k.startswith("ucsschool/kelvin/")} == {
        k: v for k, v in before.items() if k.startswith("ucsschool/kelvin/")
    }

    handler_unset([key])
    restart_app()

    assert key not in container_ucr()
    assert_synced()
