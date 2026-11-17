.. SPDX-FileCopyrightText: 2026 Univention GmbH
..
.. SPDX-License-Identifier: AGPL-3.0-only

Synchronization to Nubus
========================

The *Kelvin Connector* is the dedicated service that keeps the Kelvin v2
database (``ucsschool-kelvin-rest-api`` PostgreSQL database) consistent with
the authoritative state in Nubus / UDM / LDAP.

It is a separate Python package (``kelvin-connector``, see
``kelvin-connector/``) that runs as its own process next to the Kelvin API.
It does not live inside the FastAPI application.


Why is there a Kelvin Connector?
--------------------------------

* The **Kelvin v2 API** is optimized for fast reads against the Kelvin
  database.
* The **Kelvin database** is a denormalized projection of the authoritative
  state in Nubus (UDM / OpenLDAP). It is *not* the source of truth.
* Direct reads from LDAP at API request time defeats the performance
  goal of v2.
* Writes from Kelvin v1 land in LDAP through UDM REST (legacy path) and must
  still be observable through Kelvin v2 (read-your-writes within v2, and
  cross-version read consistency).
* Direct writes against UDM (bypassing Kelvin, for example from administrators
  using the Univention Management Console (UMC)) must also be reflected in the Kelvin database.

The connector closes this loop by consuming a stream of LDAP change events
from the Provisioning API and applying them to the Kelvin database.


Components involved
-------------------

.. mermaid::

   sequenceDiagram
       actor v1Client as Kelvin or UMC
       actor Client as HTTP Client
       participant UDM as UDM REST
       participant LDAP as OpenLDAP
       participant Provisioning as Nubus Provisioning Service
       participant Connector as Kelvin Connector
       participant KelvinAPI as Kelvin v2 API (FastAPI)
       participant KelvinDB as Kelvin DB<br/>(PostgreSQL)

       Note over v1Client,LDAP: v1/v2 write path / direct write path in UMC
       v1Client->>UDM: write request
       UDM->>LDAP: persist
       LDAP-->>Provisioning: change event (async)
       Connector->>Provisioning: pull next event
       Connector->>KelvinDB: upsert/delete<br>if valid event
       Connector->>Provisioning: acknowledge event

       Note over Client,KelvinDB: v2 read path
       Client->>KelvinAPI: GET /v2/...
       KelvinAPI->>KelvinDB: read
       KelvinDB-->>KelvinAPI: row
       KelvinAPI-->>Client: 200 OK

The relevant code locations are:

* Connector source: ``kelvin-connector/src/kelvin_connector/``
  (see ``ccf_callback.py``, ``connector.py``, ``tasks.py``, ``sync.py``).
* Storage session and domain models:
  ``ucsschool-objects/src/ucsschool_objects/``
  (see ``core/domain/``, ``core/adapters/sqlalchemy/``,
  ``database_models.py``).
* Domain port used by the connector:
  ``KelvinStorageSession`` / ``KelvinStorageSessionFactory`` /
  ``Manager[T]`` (in ``ucsschool_objects.core.domain.ports``).


Sync architecture
-----------------

The connector is a **pure event → SQL projector**. It never reads back from UDM
or LDAP: the Provisioning events carry the full ``new`` object state, a delete
needs only the object ID and DN, and the connector only *writes* to the Kelvin DB through the
``ucsschool-objects`` library.

The connector runs on the Common Connector Framework (CCF).
The CCF fetches the Provisioning messages, keeps them in its own task queue
and calls the connector's Python callback once per task.
The connector image (Docker target ``connector-prod``) is the CCF's
``ccf-python-postgres`` image plus the callback:
the sources of ``kelvin-connector`` and ``ucsschool-objects``
and their third-party dependencies, installed for the image's Python.
The Dockerfile sets the CCF variables that belong to the image
(``PYTHON_CALLBACK``, ``PYTHON_CALLBACK_PATH``, ``CCF_TEMPLATES_DIR``,
``MAX_ALLOWED_ERRORS``, and ``CCF_TITLE``, ``CCF_DESCRIPTION``, ``CCF_VERSION``
for ``kelvin-connector --help`` and ``kelvin-connector --version``);
the deployment provides ``PROVISIONING_HOSTNAME``, ``PROVISIONING_NAME``,
``PROVISIONING_PASSWORD``, ``DATABASE_URL``
(the Kelvin DB with ``options=-csearch_path=ccf``)
and ``UNIQUE_OWNER_ID``,
plus ``LDAP_SERVER_TYPE`` and the ``UCSSCHOOL_KELVIN_DB_*`` settings for the callback.

``UNIQUE_OWNER_ID`` binds the ``ccf`` schema to one connector:
the first connector that starts records its ID as the owner,
and a connector with another ID (or none) refuses to process the tasks
(its setup fails with ``Disabled: …`` and is retried).
The App sets it to the UCR variable ``hostname``.
After the host was renamed, or to hand the schema over to another host's connector,
stop the old connector and run ``kelvin-connector enable --force`` in the new one.

The CCF verifies the TLS certificates of the Provisioning API and of PostgreSQL
against the files named by ``SSL_CERT_FILE`` and ``SSL_CERT_DIR``.
The CCF image sets ``SSL_CERT_DIR`` to its own, empty directory ``/etc/ccf/ca/``.
The App mounts the host's ``/etc/ssl/certs`` into the container, as for the Kelvin container,
and sets ``SSL_CERT_FILE=/etc/ssl/certs/ca-certificates.crt`` and ``SSL_CERT_DIR=/etc/ssl/certs/``,
so the connector trusts the UCS CA and every CA added on the host.

In the App, ``PROVISIONING_PASSWORD`` and ``DATABASE_URL`` come from the environment file
``/var/lib/univention-appcenter/apps/ucsschool-kelvin-rest-api/conf/provisioning/connector.env``.
The App Center starts the containers before ``configure_host`` writes the Kelvin DB credentials
and before the join script creates the subscription,
so the preinst creates the file empty
and the join script (``write_connector_env``) fills it and recreates only the connector container.

The CCF never exits on a setup error:
it logs the error and retries the whole setup every ``SETUP_RETRY_INTERVAL``
seconds (default 30), so the container stays up and can be inspected
while the configuration is fixed.
The connector code is structured in layers (ports-and-adapters),
mirroring the rest of the project:

``ccf_callback.py`` and ``connector.py``
   the callback module the CCF imports.
   Importing it only registers its functions with ``ccf.register``
   (the CCF does not retry a failed import, so nothing at import time may fail).
   The setup function, ``build_connector()``, checks the configuration
   (the connector only runs on the Primary, ``LDAP_SERVER_TYPE=master``),
   waits for Kelvin (``KELVIN_HEALTH_URL``, default ``http://api:8911/health``:
   Kelvin migrates the Kelvin DB on start),
   builds the SQLAlchemy engine and the ``SynchronizationManager``,
   and starts the asyncio loop thread (``loop_thread.py``) last.
   If any of these fails, the CCF calls the setup function again after ``SETUP_RETRY_INTERVAL`` seconds
   and fetches no message before it succeeded;
   outside the Primary it keeps failing on purpose, so the connector idles.
   The shutdown function closes the engine's connections and stops the loop thread
   after the last task committed.
   ``CallbackResult``, ``CcfDatabaseError``, ``Task`` and ``Consumer``
   come from the CCF's ``ccf`` package,
   which the CCF image embeds and the dev dependencies install for the unit tests.

``tasks.py``
   task processing:
   the relevance filter (``is_relevant``), which runs first on the CCF worker thread,
   the dispatch by object type and operation on the asyncio loop thread,
   and the mapping of the result onto the CCF's ``CallbackResult``
   (see `Reliability`_).

``ccf_templates/provisioning/``
   CCF provisioning templates that turn each message into the task's ``attrs``:
   ``{"dn": <DN as sent>, "properties": <new.properties>}``.
   The CCF's own ``task["dn"]`` is normalized (converted to lower case),
   but the Kelvin DB's DN mapping needs the DN as sent.
   A delete arrives with empty ``attrs``.

The callback uses only the CCF's own state, never the raw message:

* Empty ``attrs`` is a delete.
  Otherwise the CCF's ``old`` table (``consumer.get_old``) tells a create
  (no ``old`` row) from a modify (an ``old`` row).
* On success, the callback leaves only a few identifying properties
  in ``task["attrs"]`` (``univentionObjectIdentifier``, ``name``, ``username``),
  which the CCF stores as the object's ``old`` row.
* A delete does not use the ``old`` table.
  Objects synced before the connector ran on the CCF have no ``old`` row
  (an upgrade keeps the subscription),
  and neither do objects whose create task was replaced by the delete
  or ended in the morgue.
  The task's ``obj_id`` is the object's ``univentionObjectIdentifier``,
  so users, groups and schools are deleted by it;
  deleting an object that is not in the Kelvin DB is a no-op.
  A DC host group is not an object in the Kelvin DB:
  it is recognized by the leaf ``cn`` of the task's DN,
  which is its name and identifies the school whose servers are cleared.
  The CCF's DN is normalized to lower case,
  so the host group name is matched case-insensitively.

``sync.py``
   ``SynchronizationManager``: the actual Kelvin DB mutations against the
   ``ucsschool-objects`` domain models, each in its own database transaction.

``models.py``
   Pydantic models validating the UDM event payloads.

The CCF calls the callback synchronously,
while the Kelvin DB is accessed through async SQLAlchemy.
Its pooled connections are bound to the event loop that opened them,
so all tasks run on one long-lived loop in a daemon thread
(``AsyncioLoopThread``).
A task that does not finish within ``KELVIN_CONNECTOR_TASK_TIMEOUT``
(default 300 seconds) is cancelled, which rolls back its transaction.

The connector logs through Python's standard ``logging``.
The CCF routes the root logger into its own log (Nubus format, one line per event)
and sets the level from its ``LOG_LEVEL`` (default ``info``).
On its own worker threads the CCF adds the task's request ID itself;
lines logged on the asyncio loop thread get it from a context variable
(``log.py``).

Nubus interfaces
^^^^^^^^^^^^^^^^

* The connector consumes the **Nubus Provisioning API** through the CCF.
  The CCF long-polls the subscription queue,
  stores each message as a task in its own tables
  and acknowledges the message once the task is stored, before it is processed.
  The tables live in the schema ``ccf`` of the Kelvin DB;
  the CCF creates the schema and migrates its tables itself.
* It uses **neither** the UDM REST API **nor** LDAP directly.

The subscription itself is created out-of-band (not by the connector process) by
``appcenter/includes/setup-provisioning-subscription.sh``, which registers the
``kelvin-connector`` subscription on the Primary. The topics are subscribed in a
deliberate order — ``container/ou``, then ``groups/group``, then ``users/user``
— so that schools exist before the groups and users that reference them, with
``request_prefill`` enabled to seed the Kelvin DB with the current state.

.. note::

   The connector only runs on the Primary Directory Node
   (``LDAP_SERVER_TYPE=master``). On other roles the callback setup fails
   and the CCF keeps retrying it, so the container stays up but idle.
   In production it runs as its own container (compose service ``provisioning``);
   in the local dev stack it is the ``connector`` service (see
   :doc:`development`).

Reliability
^^^^^^^^^^^

Each event is processed in its own transaction that rolls back on failure,
so no partial writes survive an error.
The CCF keeps one pending task per object:
a newer message for the same object replaces a pending task.
The callback reports one result per task:

* **Irrelevant object** (see the relevance filter) → ``SuccessSkipped``.
  The task is removed; an existing ``old`` row is kept.
* **Processed** → ``SuccessCreated``, ``SuccessModified`` or ``SuccessDeleted``.
  The CCF also removes earlier morgue entries of the object.
* **Failed read of the CCF's own database** (``consumer.get_old`` raises the
  ``ccf.CcfDatabaseError``) → the exception escapes the callback.
  The CCF retries the task right away without counting an error,
  so an outage of the database never sends a task to the morgue.
* **Other error or timeout** → ``Failure``.
  A validation error reports the failing fields and messages
  but not their values.
  The CCF retries the task with a growing delay
  and moves it to the morgue after ``MAX_ALLOWED_ERRORS`` failures
  (default 3, set in the connector image).
  A later event touching the same object replaces the task
  and repairs the state (modify-on-missing recreates the object).

.. attention::

   The morgue is not visible through the Kelvin API yet;
   failed events show up in the connector log and in the ``ccf.morgue`` table.
   The ``kelvin-connector`` command in the connector container
   (the CCF binary ``ccf`` under the connector's name) inspects and repairs it,
   e.g. ``docker exec <container> kelvin-connector summarize-morgue``,
   ``kelvin-connector show-item --obj-id <uuid>``
   or ``kelvin-connector retry-from-morgue --obj-id <uuid>``
   (``kelvin-connector --help`` lists all commands).
   ``kelvin-connector healthcheck`` is the image's Docker health check:
   it fails when the connector has shown no sign of life for ``HEALTHCHECK_MAX_AGE`` seconds (default 600).

Events
------

The producer is the Nubus Provisioning service (emitting an event for every UDM
change in LDAP); the sole consumer is this connector. Create / modify / delete
are handled for three object types, plus a special case:

.. list-table::
   :header-rows: 1
   :widths: 2 2 4

   * - Topic
     - Object
     - Handling
   * - ``container/ou``
     - School / OU
     - ``handle_school_{create,modify,delete}``
   * - ``groups/group``
     - School class / workgroup
     - ``handle_group_{create,modify,delete}``
   * - ``groups/group``
     - DC host groups (``OU…-DC-Edukativnetz`` / ``…-Verwaltungsnetz``)
     - ``handle_host_group_*`` — sets a school's
       ``educational_servers`` / ``administrative_servers``
   * - ``users/user``
     - User
     - ``handle_user_{create,modify,delete}``

Not everything is cached. The relevance filter requires a ``ucsschoolRole`` and:

* skips **exam users**,
* skips groups that are neither school classes, workgroups, nor the DC host
  groups above,
* skips groups that can't be synced (per-OU ``Domain Users``, the role groups, ``ouadmins``).

Irrelevant events are acknowledged and skipped.

Event schema
^^^^^^^^^^^^

The payload models live in ``kelvin-connector/src/kelvin_connector/models.py``
(``UserProperties``, ``GroupProperties``, ``SchoolProperties``,
``HostGroupProperties``). Objects are identified by their
``univentionObjectIdentifier`` (a UUID), which becomes the Kelvin DB's ``public_id``.
A create or modify carries the object's new state (DN as sent and the UDM
properties); a delete is built from the task's object ID and DN (see
`Sync architecture`_), in a payload that only requires the identifier.

Two details worth knowing:

* The full UDM properties are stored verbatim except for a denylist
  (``jpegPhoto``, ``password``), so a change to the read-time mapped-property
  configuration needs no resync.
* References (group members, legal wards / guardians, email senders) are
  resolved through a persisted **DN → public_id mapping**. An unresolved
  reference is *skipped with a log line*, not treated as an error — the link is
  established when the referenced object's own event arrives.

Conflict handling
-----------------

There is **no bidirectional conflict resolution, by design**. The model is
strictly one-directional: LDAP / UDM is the single source of truth, and the
connector only projects that state into the Kelvin DB.

Consequently the effective strategy is **"LDAP always wins" / last-event-wins
per object**, ordered by the Provisioning ``sequence_number``. When applying a
modify, the connector replaces the object's reference collections wholesale from
the event's full state rather than merging. Simultaneous changes therefore do
not produce a merge or a conflict record: the latest authoritative event
overwrites the row in the Kelvin DB.

.. note::

   Because there is no conflict, there is no conflict detection, no conflict log,
   and no customer notification. If a Kelvin DB row ever diverges from LDAP, the
   remedy is a fresh event for that object (or a re-prefill of the subscription),
   not a conflict-resolution workflow.
