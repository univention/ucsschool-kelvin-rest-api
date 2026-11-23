# SPDX-FileCopyrightText: 2026 Univention GmbH
# SPDX-License-Identifier: AGPL-3.0-only

import logging
from pathlib import Path
from typing import IO

import pytest

from ucsschool.kelvin import host_ucr
from ucsschool.kelvin.host_ucr import HostConfigRegistry, HostUcrError
from univention.config_registry.backend import ConfigRegistry

BASE_FILES = (
    "base.conf",
    "base-defaults.conf",
    "base-forced.conf",
    "base-ldap.conf",
    "base-schedule.conf",
)


class ContainerConfigRegistry(ConfigRegistry):
    PREFIX: str = ""


def write_layer(directory: Path, name: str, values: dict[str, str]) -> None:
    lines = [f"# univention_ {name}", ""] + [f"{key}: {value}" for key, value in values.items()]
    (directory / name).write_text("\n".join(lines) + "\n")


def write_host_base(directory: Path, values: dict[str, str]) -> None:
    write_layer(directory, "base.conf", {"ldap/base": "dc=test", **values})


@pytest.fixture(autouse=True)
def no_custom_baseconf(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("UNIVENTION_BASECONF", raising=False)


@pytest.fixture(autouse=True)
def host_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    directory = tmp_path / "host"
    directory.mkdir()
    for name in BASE_FILES:
        write_layer(directory, name, {})
    write_host_base(directory, {})
    monkeypatch.setattr(HostConfigRegistry, "PREFIX", str(directory))
    return directory


@pytest.fixture(autouse=True)
def container_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    directory = tmp_path / "container"
    directory.mkdir()
    monkeypatch.setattr(ContainerConfigRegistry, "PREFIX", str(directory))
    return directory


def container_values() -> dict[str, str | None]:
    registry = ContainerConfigRegistry()
    registry.load()
    return dict(registry.items())


@pytest.mark.parametrize(
    "key,expected",
    [
        ("ucsschool/import/set/homedrive", True),
        ("ucsschool/ldap/default/groupprefix/pupils", True),
        ("ucsschool/validation/logging/enabled", True),
        ("groups/default/domainusers", True),
        ("users/default/administrator", True),
        ("dhcpd/ldap/base", True),
        ("ldap/server/name", True),
        ("ldap/server/port", True),
        ("mail/hosteddomains", True),
        ("ucsschool/singlemaster", True),
        ("ucsschool/local/oulist", True),
        ("ucsschool/username/max_length", True),
        ("ucsschool/default/share/nfs", True),
        ("ucsschool/kelvin/processes", False),
        ("ldap/hostdn", False),
        ("ldap/base", False),
        ("ldap/server/addition", False),
        ("server/role", False),
        ("hostname", False),
        ("domainname", False),
        ("proxy/filter/groupdefault/foo", False),
        ("ucsschool/singlemaster/foo", False),
        ("ucsschool/import", False),
    ],
)
def test_is_synced(key: str, expected: bool) -> None:
    assert host_ucr.is_synced(key) is expected


def test_synced_keys_expands_prefixes_of_all_registries() -> None:
    keys = host_ucr.synced_keys(
        {"ucsschool/import/a": "1", "ldap/hostdn": "x"},
        {"ucsschool/ldap/b": "2", "ucsschool/kelvin/c": "3"},
    )
    assert keys == sorted(host_ucr.SYNCED_KEYS | {"ucsschool/import/a", "ucsschool/ldap/b"})


def test_diff_sets_differing_and_unsets_missing_values() -> None:
    host = {"ucsschool/import/a": "new", "ucsschool/import/same": "1", "ldap/hostdn": "host"}
    container = {
        "ucsschool/import/a": "old",
        "ucsschool/import/same": "1",
        "ucsschool/import/gone": "x",
        "ldap/hostdn": "container",
        "server/role": "memberserver",
    }
    assert host_ucr.diff(host, container) == {"ucsschool/import/a": "new", "ucsschool/import/gone": None}


def test_diff_keeps_empty_string() -> None:
    assert host_ucr.diff({"ucsschool/singlemaster": ""}, {}) == {"ucsschool/singlemaster": ""}


def test_host_registry_reads_all_layers(host_dir: Path) -> None:
    write_layer(
        host_dir, "base-defaults.conf", {"ucsschool/import/a": "default", "ucsschool/import/b": "b"}
    )
    write_host_base(host_dir, {"ucsschool/import/a": "normal"})
    write_layer(host_dir, "base-forced.conf", {"ucsschool/singlemaster": "true"})
    registry = HostConfigRegistry()
    registry.load()
    assert registry["ucsschool/import/a"] == "normal"
    assert registry["ucsschool/import/b"] == "b"
    assert registry["ucsschool/singlemaster"] == "true"


@pytest.mark.parametrize("missing", ["base-ldap.conf", "base-schedule.conf"])
def test_host_registry_requires_all_files(host_dir: Path, missing: str) -> None:
    (host_dir / missing).unlink()
    (host_dir / "base-forced.conf").unlink()
    (host_dir / "base-forced.conf").mkdir()
    with pytest.raises(HostUcrError) as exc_info:
        HostConfigRegistry()
    assert str(exc_info.value) == (
        f"Host UCR files are missing or aren't regular files below {host_dir}:"
        f" {', '.join(sorted(('base-forced.conf', missing)))}. On the host, remove any directory"
        " of that name in /etc/univention, run 'ucr dump' to recreate the files, and restart the app."
    )


def test_sync(host_dir: Path, container_dir: Path, caplog: pytest.LogCaptureFixture) -> None:
    write_host_base(host_dir, {"ucsschool/import/a": "new", "ldap/hostdn": "host"})
    write_layer(host_dir, "base-ldap.conf", {"ucsschool/singlemaster": "false"})
    write_layer(
        container_dir,
        "base.conf",
        {
            "ucsschool/import/a": "old",
            "ucsschool/import/gone": "x",
            "ldap/hostdn": "container",
            "ucsschool/kelvin/processes": "4",
        },
    )
    caplog.set_level(logging.INFO, logger=host_ucr.__name__)
    changes = host_ucr.sync(HostConfigRegistry(), ContainerConfigRegistry())
    assert changes == {
        "ucsschool/import/a": "new",
        "ucsschool/import/gone": None,
        "ucsschool/singlemaster": "false",
    }
    assert container_values() == {
        "ucsschool/import/a": "new",
        "ucsschool/singlemaster": "false",
        "ldap/hostdn": "container",
        "ucsschool/kelvin/processes": "4",
    }
    assert "ucsschool/import/gone: unset" in caplog.messages
    assert "ucsschool/import/a: 'new'" in caplog.messages
    assert "Synced 3 UCR variable(s) from the host." in caplog.messages
    assert not [record for record in caplog.records if record.levelno >= logging.WARNING]


def test_sync_is_idempotent(host_dir: Path, container_dir: Path) -> None:
    write_host_base(host_dir, {"ucsschool/import/a": "1"})
    host = HostConfigRegistry()
    container = ContainerConfigRegistry()
    assert host_ucr.sync(host, container) == {"ucsschool/import/a": "1"}
    mtime = (container_dir / "base.conf").stat().st_mtime_ns
    assert host_ucr.sync(host, container) == {}
    assert (container_dir / "base.conf").stat().st_mtime_ns == mtime


def test_sync_warns_about_shadowing_container_layer(
    host_dir: Path, container_dir: Path, caplog: pytest.LogCaptureFixture
) -> None:
    write_host_base(host_dir, {"ucsschool/import/a": "host"})
    write_layer(container_dir, "base-forced.conf", {"ucsschool/import/a": "forced"})
    host_ucr.sync(HostConfigRegistry(), ContainerConfigRegistry())
    assert [r.getMessage() for r in caplog.records if r.levelno == logging.WARNING] == [
        "ucsschool/import/a: container value 'forced' is shadowed by a container UCR layer other"
        " than 'normal'"
    ]


@pytest.fixture
def patched_main(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(host_ucr, "ConfigRegistry", ContainerConfigRegistry)


@pytest.mark.usefixtures("patched_main")
def test_main_syncs(host_dir: Path, container_dir: Path) -> None:
    write_host_base(host_dir, {"ucsschool/import/a": "1"})
    assert host_ucr.main([]) == 0
    assert container_values() == {"ucsschool/import/a": "1"}


@pytest.mark.usefixtures("patched_main")
def test_main_lists_keys(
    host_dir: Path, container_dir: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    write_host_base(host_dir, {"ucsschool/import/a": "1", "hostname": "h"})
    write_layer(container_dir, "base.conf", {"ucsschool/ldap/b": "2"})
    assert host_ucr.main(["--list"]) == 0
    assert capsys.readouterr().out.splitlines() == sorted(
        host_ucr.SYNCED_KEYS | {"ucsschool/import/a", "ucsschool/ldap/b"}
    )
    assert container_values() == {"ucsschool/ldap/b": "2"}


@pytest.mark.usefixtures("patched_main")
def test_main_list_fails_on_truncated_host_base(
    host_dir: Path, capsys: pytest.CaptureFixture[str], caplog: pytest.LogCaptureFixture
) -> None:
    (host_dir / "base.conf").write_text("ldap/base: dc=test\n")
    assert host_ucr.main(["--list"]) == 1
    assert capsys.readouterr().out == ""
    assert caplog.messages == [
        f"Syncing the host UCR variables failed: Host UCR files in {host_dir} are unreadable or"
        " truncated: 'ldap/base' is not set"
    ]


@pytest.mark.usefixtures("patched_main")
def test_main_list_fails_on_non_utf8_host_file(host_dir: Path, caplog: pytest.LogCaptureFixture) -> None:
    (host_dir / "base.conf").write_bytes(
        b"# univention_ base.conf\n\nldap/base: dc=test\nfoo/bar: \xff\n"
    )
    assert host_ucr.main(["--list"]) == 1
    assert caplog.messages[0].startswith(
        f"Syncing the host UCR variables failed: Host UCR files in {host_dir} aren't valid UTF-8: "
    )


@pytest.mark.usefixtures("patched_main")
def test_main_fails_on_missing_host_file(host_dir: Path, caplog: pytest.LogCaptureFixture) -> None:
    (host_dir / "base.conf").unlink()
    assert host_ucr.main([]) == 1
    assert caplog.messages == [
        "Syncing the host UCR variables failed: Host UCR files are missing or aren't regular files"
        f" below {host_dir}: base.conf. On the host, remove any directory of that name in"
        " /etc/univention, run 'ucr dump' to recreate the files, and restart the app."
    ]


@pytest.mark.usefixtures("patched_main")
def test_main_fails_on_truncated_host_base(
    host_dir: Path, container_dir: Path, caplog: pytest.LogCaptureFixture
) -> None:
    write_layer(container_dir, "base.conf", {"ucsschool/import/a": "1"})
    (host_dir / "base.conf").write_text("ldap/base: dc=test\n")
    assert host_ucr.main([]) == 1
    assert container_values() == {"ucsschool/import/a": "1"}
    assert caplog.messages == [
        f"Syncing the host UCR variables failed: Host UCR files in {host_dir} are unreadable or"
        " truncated: 'ldap/base' is not set"
    ]


@pytest.mark.usefixtures("patched_main")
def test_main_fails_on_unreadable_host_base(
    host_dir: Path, container_dir: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    write_layer(container_dir, "base.conf", {"ucsschool/import/a": "1"})
    unreadable = str(host_dir / "base.conf")

    def deny(file: str, mode: str = "r", encoding: str | None = None) -> IO[str]:
        if file == unreadable:
            raise PermissionError(file)
        return open(file, mode, encoding=encoding)

    monkeypatch.setattr("univention.config_registry.backend.open", deny, raising=False)
    assert host_ucr.main([]) == 1
    assert container_values() == {"ucsschool/import/a": "1"}


@pytest.mark.usefixtures("patched_main")
def test_main_fails_on_non_utf8_host_file(
    host_dir: Path, container_dir: Path, caplog: pytest.LogCaptureFixture
) -> None:
    write_layer(container_dir, "base.conf", {"ucsschool/import/a": "1"})
    (host_dir / "base.conf").write_bytes(
        b"# univention_ base.conf\n\nldap/base: dc=test\nfoo/bar: \xff\n"
    )
    assert host_ucr.main([]) == 1
    assert container_values() == {"ucsschool/import/a": "1"}
    assert len(caplog.messages) == 1
    assert caplog.messages[0].startswith(
        f"Syncing the host UCR variables failed: Host UCR files in {host_dir} aren't valid UTF-8: "
    )


@pytest.mark.usefixtures("patched_main")
def test_main_skips_sync_when_requested(
    host_dir: Path,
    container_dir: Path,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    monkeypatch.setenv("SKIP_UCSSCHOOL_KELVIN_HOST_UCR_SYNC", "true")
    write_host_base(host_dir, {"ucsschool/import/a": "1"})
    assert host_ucr.main([]) == 0
    assert container_values() == {}
    assert caplog.messages == [
        "Skipped syncing the host UCR variables, because SKIP_UCSSCHOOL_KELVIN_HOST_UCR_SYNC is 'true'."
    ]
