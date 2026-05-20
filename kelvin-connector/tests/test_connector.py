from unittest.mock import MagicMock, patch

import pytest
from kelvin_connector.connector import main


@pytest.fixture
def good_env(monkeypatch):
    monkeypatch.setenv("LDAP_SERVER_TYPE", "master")
    monkeypatch.setenv("PROVISIONING_FQDN", "provisioning.example.com")


def test_main_exits_when_ldap_server_type_is_missing(monkeypatch):
    monkeypatch.delenv("LDAP_SERVER_TYPE", raising=False)
    with pytest.raises(SystemExit) as exc_info:
        main()
    assert exc_info.value.code == 1


def test_main_exits_when_ldap_server_type_is_not_master(monkeypatch):
    monkeypatch.setenv("LDAP_SERVER_TYPE", "backup")
    with pytest.raises(SystemExit) as exc_info:
        main()
    assert exc_info.value.code == 1


def test_main_exits_when_unknown_log_level_is_present(good_env, monkeypatch):
    monkeypatch.setenv("KELVIN_CONNECTOR_LOG_LEVEL", "DOESNOTEXIST")
    with pytest.raises(SystemExit) as exc_info:
        main()
    assert exc_info.value.code == 1


def test_main_exits_when_provisioning_fqdn_is_missing(good_env, monkeypatch):
    monkeypatch.delenv("PROVISIONING_FQDN")
    with pytest.raises(SystemExit) as exc_info:
        main()
    assert exc_info.value.code == 1


def test_main_exits_when_build_settings_raises(good_env):
    with patch("kelvin_connector.connector.build_settings", side_effect=RuntimeError("bad config")):
        with pytest.raises(SystemExit) as exc_info:
            main()
    assert exc_info.value.code == 1


def test_main_happy_path(good_env):
    mock_settings = MagicMock()
    mock_engine = MagicMock()
    mock_storage_factory = MagicMock()
    mock_consumer_instance = MagicMock()
    mock_consumer_cls = MagicMock(return_value=mock_consumer_instance)
    mock_asyncio_run = MagicMock()

    with (
        patch("kelvin_connector.connector.build_settings", return_value=mock_settings),
        patch("kelvin_connector.connector.build_engine", return_value=mock_engine) as p_engine,
        patch(
            "kelvin_connector.connector.build_kelvin_storage_session_factory",
            return_value=mock_storage_factory,
        ) as p_storage,
        patch("kelvin_connector.connector.SynchronizationManager"),
        patch("kelvin_connector.connector.KelvinConnectorEventHandler"),
        patch("kelvin_connector.connector.ConsumerModule", mock_consumer_cls),
        patch("kelvin_connector.connector.asyncio.run", mock_asyncio_run),
    ):
        main()

    p_engine.assert_called_once_with(mock_settings)
    p_storage.assert_called_once_with(mock_engine)
    mock_consumer_cls.assert_called_once()
    _, kwargs = mock_consumer_cls.call_args
    assert kwargs["name"] == "kelvin-connector"
    assert kwargs["provisioning_url"] == "https://provisioning.example.com/univention/provisioning"
    mock_asyncio_run.assert_called_once()
