from __future__ import annotations

from dependency_injector import providers
from kelvin_connector.containers import ConnectorContainer
from kelvin_connector.sync import SynchronizationManager


class DummyStorageFactory:
    def transaction_scope(self):  # pragma: no cover - not needed for wiring test
        raise NotImplementedError

    def session_scope(self):  # pragma: no cover - not needed for wiring test
        raise NotImplementedError


def test_container_builds_synchronization_manager_from_storage_factory() -> None:
    container = ConnectorContainer()
    fake_storage_factory = DummyStorageFactory()
    container.storage_factory.override(providers.Object(fake_storage_factory))

    manager = container.synchronization_manager()

    assert isinstance(manager, SynchronizationManager)
    assert manager.storage_factory is fake_storage_factory


def test_container_formats_provisioning_url_from_config() -> None:
    container = ConnectorContainer()
    container.config.provisioning_fqdn.from_value("provisioning.example.test")

    assert container.provisioning_url() == "https://provisioning.example.test/univention/provisioning"


class DummyConsumerModule:
    def __init__(self) -> None:
        self.consume_loop_called = False

    def consume_loop(self) -> None:
        self.consume_loop_called = True


def test_container_consumer_module_can_be_overridden_for_startup_smoke() -> None:
    container = ConnectorContainer()
    fake_consumer = DummyConsumerModule()
    container.consumer_module.override(providers.Object(fake_consumer))

    resolved = container.consumer_module()
    resolved.consume_loop()

    assert resolved is fake_consumer
    assert fake_consumer.consume_loop_called is True
