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
  (see ``ccf_launcher.py``, ``connector.py``, ``tasks.py``, ``sync.py``).
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
or LDAP: the Provisioning events carry the full ``new`` / ``old`` object state,
and the connector only *writes* to the Kelvin DB through the
``ucsschool-objects`` library.

The connector runs on the Common Connector Framework (CCF),
a Rust binary from the ``common-connector-framework`` submodule.
The CCF fetches the Provisioning messages, keeps them in its own task queue
and calls the connector's Python callback once per task.
The connector code is structured in layers (ports-and-adapters),
mirroring the rest of the project:

``ccf_launcher.py``
   the process entry point (``python -m kelvin_connector.ccf_launcher``).
   It derives the CCF configuration from the connector's one
   (subscription credentials, Kelvin DB settings)
   and replaces itself with the ``ccf`` binary.

``ccf_callback.py`` and ``connector.py``
   the callback module the CCF imports.
   On import, ``build_runner()`` checks the configuration,
   builds the SQLAlchemy engine and the ``SynchronizationManager``,
   and starts the asyncio loop thread (``loop_thread.py``).
   A configuration error stops the CCF before it fetches the first message.

``tasks.py``
   task processing:
   the relevance filter (``is_relevant``), which runs first on the CCF worker thread,
   the dispatch by object type and operation on the asyncio loop thread,
   and the mapping of the result onto the CCF's ``CallbackResult``
   (see `Reliability`_).

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

Nubus interfaces
^^^^^^^^^^^^^^^^

* The connector consumes the **Nubus Provisioning API** through the CCF.
  The CCF long-polls the subscription queue,
  stores each message as a task in its own tables
  and acknowledges the message once the task is stored, before it is processed.
  The tables live in the schema ``ccf`` of the Kelvin DB,
  created by an Alembic revision; the CCF migrates them itself.
* It uses **neither** the UDM REST API **nor** LDAP directly.

The subscription itself is created out-of-band (not by the connector process) by
``appcenter/includes/setup-provisioning-subscription.sh``, which registers the
``kelvin-connector`` subscription on the Primary. The topics are subscribed in a
deliberate order — ``container/ou``, then ``groups/group``, then ``users/user``
— so that schools exist before the groups and users that reference them, with
``request_prefill`` enabled to seed the Kelvin DB with the current state.

.. note::

   The connector only runs on the Primary Directory Node
   (``LDAP_SERVER_TYPE=master``). On other roles its start script sleeps.
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
  The task is removed, the CCF keeps no state for the object.
* **Processed** → ``SuccessCreated``, ``SuccessModified`` or ``SuccessDeleted``.
  The CCF also removes earlier morgue entries of the object.
* **Malformed event** (validation error) → ``PermanentFailure``.
  The task moves to the CCF's ``morgue`` table at once,
  with the failing fields and messages but without their values.
* **Other error or timeout** → ``Failure``.
  The CCF retries the task with a growing delay
  and moves it to the morgue after ``MAX_ALLOWED_ERRORS`` failures
  (default 3, set by ``ccf_launcher.py``).
  A later event touching the same object replaces the task
  and repairs the state (modify-on-missing recreates the object).

.. attention::

   The morgue is not visible through the Kelvin API yet;
   failed events show up in the connector log and in the ``ccf.morgue`` table.

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
Each event carries a timestamp and a ``sequence_number`` plus the ``new`` and
``old`` object state. Deletes use a permissive payload that only requires the
identifier, because a deleted object's remaining fields may be malformed.

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
