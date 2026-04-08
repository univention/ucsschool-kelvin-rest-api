# ucsschool-objects

This is an internal library designed to query and manipulate ucsschool-objects.

While the library uses a SQL database to persist the objects,
it exposes pydantic models and means to manipulate those pydantic objects.

## Kelvin V2 core library

The package provides a hexagonal read/search core in
`ucsschool_objects.core` for the object types User, Group, and School.

- Ports: `UserReader`, `GroupReader`, `SchoolReader`
- SQLAlchemy adapter: `ucsschool_objects.core.adapters.sqlalchemy_readers`
- Query model: `SearchQuery`, `Filter`, `And`, `Or`, `SortSpec`
- Relationship loading model: `LoadSpec` and the `UNLOADED` sentinel

The initial scope is intentionally read/search only.

Important design decision:
The core library does not execute UDM hooks or Kelvin PyHooks.

## Type checking

Protocol conformance of the SQLAlchemy readers is enforced statically with `mypy`.
The file `tests/test_protocol_conformance.py` assigns the concrete reader adapters to
the `UserReader`, `GroupReader`, and `SchoolReader` protocols so a type mismatch fails
the strict type check.

Run it with:

```bash
make typecheck-ucsschool-objects
```