#!/usr/share/ucs-test/runner pytest-3 -s -l -v
## -*- coding: utf-8 -*-
## desc: Kelvin-relevant host UCR variables are synced into the Kelvin container on every start
## tags: [ucs_school_kelvin]
## exposure: dangerous
## packages: []
## bugs: []

# SPDX-FileCopyrightText: 2026 Univention GmbH
# SPDX-License-Identifier: AGPL-3.0-only

import random
import subprocess
import time
import uuid
from collections.abc import Callable, Iterator

import pytest
import requests
from ldap.filter import filter_format

from univention.config_registry import handler_set, handler_unset, ucr
from univention.testing.ucsschool.kelvin_api import RESOURCE_URLS

APP_ID = "ucsschool-kelvin-rest-api"
PROTECTED_UCR_VARIABLES = ("ldap/hostdn", "server/role", "hostname")
PUPILS_GROUP_PREFIX = "ucsschool/ldap/default/groupprefix/pupils"
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


def wait_until_healthy() -> None:
    deadline = time.monotonic() + 300
    while app_shell("python3", "-c", HEALTH_CHECK, check=False).returncode != 0:
        assert time.monotonic() < deadline, "Kelvin did not become healthy."
        time.sleep(2)


def restart_app() -> None:
    subprocess.run(["univention-app", "restart", APP_ID], check=True)  # nosec
    wait_until_healthy()


def reinitialize_app() -> None:
    subprocess.run(["univention-app", "reinitialize", APP_ID], check=True)  # nosec
    wait_until_healthy()


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


@pytest.fixture
def set_pupils_group_prefix() -> Iterator[Callable[[], str]]:
    old_value = ucr.get(PUPILS_GROUP_PREFIX)

    def _set() -> str:
        prefix = f"sus{uuid.uuid4().hex[:6]}-"
        handler_set([f"{PUPILS_GROUP_PREFIX}={prefix}"])
        return prefix

    yield _set
    if old_value is None:
        handler_unset([PUPILS_GROUP_PREFIX])
    else:
        handler_set([f"{PUPILS_GROUP_PREFIX}={old_value}"])
    restart_app()


@pytest.fixture
def create_school(auth_header, delete_ou, delete_ou_cleanup) -> Iterator[Callable[[], str]]:
    created: list[str] = []

    def _create() -> str:
        name = f"testou{random.randint(1000, 9999)}"  # nosec
        created.append(name)
        response = requests.post(
            RESOURCE_URLS["schools"], headers=auth_header, json={"name": name, "display_name": name}
        )
        assert response.status_code == 201, response.text
        return name

    yield _create
    for name in created:
        delete_ou(name)
        delete_ou_cleanup(name)


def assert_group_exists(lo, name: str) -> None:
    assert lo.searchDn(filter_format("(&(objectClass=univentionGroup)(cn=%s))", (name,))), (
        f"Group {name!r} not found."
    )


def test_list_excludes_protected_variables() -> None:
    keys = synced_keys()
    for key in PROTECTED_UCR_VARIABLES:
        assert key not in keys
    assert not [key for key in keys if key.startswith("ucsschool/kelvin/")]


def test_list_includes_ldap_server() -> None:
    assert {"ldap/server/name", "ldap/server/port"} <= set(synced_keys())


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


def test_host_change_synced_on_reinitialize(host_ucr_change: tuple[str, str]) -> None:
    key, old_value = host_ucr_change
    # The old container must hold the old value, so that the UCR files that the reinitialization
    # backs up and restores into the new container are outdated.
    restart_app()
    before = container_ucr()
    assert before.get(key) == old_value
    new_value = uuid.uuid4().hex
    handler_set([f"{key}={new_value}"])

    reinitialize_app()

    after = container_ucr()
    assert after.get(key) == new_value
    assert_synced()
    for protected in PROTECTED_UCR_VARIABLES:
        assert after.get(protected) == before.get(protected)
    assert {k: v for k, v in after.items() if k.startswith("ucsschool/kelvin/")} == {
        k: v for k, v in before.items() if k.startswith("ucsschool/kelvin/")
    }


def test_workers_use_host_change_after_restart(set_pupils_group_prefix, create_school, lo) -> None:
    prefix = set_pupils_group_prefix()
    restart_app()

    school = create_school()

    assert_group_exists(lo, f"{prefix}{school.lower()}")


def test_workers_use_host_change_after_reinitialize(set_pupils_group_prefix, create_school, lo) -> None:
    set_pupils_group_prefix()
    restart_app()
    prefix = set_pupils_group_prefix()

    reinitialize_app()

    school = create_school()
    assert_group_exists(lo, f"{prefix}{school.lower()}")
