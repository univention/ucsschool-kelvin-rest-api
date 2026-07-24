.. SPDX-FileCopyrightText: 2026 Univention GmbH
..
.. SPDX-License-Identifier: AGPL-3.0-only

Database
========

Kelvin ``v2`` adds the Kelvin DB, an SQL database that serves as a *read cache* for
UCS\@school objects.
Read and search requests are answered from this database instead of querying
LDAP / the UDM REST API,
which is the main reason ``v2`` reads are much faster than ``v1`` reads.
The database is a denormalized projection of the authoritative state in Nubus
(UDM / OpenLDAP);
it is *not* the source of truth.
See :doc:`synchronisation` for how the Kelvin DB is kept consistent.

Engine and driver
-----------------

* **Production:** PostgreSQL, accessed through the ``psycopg`` (v3) driver.
* **Tests:** SQLite in-memory, accessed through ``aiosqlite``.

SQLAlchemy is used in async mode throughout.
A bare ``postgresql://`` URL is rewritten to ``postgresql+psycopg`` at connect
time, so the psycopg v3 driver is always used
(see ``ucsschool-objects/src/ucsschool_objects/core/adapters/sqlalchemy/session.py``
and ``kelvin-api/ucsschool/kelvin/database.py``).

.. note::

   The code deliberately papers over differences between the two backends:

   * JSON columns are declared as ``JSON().with_variant(JSONB(), "postgresql")``,
     because PostgreSQL ``jsonb`` has an equality operator (needed for
     ``SELECT DISTINCT``) while ``json`` does not.
   * UUID string values are coerced to :class:`uuid.UUID` objects, because
     psycopg accepts strings for ``uuid`` columns but SQLite's ``Uuid`` type
     does not.

   Because SQLite's ``LIKE`` / ``ILIKE`` semantics differ from PostgreSQL's,
   the case-insensitive search behavior is verified against a real PostgreSQL
   instance started via ``testcontainers`` (skipped in CI to avoid registry
   pull limits, controlled by an environment variable).

Where the database runs
-----------------------

There is **one active database per domain**, shared by all Kelvin instances in
that domain.

When Kelvin is installed on a primary or backup node, the App Center App
settings prompt the creation of a local PostgreSQL database named
``ucsschool-kelvin-rest-api`` on that node.
The connection details are stored domain-wide in a UDM ``settings/data`` object
(``cn=ucsschool-kelvin-rest-api,cn=data,cn=univention,<ldap_base>``).
The **first installation wins**: subsequent installations on other nodes read
the existing ``settings/data`` object and connect to the same database rather
than using their own local one.
See :doc:`lifecycle` for the full lifecycle, the ``settings/data`` schema, and
the illustrating diagram.

At runtime the API reads the connection coordinates from the App settings
(``ucsschool/kelvin/db/uri``, ``ucsschool/kelvin/db/username``) and the password
from ``/etc/ucsschool/kelvin/postgresql-kelvin.secret``.

.. note::

   There are two independent URL builders — ``get_database_url()`` in
   ``kelvin-api/ucsschool/kelvin/database.py`` (API runtime) and ``_get_url()`` /
   ``build_settings()`` in ``ucsschool-objects`` (used by the core library and
   Alembic). They read overlapping but differently-named environment variables
   and are marked for merging (``# TODO: merge`` in ``session.py``).

Sessions and connection pooling
-------------------------------

Engine and session plumbing lives in
``ucsschool-objects/.../core/adapters/sqlalchemy/session.py``:

* The engine is created with ``pool_size=10`` and ``max_overflow=20``
  (SQLite ``:memory:`` uses a ``StaticPool`` instead).
* Sessions are produced by an ``async_sessionmaker`` with
  ``expire_on_commit=False`` and ``autoflush=False``.
* The public port is ``KelvinStorageSession`` /
  ``KelvinStorageSessionFactory`` (concrete: ``KelvinSqlAlchemySession`` /
  ``KelvinSqlAlchemySessionFactory``), exposing ``transaction_scope()``
  (auto-commit/rollback) and ``session_scope()`` (no auto-commit).
* A session lazily exposes per-entity managers: ``.users``, ``.groups``,
  ``.schools``, ``.roles``.

Database schema
---------------

The SQLAlchemy ORM models in
``ucsschool-objects/src/ucsschool_objects/database_models.py`` are the single
source of truth for the table definitions.
They are declared *internal* — not a public API.
The entities and their relationships are documented in :doc:`architecture`;
the entity-relationship diagram is rendered from
``architecture/er.mmd``.

Tables
^^^^^^

**Core school objects**

``school``
   A school / OU. Unique ``name``; ``public_id`` (UUID, matches the
   ``univentionObjectIdentifier``); JSON columns for
   ``educational_servers``, ``administrative_servers`` and ``udm_properties``.

``group``
   A group (school class or workgroup). Unique ``name`` and ``email``;
   ``has_share``; FK ``school_id`` → ``school.id``; self-referential M:N
   relations for allowed email senders.

``user``
   A person and their account. Unique ``name`` (username) and ``email``;
   ``active`` maps to the UDM ``disabled`` attribute; self-referential M:N
   ``legal_guardians`` / ``legal_wards``; JSON ``udm_properties``.

``role``
   for example ``teacher``, ``student``, ``staff``, ``school_admin``.
   Nine default rows are seeded by the initial migration; ``display_name`` is a
   localized JSON object.

**Junction / auxiliary**

``school_membership``
   The central relationship object linking a ``user`` to a ``school``.
   Carries ``is_primary`` and holds the M:N links to ``groups`` and ``roles``.
   The internally-managed ``primary_user_constraint`` column
   (set by a ``before_insert`` / ``before_update`` ORM event to the ``user_id``
   when ``is_primary`` else ``NULL``) enforces **at most one primary school per
   user** via a unique constraint.

**Association tables** (pure M:N joins)
   ``group_member_association``, ``group_member_role_association``,
   ``group_role_association``, ``school_membership_role_association``,
   ``group_user_email_senders_association``,
   ``group_group_email_senders_association``, ``legal_guardian_association``.

**DN mapping tables**
   ``school_dn_public_id_mapping``, ``group_dn_public_id_mapping``,
   ``user_dn_public_id_mapping`` map each entity's ``public_id`` (UUID) to its
   LDAP/UDM ``dn`` (``String(4096)``, unique). They bridge the DN world of
   LDAP/UDM to the Kelvin DB's UUIDs.

.. note::

   The ``UserUDMProperties`` / ``GroupUDMProperties`` / ``SchoolUDMProperties``
   entities described in :doc:`architecture` are **not** separate tables yet.
   UDM properties live inline as a ``udm_properties`` JSON/JSONB
   column on each core table.

Constraints and indexes
^^^^^^^^^^^^^^^^^^^^^^^^

* Integer autoincrement ``id`` primary keys on core / auxiliary tables;
  composite primary keys on the association tables.
* Unique constraints on the natural keys (``name`` / ``email``), on
  ``(record_uid, source_uid)``, on ``school_membership (user_id, school_id)``,
  and on ``primary_user_constraint``.
* B-tree indexes on every ``public_id`` and on the DN mapping columns.
* Foreign keys mostly cascade on delete; ``group.school_id`` uses
  ``NO ACTION``.

Trigram indexes for case-insensitive search
""""""""""""""""""""""""""""""""""""""""""""

Six GIN trigram indexes back the case-insensitive wildcard search
(``ILIKE '%…%'``) on the columns the ``v2`` list endpoints filter:
``user.name``, ``user.firstname``, ``user.lastname``, ``user.email``,
``school.name`` and ``group.name``.

They are created by hand in the migration (not in the ORM metadata), which also
enables the ``pg_trgm`` extension:

.. code-block:: python
   :caption: ``alembic/versions/e49791148e25_init_tables.py``

   op.execute(sa.text("CREATE EXTENSION IF NOT EXISTS pg_trgm"))
   for index_name, table, column in _TRGM_INDEXES:
       op.execute(sa.text(
           f"CREATE INDEX IF NOT EXISTS {index_name} "
           f'ON "{table}" USING gin ("{column}" gin_trgm_ops)'
       ))

Without these indexes, ``ILIKE '%substr%'`` forces sequential scans; with them
PostgreSQL can index-scan.

.. attention::

   The indexes are built with a plain ``CREATE INDEX`` (not
   ``CONCURRENTLY``), which briefly locks writes while the index builds.
   Large deployments might want to switch to ``CREATE INDEX CONCURRENTLY`` inside
   an ``op.get_context().autocommit_block()``.

Migrations
----------

The physical schema is evolved with `Alembic <https://alembic.sqlalchemy.org/>`_.

* There is **no** ``alembic.ini``. The configuration is in ``pyproject.toml``
  under ``[tool.alembic]`` (only ``script_location = "%(here)s/alembic"``).
  Alembic is therefore invoked as ``alembic --config pyproject.toml …``.
* Migration scripts live in ``alembic/versions/``. After the squash into a
  single init revision there is **exactly one** revision
  (``e49791148e25_init_tables.py``, ``down_revision = None``).

.. note::

   The ``v2`` Kelvin DB is not yet deployed in production, so the initial migration
   is still edited in place rather than layered with follow-up revisions.

Generate a migration
^^^^^^^^^^^^^^^^^^^^^^

.. code-block:: shell

   make alembic-migration

This runs
``uv run --env-file .env.alembic alembic revision --autogenerate -m "<message>"``
against the local dev-server database (it depends on the ``kelvin-dev`` docker
compose stack running).
``.env.alembic`` provides the DB coordinates for autogenerate.

.. attention::

   Autogenerate only reproduces what is in the ORM metadata.
   Anything added by hand must be preserved manually across regenerations —
   in the init revision this is the default-role seed insert
   (``op.bulk_insert``) and the ``pg_trgm`` extension plus GIN trigram indexes.

Apply migrations at startup
^^^^^^^^^^^^^^^^^^^^^^^^^^^^

The container entry point runs ``alembic --config pyproject.toml upgrade head``
before starting Gunicorn/Uvicorn (``docker/start-kelvin.sh``).
It first waits for the DB URI file to appear.
Migration can be disabled with ``SKIP_UCSSCHOOL_KELVIN_DB_MIGRATION=true``.

Because all Kelvin instances in a domain share one database, ``env.py`` wraps
migrations in a **PostgreSQL advisory lock** (polling ``pg_try_advisory_lock``
every 2 s, up to a 60 s timeout).
This serializes concurrent ``upgrade head`` attempts from multiple instances.
The advisory lock is a no-op on SQLite.

Rollback
^^^^^^^^

Rollback uses the standard ``alembic --config pyproject.toml downgrade``.
The init revision's ``downgrade()`` drops the trigram indexes first, then all
tables in reverse dependency order.
It deliberately does **not** drop the ``pg_trgm`` extension, because a
dynamic UDM-property-index migration might depend on it and dropping a shared
extension inside a linear migration chain is unsafe.

Queries
-------

The whole point of ``v2`` is fast reads served from the Kelvin DB, so the query
machinery is where the performance-critical paths live.
The query DSL is defined in
``ucsschool-objects/src/ucsschool_objects/core/domain/query.py``
(``Filter``, ``And`` / ``Or`` / ``Not``, ``SortSpec``, ``SearchQuery`` and the
operator set ``EQ, NE, IN, MATCHES, MATCHES_CI, GT, GTE, LT, LTE, CONTAINS``).
The SQLAlchemy adapter translates that tree into SQL in
``.../core/adapters/sqlalchemy/query_filter.py``.

Performance-critical query paths:

#. **Case-insensitive wildcard filtering (ILIKE)** on the name-like columns
   of users, schools and groups — the primary hot path, backed by the pg_trgm
   GIN indexes above. User wildcards (``*``) are translated to SQL ``%`` while
   literal LIKE metacharacters in user input are escaped, so wildcards work
   without allowing LIKE-injection.
#. **Nested-relationship filtering / sorting with joins.** Filtering users by
   ``schools.name``, ``groups.*`` or ``roles.*`` triggers ``LEFT OUTER JOIN`` s
   through ``school_membership``. Because those relations are M:N, the statement
   is wrapped in ``SELECT DISTINCT`` — which is exactly why the JSON columns
   have to be ``jsonb`` on PostgreSQL.
#. **Eager-load shaping to avoid N+1 queries.** Read queries use
   ``selectinload(...).load_only(...)`` to pull only the requested columns of
   the related memberships / schools / groups / roles, gated by a ``LoadSpec``.
   The base ORM relationships are ``lazy="raise"``, so accidentally accessing an
   unloaded relation raises instead of silently emitting a lazy query.
#. **JSON/JSONB filtering on udm_properties**, compiled per-dialect
   (``jsonb_exists`` / ``->>`` on PostgreSQL, ``json_each`` / ``JSON_EXTRACT``
   on SQLite). These columns are **not** covered by the trigram indexes, so
   heavy filtering on ``udm_properties`` is not yet index-accelerated.
