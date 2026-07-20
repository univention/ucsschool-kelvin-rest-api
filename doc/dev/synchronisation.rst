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


Why is there a Kelvin connector?
--------------------------------

* The **Kelvin v2 API** is optimized for fast reads against the Kelvin
  database.
* The **Kelvin database** is a denormalized projection of the authoritative
  state in Nubus (UDM / OpenLDAP). It is *not* the source of truth.
* Direct reads from LDAP at API request time would defeat the performance
  goal of v2.
* Writes from Kelvin v1 land in LDAP via UDM REST (legacy path) and must
  still be observable through Kelvin v2 (read-your-writes within v2, and
  cross-version read consistency).
* Direct writes against UDM (bypassing Kelvin, e.g. from administrators
  using the UMC) must also be reflected in the Kelvin database.

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
  (see ``connector.py``, ``consumer.py``, ``sync.py``).
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
and the connector only *writes* to the PostgreSQL cache through the
``ucsschool-objects`` library.

It is structured as three layers (ports-and-adapters), mirroring the rest of the
project:

``connector.py``
   the process entry point (the ``connector`` console script). It reads its
   configuration from the environment, builds the SQLAlchemy engine and
   ``KelvinStorageSessionFactory``, wires up the consumer, and runs
   ``asyncio.run(consumer.consume_loop())``.

``consumer.py``
   event ingestion — ``KelvinConnectorEventHandler`` (relevance filtering and
   dispatch by object type / operation) and ``KelvinConsumerModule`` (the retry
   policy, see `Reliability`_).

``sync.py``
   ``SynchronizationManager`` — the actual cache mutations against the
   ``ucsschool-objects`` domain models, each in its own database transaction.

``models.py``
   Pydantic models validating the UDM event payloads.

Nubus interfaces
^^^^^^^^^^^^^^^^

* The connector consumes the **Nubus Provisioning API** through the
  ``provisioning-consumer-lib``. It long-polls the subscription queue for the
  next message and acknowledges each message after processing.
* It uses **neither** the UDM REST API **nor** LDAP directly.

The subscription itself is created out-of-band (not by the connector process) by
``appcenter/includes/setup-provisioning-subscription.sh``, which registers the
``kelvin-connector`` subscription on the Primary. The topics are subscribed in a
deliberate order — ``container/ou``, then ``groups/group``, then ``users/user``
— so that schools exist before the groups and users that reference them, with
``request_prefill`` enabled to seed the cache with the current state.

.. note::

   The connector only runs on the Primary Directory Node
   (``LDAP_SERVER_TYPE=master``). On other roles its start script simply sleeps.
   In production it runs as its own container (compose service ``provisioning``);
   in the local dev stack it is the ``connector`` service (see
   :doc:`development`).

Reliability
^^^^^^^^^^^

Each event is processed in its own transaction that rolls back on failure, so no
partial writes survive an error. Delivery reliability is handled by
``KelvinConsumerModule``, which overrides the library default (the default
crashes without acknowledging a failed event, turning any deterministically
failing event into a *poison pill* that halts sync forever). The policy, keyed
on the Provisioning ``num_delivered`` counter (default budget: 3 deliveries):

* **Malformed event** (validation error) → dropped and acknowledged immediately
  (a retry cannot fix it).
* **Other error, budget remaining** → logged at ``ERROR`` and re-raised
  *without* acknowledging; the process exits and is restarted by Docker
  (``restart: unless-stopped``), and Provisioning redelivers the event. This
  absorbs transient DB hiccups and event-ordering races.
* **Other error, budget exhausted** → logged at ``CRITICAL`` with the full
  event, then acknowledged (dropped) and the process restarted. A later event
  touching the same object repairs the dropped state (modify-on-missing
  recreates the object).

.. attention::

   There is **no dead-letter queue**. "Dead-letter handling" is effectively
   "log at ``CRITICAL`` and drop after 3 deliveries, relying on future events to
   repair the object". This retry policy is a stopgap intended to move into the
   provisioning-consumer library upstream.

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
* skips unsyncable groups (per-OU ``Domain Users``, the role groups, ``ouadmins``).

Irrelevant events are acknowledged and skipped.

Event schema
^^^^^^^^^^^^

The payload models live in ``kelvin-connector/src/kelvin_connector/models.py``
(``UserProperties``, ``GroupProperties``, ``SchoolProperties``,
``HostGroupProperties``). Objects are identified by their
``univentionObjectIdentifier`` (a UUID), which becomes the cache's ``public_id``.
Each event carries a timestamp and a ``sequence_number`` plus the ``new`` and
``old`` object state. Deletes use a permissive payload that only requires the
identifier, because a deleted object's remaining fields may be malformed.

Two details worth knowing:

* The full UDM properties are stored verbatim except for a denylist
  (``jpegPhoto``, ``password``), so a change to the read-time mapped-property
  configuration needs no resync.
* References (group members, legal wards / guardians, e-mail senders) are
  resolved through a persisted **DN → public_id mapping**. An unresolved
  reference is *skipped with a log line*, not treated as an error — the link is
  established when the referenced object's own event arrives.

Conflict handling
-----------------

There is **no bidirectional conflict resolution, by design**. The model is
strictly one-directional: LDAP / UDM is the single source of truth, and the
connector only projects that state into the read cache.

Consequently the effective strategy is **"LDAP always wins" / last-event-wins
per object**, ordered by the Provisioning ``sequence_number``. When applying a
modify, the connector replaces the object's reference collections wholesale from
the event's full state rather than merging. Simultaneous changes therefore do
not produce a merge or a conflict record: the latest authoritative event simply
overwrites the cached row.

.. note::

   Because there is no conflict, there is no conflict detection, no conflict log,
   and no customer notification. If a cache row ever diverges from LDAP, the
   remedy is a fresh event for that object (or a re-prefill of the subscription),
   not a conflict-resolution workflow.
