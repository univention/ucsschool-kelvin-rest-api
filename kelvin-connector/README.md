# Kelvin Connector

The connector now uses `dependency-injector` as its composition root.

## Runtime Wiring

The container is defined in `kelvin_connector.containers.ConnectorContainer` and provides:

- SQLAlchemy settings via `build_settings()`
- async engine via `build_engine()`
- Kelvin storage session factory via `build_kelvin_storage_session_factory()`
- `SynchronizationManager` via the storage factory

The entrypoint (`connector` script -> `kelvin_connector.consumer:main`) resolves dependencies from the container instead of manually chaining factory calls.

## Required Environment Variables

- `LDAP_SERVER_TYPE=master`
- `PROVISIONING_FQDN`
- `UCSSCHOOL_KELVIN_DB_URI`

Optional DB variables used by `build_settings()` are still supported:

- `UCSSCHOOL_KELVIN_DB_USERNAME`
- `UCSSCHOOL_KELVIN_DB_PASSWORD_FILE`
