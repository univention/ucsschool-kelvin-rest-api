# SPDX-FileCopyrightText: 2026 Univention GmbH
# SPDX-License-Identifier: AGPL-3.0-only

import json
from unittest.mock import MagicMock, patch

import pytest
from kelvin_connector.ccf_launcher import CCF_BINARY, ccf_database_url, ccf_environment, main
from sqlalchemy.engine import make_url

_CONFIG = {"subscription_name": "kelvin-connector", "subscription_password": "s3cret"}


def test_ccf_database_url_uses_the_kelvin_db_in_the_ccf_schema():
    kelvin_url = make_url("postgresql+psycopg://kelvin:p%40ss%2Fword@db.example:5432/kelvin")

    url = ccf_database_url(kelvin_url)

    assert url == "postgres://kelvin:p%40ss%2Fword@db.example:5432/kelvin?options=-csearch_path%3Dccf"


def test_ccf_environment_sets_the_callback_provisioning_and_database():
    env = ccf_environment(
        {"PROVISIONING_FQDN": "primary.example"}, _CONFIG, "postgres://db", ["", "/a", "/b"]
    )

    assert env["PYTHON_CALLBACK"] == "kelvin_connector.ccf_callback"
    assert env["PYTHON_CALLBACK_PATH"] == "/a:/b"
    assert env["PROVISIONING_HOSTNAME"] == "primary.example"
    assert env["PROVISIONING_NAME"] == "kelvin-connector"
    assert env["PROVISIONING_PASSWORD"] == "s3cret"
    assert env["DATABASE_URL"] == "postgres://db"
    assert env["MAX_ALLOWED_ERRORS"] == "3"
    assert env["ASYNC_PROCESSING"] == "1"
    assert env["PROVISIONING_ACCEPT_INVALID_CERTS"] == "false"


def test_ccf_environment_lets_the_environment_override_the_defaults():
    environ = {"PROVISIONING_FQDN": "primary.example", "MAX_ALLOWED_ERRORS": "7", "OTHER": "kept"}

    env = ccf_environment(environ, _CONFIG, "postgres://db", [])

    assert env["MAX_ALLOWED_ERRORS"] == "7"
    assert env["OTHER"] == "kept"


@pytest.fixture
def provisioning_config_file(tmp_path):
    path = tmp_path / "provisioning_config.json"
    path.write_text(json.dumps(_CONFIG))
    with patch("kelvin_connector.ccf_launcher.PROVISIONING_CONFIG_FILE", path):
        yield path


@pytest.fixture
def kelvin_settings():
    settings = MagicMock(url=make_url("postgresql+psycopg://kelvin:pw@db/kelvin"))
    with patch("kelvin_connector.ccf_launcher.build_settings", return_value=settings):
        yield settings


def test_main_execs_the_ccf_binary(monkeypatch, provisioning_config_file, kelvin_settings):
    monkeypatch.setenv("PROVISIONING_FQDN", "primary.example")

    with patch("kelvin_connector.ccf_launcher.os.execve") as execve:
        main()

    binary, argv, env = execve.call_args.args
    assert (binary, argv) == (CCF_BINARY, [CCF_BINARY])
    assert env["DATABASE_URL"] == "postgres://kelvin:pw@db/kelvin?options=-csearch_path%3Dccf"
    assert env["PROVISIONING_NAME"] == "kelvin-connector"


def test_main_exits_when_provisioning_fqdn_is_missing(monkeypatch):
    monkeypatch.delenv("PROVISIONING_FQDN", raising=False)

    with pytest.raises(SystemExit) as exc_info:
        main()
    assert exc_info.value.code == 1


@pytest.mark.parametrize("content", [None, "not json", json.dumps({"subscription_name": "x"})])
def test_main_exits_when_the_provisioning_config_is_unusable(
    monkeypatch, provisioning_config_file, kelvin_settings, content
):
    monkeypatch.setenv("PROVISIONING_FQDN", "primary.example")
    if content is None:
        provisioning_config_file.unlink()
    else:
        provisioning_config_file.write_text(content)

    with (
        patch("kelvin_connector.ccf_launcher.os.execve") as execve,
        pytest.raises(SystemExit) as exc_info,
    ):
        main()
    assert exc_info.value.code == 1
    execve.assert_not_called()


def test_main_exits_when_the_kelvin_db_settings_are_missing(monkeypatch, provisioning_config_file):
    monkeypatch.setenv("PROVISIONING_FQDN", "primary.example")

    with (
        patch("kelvin_connector.ccf_launcher.build_settings", side_effect=RuntimeError("no db")),
        pytest.raises(SystemExit) as exc_info,
    ):
        main()
    assert exc_info.value.code == 1
