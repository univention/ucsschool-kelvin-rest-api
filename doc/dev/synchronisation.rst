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

* The **Kelvin v2 API** is optimised for fast reads against the Kelvin
  database.
* The **Kelvin database** is a denormalised projection of the authoritative
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

* 🚧 How is the sync service structured?
* 🚧 Which interfaces of Nubus are used? (UDM REST, Provisioning service?)
* 🚧 How is reliability ensured (retry, dead letter queue)?

Events
------

* 🚧 What events are there (e.g., ``user created``, ``group changed``)?
* 🚧 How is the event schema structured? Who produces, who consumes?

Conflict handling
-----------------

* 🚧 What happens when simultaneous changes are made in both directions?
* 🚧 What conflict resolution strategy applies (last write wins, merge, manual)?
* 🚧 How are conflicts logged? How are customers notified?

