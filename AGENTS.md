# CLAUDE.md — Kelvin REST API

## Project overview

The **Kelvin REST API** is a REST API for managing **UCS@school** data (users, schools, school classes, roles, workgroups, etc.). It is part of the **Univention Corporate Server (UCS)** ecosystem.

### Technology stack overview

```
HTTP clients
     │
     ▼
Kelvin REST API   (FastAPI, this repo)
     │
     ▼
UCS@school import / UCS@school library   (ucs-school-import/, ucs-school-lib/)
     │                    │
     │  (sometimes direct LDAP for performance / missing UDM attributes)
     ▼                    ▼
UDM REST API          OpenLDAP
  (Nubus)              (Nubus)
```

### Key concepts

- **UCS (Univention Corporate Server)**: A Debian-based Linux distribution with an integrated IAM called **Nubus**.
- **Nubus**: The IAM at the heart of UCS. Stores all identity and access data (users, groups, computers, etc.) in **OpenLDAP**.
- **UDM (Univention Directory Manager)**: Nubus's data model and Python library. The REST interface is called the **UDM REST API** or **UDM HTTP REST API**.
- **UCS@school**: An add-on/app on top of UCS that provides data models, functions, and UIs for the educational sector. UCS@school only runs on UCS (not on Nubus-for-Kubernetes).
- **UCS@school library** (`ucs-school-lib/`): Core UCS@school business logic. Data models inherit from UDM and have been adapted to use the UDM REST API instead of the UDM Python library directly.
- **UCS@school import** (`ucs-school-import/`): Bulk-import mechanism built on top of the UCS@school library. Its data models inherit from the UCS@school library's models, adding attributes and functions. Kelvin uses both.
- **Kelvin** (`kelvin-api/`): The REST API frontend. Data and control flow from the HTTP endpoints into UCS@school libraries (business logic), then to the UDM REST API, which persists data in LDAP.

> **Layer note**: Although it is technically a layer violation, Kelvin and UCS@school libraries sometimes access LDAP directly for performance or because an attribute is not exposed by the UDM REST API.

### Slim UDM packages

Two trimmed-down packages in this repo replace the full UDM Python library for querying via REST:

- `univention-directory-manager-modules-slim/` — slim UDM modules that query the UDM REST API
- `univention-lib-slim/` — slim Univention utility library

---

## Repository layout

```
kelvin-api/                  Main Kelvin REST API (FastAPI app, version 3.2.0)
  ucsschool/kelvin/          Python package: main.py, routers/, config.py, ldap.py, …
  tests/                     Pytest test suite
  setup.py / setup.cfg       Package & pytest config
  requirements_all.txt       All Python dependencies
  changelog.rst              Release changelog

ucs-school-lib/              UCS@school core library
  modules/ucsschool/lib/     Python modules
  tests/                     Test suite

ucs-school-import/           UCS@school bulk-import framework
  modules/                   Python modules
  tests/                     Test cases

univention-directory-manager-modules-slim/   Slim UDM (queries UDM REST API)
univention-lib-slim/                         Slim Univention utilities

ucs-test-ucsschool-kelvin/   Integration tests

doc/docs/                    Sphinx documentation
docker/                      Dockerfile and container startup scripts
appcenter/                   Univention App Center configuration
.gitlab-ci/                  GitLab CI job scripts
```

---

## Development

### Running tests

```bash
# Run all unit tests (ucs-school-lib + kelvin-api)
make tests

# Equivalent explicit command
python3 -m pytest -l -vv --asyncio-mode=auto \
    ucs-school-lib/modules/ucsschool/lib/tests/ \
    kelvin-api/tests/
```

Pytest is configured in `kelvin-api/setup.cfg`:
- `--verbose --showlocals -p no:warnings --asyncio-mode=auto`
- Minimum coverage: 35 %
- Required fixtures: `setup_environ`, `setup_import_config`, `setup_mapped_udm_properties_config`

### Code quality

Pre-commit hooks are configured in `.pre-commit-config.yaml`:

```bash
pre-commit run --all-files   # run all hooks manually
```

Tools used:
- **black** — code formatting (config in `.black`)
- **isort** — import sorting (config in `.isort.cfg`)
- **flake8** — linting (config in `.flake8`)

### Key dependencies (`kelvin-api/requirements_all.txt`)

| Package | Purpose |
|---------|---------|
| `fastapi` | Web framework |
| `uvicorn` / `gunicorn` | ASGI/WSGI servers |
| `pydantic` | Data validation |
| `uldap3` | LDAP client |
| `udm-rest-client` | UDM REST API client |
| `pytest-asyncio` | Async test support |
| `factory_boy` / `Faker` | Test fixtures |

---

## Architecture notes

- The FastAPI application entry point is `kelvin-api/ucsschool/kelvin/main.py`.
- Routes are organised under `kelvin-api/ucsschool/kelvin/routers/`.
- Authentication is handled in `kelvin-api/ucsschool/kelvin/token_auth.py`.
- LDAP direct access is in `kelvin-api/ucsschool/kelvin/ldap.py`.
- Configuration is in `kelvin-api/ucsschool/kelvin/config.py` and `kelvin-api/ucsschool/kelvin/constants.py`.

---

## CI/CD

GitLab CI (`.gitlab-ci.yml`) runs:
1. Pre-commit / lint checks
2. Unit tests for `ucs-school-lib` and `kelvin-api` with coverage reports
3. Docker image build (Alpine Linux base, `docker/kelvin/Dockerfile`)
4. Sphinx documentation build
5. App Center release pipeline

---

## Documentation

Sphinx docs live in `doc/docs/`. Key pages:

- `overview.rst` — API overview
- `resource-*.rst` — per-resource guides (users, schools, classes, roles, workgroups)
- `authentication-authorization.rst` — auth model
- `installation-configuration.rst` — deployment and configuration
- `changelog.rst` → symlink to `kelvin-api/changelog.rst`
