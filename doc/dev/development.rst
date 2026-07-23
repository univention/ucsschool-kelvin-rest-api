.. SPDX-FileCopyrightText: 2026 Univention GmbH
..
.. SPDX-License-Identifier: AGPL-3.0-only

Development
===========

Local development setup
-----------------------

Requirements
^^^^^^^^^^^^

* `uv <https://docs.astral.sh/uv/>`_ as the Python project / workspace manager.
* Python ``3.11`` (pinned in ``.python-version``; the workspace requires
  ``>=3.11``).
* Docker with the Compose plugin, for running Kelvin and its dependencies
  locally.
* Access to **a running UCS instance**. A local Kelvin container still needs a
  real UCS host for the UDM REST API and for credentials/certificates — the
  container is not self-contained.

.. note::

   ``python-ldap`` (a transitive dependency of ``univention-lib-slim``) builds
   C extensions and has additional system requirements. See the
   `python-ldap installation notes
   <https://www.python-ldap.org/en/python-ldap-3.4.3/installing.html#installing-from-pypi>`_.

Install the Python environment
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

.. code-block:: shell

   uv sync        # install all workspace packages and dev dependencies

Run any command inside the environment with ``uv run <command>``.

Run Kelvin locally
^^^^^^^^^^^^^^^^^^

The local workflow has two steps:

.. code-block:: shell

   make fetch-vm-data TARGET="<IP/FQDN of a UCS host>"
   make dev-server

* ``make fetch-vm-data`` copies the secrets and configuration needed to talk to
  that host's UDM REST API into ``dev/_vm_config/`` (machine/LDAP secrets, the
  CA certificate, ``base.conf``, a generated ``env`` file, and test data).
  This directory is generated and must **never** be committed.
* ``make dev-server`` builds the Kelvin image and starts the local stack with
  ``docker compose -f dev/docker-compose.yaml up --watch`` (compose project
  ``kelvin-dev``). The API is then reachable at
  ``http://127.0.0.1:8911/ucsschool/kelvin/``.

Thanks to Compose ``--watch``, changes to the source code are synchronized into
the running container automatically and take effect immediately; changes to
``pyproject.toml``, ``uv.lock`` or the ``Dockerfile`` trigger a rebuild.

The dev stack starts three services:

``postgres``
   ``postgres:15-bookworm``, exposed on ``5432`` — the ``v2`` read cache.

``kelvin``
   the FastAPI application (``docker/Dockerfile`` target ``kelvin-prod``),
   exposed on ``8911``.

``connector``
   the Provisioning Consumer (``docker/Dockerfile`` target ``connector-prod``),
   which syncs LDAP changes into the cache. Its subscription is created by
   ``make setup-provisioning-subscription`` (run as a dependency of
   ``dev-server``).

Other useful targets
^^^^^^^^^^^^^^^^^^^^^

Run ``make`` (or ``make help``) for the self-documenting list.

``make build-docker-image``
   Build the production image
   (``docker build … -f docker/Dockerfile .``).

``make alembic-migration``
   Autogenerate a new Alembic revision from the running dev-server database
   (see :doc:`database`).

``make update-architecture-docs``
   Regenerate the entity tables and the ER diagram under
   ``doc/dev/architecture/`` from the SQLAlchemy models
   (``sqlalchemy_to_rst.py`` and ``render_er_diagram.py``).

Project structure
-----------------

The repository is a **uv workspace**: a single root ``pyproject.toml`` aggregates
the member packages under ``[tool.uv.workspace]`` and ``uv.lock`` pins the
resolved graph. ``kelvin-api`` is the root project itself; the others are
workspace members.

.. list-table::
   :header-rows: 1
   :widths: 2 5

   * - Path
     - Purpose
   * - ``kelvin-api/``
     - The FastAPI application (``ucsschool/kelvin/``), static files and the
       API test suite. This is the root project.
   * - ``kelvin-connector/``
     - The Provisioning Consumer that syncs Nubus/LDAP changes into the
       ``v2`` cache (``src/kelvin_connector/``). See :doc:`synchronisation`.
   * - ``ucsschool-objects/``
     - The ``v2`` read-cache library: a persistence-agnostic, ports-and-adapters
       domain layer with a SQLAlchemy/PostgreSQL adapter. Used by both the
       ``v2`` read path and the connector. Has no UDM/LDAP/FastAPI/Pydantic
       dependencies.
   * - ``ucs-school-lib/``
     - The vendored UCS\@school core library (``ucsschool.lib``).
   * - ``ucs-school-import/``
     - The vendored UCS\@school import framework (``ucsschool.importer``).
   * - ``univention-directory-manager-modules-slim/``
     - Slim UDM modules that query the UDM REST API.
   * - ``univention-lib-slim/``
     - Slim Univention utility library.
   * - ``alembic/``
     - Database migrations for the ``v2`` cache (see :doc:`database`).
   * - ``dev/``
     - Local development tooling: ``docker-compose.yaml`` and the generated
       ``_vm_config/``.
   * - ``docker/``
     - Multi-stage ``Dockerfile`` (``kelvin-prod`` / ``connector-prod``) and
       container start scripts.
   * - ``appcenter/``
     - Univention App Center packaging (jinja templates, install/remove
       scripts, app settings, provisioning setup).
   * - ``ucs-test-ucsschool-kelvin/``
     - ``ucs-test`` integration / end-to-end suite that runs against an
       installed Kelvin on a real UCS system.
   * - ``doc/``
     - Sphinx documentation: ``dev/`` (this developer manual) and ``docs/``
       (end-user documentation).

The FastAPI entry point is ``kelvin-api/ucsschool/kelvin/main.py``.
Routes are organized under ``kelvin-api/ucsschool/kelvin/routers/`` in two
versioned subpackages, ``v1/`` and ``v2/``.
The ``v1`` routes talk to the UDM REST API / LDAP per request; the ``v2`` read
routes read from the PostgreSQL cache, while ``v2`` **write** routes reuse the
``v1`` handlers. See :doc:`api-reference` and :doc:`architecture`.

Coding guidelines
-----------------

Code style and static checks run through
`pre-commit <https://pre-commit.com/>`_ (``.pre-commit-config.yaml``) on a
``python3.11`` environment. Run all hooks before pushing:

.. code-block:: shell

   pre-commit run -a

.. list-table::
   :header-rows: 1
   :widths: 2 2 3

   * - Tool
     - Config
     - Scope / notes
   * - ``isort``
     - ``.isort.cfg``
     - ``profile=black``, line length 105.
   * - ``black``
     - ``.black``
     - line length 105, target ``py311``.
   * - ``flake8``
     - ``.flake8``
     - line length 105.
   * - ``mypy --strict``
     - ``[tool.mypy]`` in ``pyproject.toml``
     - scoped to ``ucsschool-objects/`` only.
   * - ``basedpyright``
     - ``pyrightconfig.json`` + ``basedpyright-baseline.json``
     - runs against a committed baseline (baseline mode ``auto``).
   * - ``bandit``
     - ``.bandit``
     - security scan; test dirs excluded.
   * - ``pre-commit-hooks`` / ``pygrep-hooks``
     - —
     - trailing-whitespace, large-files, JSON/YAML/XML checks, no-eval,
       blanket-noqa, rst-backticks.

.. note::

   There is **no Ruff** in the stack despite what an older documentation scaffold might
   suggest — formatting/linting is ``isort`` + ``black`` + ``flake8``, typing is
   ``mypy`` (strict, ``ucsschool-objects`` only) + ``basedpyright``.

Types and models
^^^^^^^^^^^^^^^^^

The HTTP layer uses **Pydantic v1** (``pydantic[dotenv,email]<2`` is pinned;
models still use ``.dict()`` etc.). Don't upgrade to Pydantic v2 casually.
The FastAPI version is likewise pinned (``>=0.95.2,<0.98.0``). ``ucsschool-objects``
is fully typed and gated by ``mypy --strict``.

Commit messages
^^^^^^^^^^^^^^^^

Two ``commit-msg`` hooks are enforced:

* **Conventional Commits** (``conventional-pre-commit --strict``).
* An **issue reference** on its own line after a blank line — either
  ``Issue <group>/<project>#<n>`` or ``Bug #<n>``.

.. code-block:: text

   feat(kelvin): add cache-invalidation endpoint

   Issue univention/dev/education/ucsschool-kelvin-rest-api#42

.. note::

   When staging several commits at once, stage ``.pre-commit-config.yaml``
   first — pre-commit aborts if that file is modified but unstaged.

Testing
-------

Tests use ``pytest`` (async mode is enabled globally:
``addopts = "--verbose --showlocals -p no:warnings --asyncio-mode=auto"`` in the
root ``pyproject.toml``).

.. code-block:: shell

   uv run pytest                                   # from within a package dir
   uv run pytest path/to/test_foo.py::test_bar     # a single test

Each workspace package owns its own ``tests/`` directory and its own pytest /
coverage configuration; CI runs one job per package (inside the built Docker
image).

Testing strategy
^^^^^^^^^^^^^^^^^

* **Unit tests** live in each package's ``tests/`` — most importantly
  ``ucsschool-objects/tests/`` (domain, adapters, and an architecture test
  ``test_architecture.py`` that enforces the ports-and-adapters import rules)
  and ``kelvin-connector/tests/`` (sync logic, mocked).
* **kelvin-api/tests/** is integration-style: it uses FastAPI's ``TestClient``,
  real JWT creation, and expects LDAP/UDM connectivity (CI stubs the ``LDAP_*``
  environment). ``test_route_v1_v2_parity.py`` keeps the two API versions in
  sync.
* **End-to-end** tests live in ``ucs-test-ucsschool-kelvin/`` and run against an
  installed Kelvin app on a real UCS system.

Test database
^^^^^^^^^^^^^

``ucsschool-objects/tests/conftest.py`` provides two engine fixtures:

* **SQLite in-memory** (default) — the schema is created directly from the ORM
  metadata (``Base.metadata.create_all``), not via Alembic. Fast, but its
  ``LIKE`` / ``ILIKE`` semantics differ from PostgreSQL.
* **PostgreSQL via** ``testcontainers`` (``PostgresContainer("postgres:15",
  driver="psycopg")``) — used for the behavior that depends on real PostgreSQL
  (for example the case-insensitive trigram search). **Skipped in CI** to avoid Docker
  registry pull limits, unless ``CORELIB_POSTGRES_TEST_URL`` is provided.

Coverage
^^^^^^^^

``ucsschool-objects`` and ``kelvin-connector`` require **100% branch
coverage** (CI runs with ``--cov-fail-under=100``). ``kelvin-api`` and
``ucs-school-lib`` use configurable CI coverage thresholds.
