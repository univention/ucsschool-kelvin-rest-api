# AGENTS.md — Kelvin REST API

## Project overview

The **Kelvin REST API** is a REST API for managing **UCS@school** data (users, schools, school classes, roles, workgroups, etc.). It is part of the **Univention Corporate Server (UCS)** ecosystem.

### Technology stack overview

The write path is unchanged between Kelvin `v1` and `v2`:

```
HTTP clients
     │
     ▼
Kelvin REST API   (FastAPI; kelvin-api/)
     │
     ▼
UCS@school import / UCS@school library   (ucs-school-import/, ucs-school-lib/)
     │                    │
     │  (sometimes direct LDAP for performance / missing UDM attributes)
     ▼                    ▼
UDM REST API          OpenLDAP
  (Nubus)              (Nubus)
```

Kelvin `v2` adds a read cache and a separate read path that bypasses the legacy libraries:

```
HTTP clients
     │
     ▼
Kelvin REST API   (FastAPI; kelvin-api/)
     │
     ▼
ucsschool-objects   (ucsschool-objects/)
     │
     ▼
SQL database   (PostgreSQL in production, SQLite in tests)
     ▲
     │ Cache writers:
     │   1. Kelvin's write path stores each response before returning it.
     │   2. A Provisioning Consumer sidecar (planned — `kelvin-connector/`
     │      is currently a scaffold) will react to LDAP change events from
     │      Nubus Provisioning to keep the cache eventually consistent with
     │      OpenLDAP, covering writes that bypass Kelvin.
```

See the project [`README.md`](./README.md) for the full v1 / v2 diagrams (ASCII and Mermaid).

### Key concepts

- **UCS (Univention Corporate Server)**: A Debian-based Linux distribution with an integrated IAM called **Nubus**.
- **Nubus**: The IAM at the heart of UCS. Stores all identity and access data (users, groups, computers, etc.) in **OpenLDAP**.
- **UDM (Univention Directory Manager)**: Nubus's data model and Python library. The REST interface is called the **UDM REST API** or **UDM HTTP REST API**.
- **UCS@school**: An add-on/app on top of UCS that provides data models, functions, and UIs for the educational sector. UCS@school only runs on UCS (not on Nubus-for-Kubernetes).
- **UCS@school library** (`ucs-school-lib/`): Core UCS@school business logic. Data models inherit from UDM and have been adapted to use the UDM REST API instead of the UDM Python library directly.
- **UCS@school import** (`ucs-school-import/`): Bulk-import mechanism built on top of the UCS@school library. Its data models inherit from the UCS@school library's models, adding attributes and functions. Kelvin uses both.
- **Kelvin** (`kelvin-api/`): The REST API frontend. Data and control flow from the HTTP endpoints into UCS@school libraries (business logic), then to the UDM REST API, which persists data in LDAP.
- **`ucsschool-objects`** (`ucsschool-objects/`): The Kelvin `v2` read-cache library. A persistence-agnostic, ports-and-adapters package with a SQLAlchemy adapter that stores UCS@school objects in PostgreSQL. It has no UDM, LDAP, FastAPI, or Pydantic dependencies — see [`ucsschool-objects/AGENTS.md`](ucsschool-objects/AGENTS.md) and [`ucsschool-objects/README.md`](ucsschool-objects/README.md).
- **Provisioning Consumer** (`kelvin-connector/`): A sidecar process that runs alongside the Kelvin REST API container. The design is to subscribe to the [Nubus Provisioning event system](https://docs.software-univention.de/manual/5.2/en/domain-ldap/nubus-provisioning-service.html#nubus-provisioning-service) and apply LDAP changes to the SQL cache via the `ucsschool-objects` library, so the cache stays eventually consistent with LDAP even when other clients write directly to UDM/OpenLDAP. **Currently a scaffold**: the package, its Docker target (`connector-prod` in `docker/Dockerfile`), and its startup script (`docker/start-connector.sh`, gated on `LDAP_SERVER_TYPE=master`) are wired up, but the event-subscription and cache-update logic are not yet implemented — see [`kelvin-connector/README.md`](kelvin-connector/README.md).

> **Layer note**: Although it is technically a layer violation, Kelvin and UCS@school libraries sometimes access LDAP directly for performance or because an attribute is not exposed by the UDM REST API.

### Slim UDM packages

Two trimmed-down packages in this repo replace the full UDM Python library for querying via REST:

- `univention-directory-manager-modules-slim/` — slim UDM modules that query the UDM REST API
- `univention-lib-slim/` — slim Univention utility library

---

## Repository layout

The repo is a **`uv` workspace**: a single root `pyproject.toml` aggregates the member packages listed under `[tool.uv.workspace]`, and `uv.lock` pins the resolved dependency graph. There is no per-package `setup.py` / `setup.cfg` / `requirements*.txt` anymore.

```
pyproject.toml               Root project + uv workspace config; pytest config; alembic config
uv.lock                      Resolved dependency lockfile
Makefile                     Dev workflow targets (fetch-vm-data, dev-server, alembic-migration, …)
.pre-commit-config.yaml      Pre-commit hooks (see "Code quality")

kelvin-api/                  Main Kelvin REST API (FastAPI app)
  ucsschool/kelvin/          Python package: main.py, routers/, config.py, ldap.py, database.py, …
  tests/                     Pytest test suite
  changelog.rst              Release changelog (current: v3.3.0 TBD)

kelvin-connector/            Provisioning Consumer (Nubus → SQL cache sidecar)
  src/                       Python package
  tests/                     Pytest suite

ucs-school-lib/              UCS@school core library
  modules/ucsschool/lib/     Python modules
  tests/                     Test suite

ucs-school-import/           UCS@school bulk-import framework
  modules/                   Python modules
  tests/                     Test cases

ucsschool-objects/           Kelvin v2 read-cache library (PostgreSQL via SQLAlchemy)
  src/ucsschool_objects/     Domain models, query DSL, ports, SQLAlchemy adapter
  tests/                     Pytest suite (100 % branch coverage required)
  AGENTS.md                  Conventions and architecture for this package

univention-directory-manager-modules-slim/   Slim UDM (queries UDM REST API)
univention-lib-slim/                         Slim Univention utilities

ucs-test-ucsschool-kelvin/   Integration tests

alembic/                     Alembic migrations for the v2 SQL cache schema
dev/                         Local development docker-compose (used by `make dev-server`)

doc/docs/                    Sphinx documentation
docker/                      Multi-stage Dockerfile (kelvin-prod and connector-prod targets)
appcenter/                   Univention App Center configuration
.gitlab-ci/                  GitLab CI job scripts
```

---

## Development

### Setup

```bash
uv sync                      # install all workspace packages and dev deps
```

Useful Makefile targets (run `make` for the current list):

```bash
make fetch-vm-data TARGET=<UCS host>   # pull UCS credentials/config for local dev
make dev-server                        # start local Kelvin via docker compose (dev/docker-compose.yaml)
make alembic-migration                 # generate a new alembic revision for the SQL cache
make build-docker-image                # build the production Kelvin image (docker/Dockerfile)
```

### Running tests

```bash
uv run pytest                                          # whole workspace (configured in root pyproject.toml)
uv run pytest ucs-school-lib/modules/ucsschool/lib/tests/   # one package
uv run pytest kelvin-api/tests/                        # one package
uv run pytest path/to/test_foo.py::test_bar            # single test
```

Pytest config lives in the root `pyproject.toml` under `[tool.pytest.ini_options]`:
`addopts = "--verbose --showlocals -p no:warnings --asyncio-mode=auto"`.
Each workspace package may add its own gates — e.g. `ucsschool-objects/` requires **100 % branch coverage**.

### Code quality

Pre-commit hooks are configured in `.pre-commit-config.yaml` and run on `python3.11`:

```bash
pre-commit run --all-files   # run all hooks manually
```

Hooks:

| Hook | Purpose | Notes |
|---|---|---|
| **black** | Formatting | config: `.black` |
| **isort** | Import ordering | config: `.isort.cfg` |
| **flake8** | Linting | config: `.flake8` |
| **mypy --strict** | Static typing | scoped to `ucsschool-objects/` only |
| **bandit** | Security scanning | config: `.bandit`; tests excluded |
| **pre-commit-hooks** | trailing-whitespace, large-files, json/yaml/xml checks | — |
| **pygrep-hooks** | python-no-eval, blanket-noqa, rst-backticks | — |
| **conventional-pre-commit** (commit-msg) | Conventional Commits format | `--strict` |
| **issue-reference** (commit-msg, local) | Requires `Issue …#N` or `Bug #N` on its own line in the commit body | local pygrep hook |

Commit messages must follow Conventional Commits **and** include an issue / bug reference on its own line after a blank line:

```
feat(kelvin): add cache-invalidation endpoint

Issue univention/ucsschool-kelvin-rest-api#42
```

or `Bug #123456`.

### Key dependencies

Runtime and dev dependencies are declared in the root `pyproject.toml` (`[project].dependencies` and `[dependency-groups].dev`). Some are pinned for compatibility — **don't bump these without checking why**:

| Package | Constraint | Notes |
|---|---|---|
| `fastapi` | `>=0.95.2,<0.98.0` | Pinned below 0.98 |
| `pydantic[dotenv,email]` | `<2` | Still on Pydantic v1 |
| `httpx` | `<0.28.0` | — |
| `pyjwt` | `<2.10` | — |
| `uvicorn` / `gunicorn` | latest | ASGI/WSGI servers |
| `uldap3` | git source | private repo (`git.knut.univention.de/.../uldap3.git`) |
| `openapi-client-udm` | tarball | vendored (`openapi-client-udm-1.0.2.tar.gz`) |
| `psycopg[binary]` | `>=3.3.3` | PostgreSQL driver for the v2 cache |
| `alembic` | `>=1.18.4` | SQL cache migrations |
| `kelvin-connector`, `ucs-school-lib`, `ucs-school-import`, `ucsschool-objects`, `univention-directory-manager-modules` | workspace | resolved from this repo via `[tool.uv.workspace]` |

---

## Architecture notes

- The FastAPI application entry point is `kelvin-api/ucsschool/kelvin/main.py`.
- Routes are organised under `kelvin-api/ucsschool/kelvin/routers/`.
- Authentication is handled in `kelvin-api/ucsschool/kelvin/token_auth.py`.
- LDAP direct access is in `kelvin-api/ucsschool/kelvin/ldap.py`.
- Configuration is in `kelvin-api/ucsschool/kelvin/config.py` and `kelvin-api/ucsschool/kelvin/constants.py`.

### Kelvin `v2` architecture

- The SQL read cache stores UCS@school objects in the representation planned for future (`v3+`) releases. Kelvin `v2` transforms that representation into the `v1` shape before returning it, so the HTTP API stays backwards-compatible.
- Because the read path doesn't go through the UCS@school / UCS@school import libraries, their **read-hooks are no longer executed** in `v2` — a behavioral break worth flagging in any change that touches reads.
- The cache is intended to be kept consistent in two ways:
  - **Synchronous**: each write response is stored in the SQL database before being returned to the client.
  - **Asynchronous** *(planned)*: the Provisioning Consumer (`kelvin-connector/`) sidecar will apply LDAP change events from Nubus Provisioning, covering writes that bypass Kelvin (other UDM REST API clients or direct OpenLDAP writes). The connector package is currently a scaffold; this writer is not active yet.
- Both writers go through the `ucsschool-objects` library. The SQLAlchemy ORM in `ucsschool-objects/src/ucsschool_objects/database_models.py` is the single source of truth for the cache table definitions; the physical schema is evolved via **Alembic** revisions in `alembic/` (root config: `[tool.alembic] script_location = "%(here)s/alembic"`; new revisions: `make alembic-migration`).
- Architecture rules for `ucsschool-objects` are enforced by `tests/test_architecture.py` in that package (combined `pytestarch` + AST-based scan). Don't relax those rules to make a test pass — restructure the import.

---

## CI/CD

GitLab CI (`.gitlab-ci.yml`, includes from `.gitlab-ci/`) runs:
1. Pre-commit / lint checks
2. Unit tests for the workspace packages with coverage reports
3. Docker image build via `docker/Dockerfile` (multi-stage: `kelvin-prod` and `connector-prod` targets, both built on the UCS base image `ucs-base-python-524`)
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
