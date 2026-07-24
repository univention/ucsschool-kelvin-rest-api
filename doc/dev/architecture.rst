.. SPDX-FileCopyrightText: 2026 Univention GmbH
..
.. SPDX-License-Identifier: AGPL-3.0-only

Architecture
============

System overview
---------------

Kelvin is a single FastAPI application that mounts two API versions. ``v1``
reads and writes through the UDM REST API (and occasionally LDAP directly).
``v2`` keeps the ``v1`` write path but serves reads and searches from the local
Kelvin DB, a PostgreSQL read cache. The Kelvin DB is filled by two writers: synchronously by Kelvin's
own write path, and asynchronously by the *Kelvin Connector*, which applies
LDAP change events from the Nubus Provisioning service (see
:doc:`synchronisation`).

.. mermaid::
   :caption: Container view of Kelvin ``v2``.

   graph TB
       Client["HTTP client"]
       subgraph Kelvin["Kelvin app host (Primary / Backup)"]
           API["Kelvin REST API<br/>(FastAPI, kelvin-api/)"]
           Connector["Kelvin Connector<br/>(kelvin-connector/)"]
           DB[("Kelvin DB<br/>read cache")]
       end
       subgraph Nubus["Nubus"]
           UDM["UDM REST API"]
           LDAP[("OpenLDAP")]
           Prov["Provisioning<br/>service"]
       end

       Client -->|"HTTPS / JSON"| API
       API -->|"write path (v1 + v2 writes)"| UDM
       API -->|"read path (v2)"| DB
       API -.->|"direct read / auth bind"| LDAP
       UDM --> LDAP
       LDAP -->|"change events"| Prov
       Prov -->|"consume events"| Connector
       Connector -->|"upsert / delete"| DB

External systems involved:

* **UDM REST API** (Nubus) — the write path; also used by ``v2`` write
  operations.
* **OpenLDAP** (Nubus) — the source of truth; accessed directly for
  authentication binds, group-membership lookups, and some attributes.
* **Nubus Provisioning service** — the event source the Kelvin Connector
  consumes.
* **PostgreSQL** — the ``v2`` Kelvin DB, a read cache (see :doc:`database`).

Authentication uses a self-issued HS256 JWT verified against OpenLDAP; there is
no external OpenID Connect (OIDC) / Keycloak dependency, and the Guardian-based permission
system is only a planned use case (:doc:`usecases/uc011_permission_system`).

Components
----------

Within the FastAPI application the layers are:

Routers (``kelvin-api/ucsschool/kelvin/routers/``)
   HTTP endpoints, request/response models, and query-parameter parsing, split
   into ``v1/`` and ``v2/`` subpackages.

Service (``kelvin-api/ucsschool/kelvin/service/``)
   Cross-cutting concerns: the ASGI lifespan, middleware (correlation id,
   timing), exception handlers, and request dependencies (auth, storage-session,
   DB-compatibility check).

Domain / persistence (``ucsschool-objects``)
   The ``v2`` read path. A ports-and-adapters library whose SQLAlchemy adapter
   maps UCS\@school objects to the Kelvin DB. The FastAPI app obtains a
   storage-session factory from ``app.state`` (populated by the lifespan) and
   uses per-entity managers to query it.

UCS\@school libraries (``ucs-school-lib``, ``ucs-school-import``)
   The write path (and the whole ``v1`` path). They talk to the UDM REST API
   and persist to OpenLDAP.

Data flow for a typical request:

* **A v2 read** (``GET``/``HEAD``): router → auth + DB-compatibility
  dependency → storage session → SQLAlchemy query against PostgreSQL → the
  ``ucsschool-objects`` domain object is transformed into the ``v1`` response
  shape and returned. The
  UCS\@school libraries are not involved, so read-hooks do not run.
* **A v2 write** (``POST``/``PATCH``/``PUT``/``DELETE``): the ``v2`` router
  reuses the ``v1`` handler, which goes through the UCS\@school import library →
  UDM REST API → OpenLDAP, and stores the response in the Kelvin DB before
  returning.

Data model
----------

Entities
^^^^^^^^

Tables in this section have been generated from the ``SQLAlchemy`` models unless otherwise noted.

User
""""

   A user represents a person and their account.

.. include:: architecture/user-attributes.rst

.. note::

   The Kelvin API requires ``source_uid`` and ``record_uid``. When a user is provisioned by the Kelvin Connector, however,
   it is possible that they won't have a value for these two attributes. In that case, ``"nubus"`` is the ``source_uid``
   and ``record_uid`` is equal to the ``univentionObjectIdentifier``/``public_id``.

.. include:: architecture/user-relations.rst


.. .. include:: architecture/user-constraints.rst



Role
""""

   A role, for example teacher, student, legal guardian, or admin.

.. include:: architecture/role-attributes.rst

.. include:: architecture/role-relations.rst

.. note::

   The assignment of a role to a group means that the members of that group inherit the role.
   The details of this relationship are not yet worked out and are not documented here.

.. attention::

   A role does not have a corresponding object in the Nubus database. Roles in Nubus are saved as strings
   on the ``guardianRole`` multi-value attribute. Thus, the ``public_id`` does not correspond to any
   ``univentionObjectIdentifier`` in Nubus. However, the ``public_id`` might refer to the identifier of a
   role in the Guardian application.

School
""""""

.. include:: architecture/school-attributes.rst

.. include:: architecture/school-relations.rst


SchoolMembership
""""""""""""""""

.. include:: architecture/schoolmembership-attributes.rst

.. include:: architecture/schoolmembership-relations.rst

.. note::

   1. A user must have at least one school membership.
   2. A user must have exactly one primary school membership.
   3. A user must have at least one role in a school they are a member of.

   These constraints are not yet completely enforced in this model:
   A user without a school can be created; this must be prevented in the application
   layer.


Group
"""""

.. include:: architecture/group-attributes.rst

.. include:: architecture/group-relations.rst


UserUDMProperties
"""""""""""""""""

Not yet implemented in ``SQLAlchemy``.

.. include:: architecture/user-udm-properties-attributes.rst

.. include:: architecture/user-udm-properties-relations.rst


GroupUDMProperties
""""""""""""""""""

Not yet implemented in ``SQLAlchemy``.

.. include:: architecture/group-udm-properties-attributes.rst

.. include:: architecture/group-udm-properties-relations.rst


SchoolUDMProperties
"""""""""""""""""""

Not yet implemented in ``SQLAlchemy``.

.. include:: architecture/school-udm-properties-attributes.rst

.. include:: architecture/school-udm-properties-relations.rst


Entity-relationship diagram
^^^^^^^^^^^^^^^^^^^^^^^^^^^

.. mermaid:: architecture/er.mmd

.. attention::

   Omitted relations to simplify the diagram:

   * All relations related to UDM properties

Localization
^^^^^^^^^^^^

Localized attributes are stored in a JSON object, where the keys are the language codes (ISO 639) and the values are the localized strings.

.. code:: json

   {
     "en": "English",
     "de": "Deutsch"
   }

Future entities
^^^^^^^^^^^^^^^

.. attention::

   The following entities are suggestions for future development.

SchoolAuthority
"""""""""""""""

   A school authority manages zero or more schools.

.. list-table:: Attributes
   :header-rows: 1
   :widths: 1 1 1 3 3

   * - Name
     - Type
     - Default
     - Constraints
     - Description
   * - ``public_id``
     - ``uuid``
     - Generated
     - ``Unique``, ``not NULL``
     -
   * - ``display_name``
     - ``json``
     - ``{}``
     - ``not NULL``
     - Localized display name of the school authority

.. list-table:: Relations from the perspective of entity ``SchoolAuthority``
   :header-rows: 1
   :widths: 1 1 2

   * - Entity
     - Cardinality
     - Relationship
   * - School
     - 1:N
     - A school authority **administers** N schools.

.. note::

   * A school authority does not have a direct relation to an object in UDM.

UserRelation
""""""""""""

See `Issue #208 <https://git.knut.univention.de/univention/dev/education/ucsschool-kelvin-rest-api/-/work_items/208>`_

   A user has a relation of a certain type to another user.

.. note::

   This suggestion for a relation has some shortcomings: Only for parent-child type relationships
   with no other constraints, like one-to-one etc. Additionally, it seems to be complicated to implement
   with SQLAlchemy. Another variant is to have additional association tables for each new relation.

.. list-table:: Attributes of ``UserRelation``
   :header-rows: 1
   :widths: 1 1 1 3 3

   * - Name
     - Type
     - Default
     - Constraints
     - Description
   * - ``relation_type``
     - ``enum``
     -
     - ``Unique`` via ``enum``
     -

.. list-table:: Relations to entities from the perspective of ``UserRelation``
   :header-rows: 1
   :widths: 1 1 2

   * - Entity
     - Cardinality
     - Relationship
   * - User
     - 1:1
     - A user relation **contains** exactly one parent
   * - User
     - 1:1
     - A user relation **contains** exactly one child

Architecture of authentication and authorization
------------------------------------------------

Authentication is a self-issued **JWT bearer token** flow (OAuth 2.0 password
grant). There is no external OIDC / Keycloak provider: Kelvin verifies the
credentials against OpenLDAP itself and signs its own token.

* The client posts credentials to ``POST /ucsschool/kelvin/token``.
* Kelvin looks up the user's DN and **binds to OpenLDAP with the supplied
  credentials** to verify the password.
* On success it issues an **HS256** JWT (PyJWT) signed with a symmetric secret
  read from a file on the app host. The token embeds the username, the
  ``kelvin_admin`` / ``kelvin_reader`` flags, the user's schools and roles, and
  an ``exp`` (default 60 minutes).
* On every subsequent request the ``Authorization: Bearer`` token is decoded
  with the same secret, and the user is re-loaded from LDAP.

Authorization is by membership in two LDAP groups, checked at token-issue time:

``ucsschool-kelvin-rest-api-admins``
   full read and write access (``kelvin_admin``).

``ucsschool-kelvin-rest-api-readers``
   read-only access — ``GET`` / ``HEAD`` (``kelvin_reader``).

A user in neither group cannot obtain a usable token; a reader calling a write
endpoint is rejected. Denials return **401** (not 403). Regardless of the
authenticated user, Kelvin performs its UDM/LDAP operations as the ``cn=admin``
account — the group membership is the only authorization layer. A
finer-grained, Guardian-based permission model is a planned use case
(:doc:`usecases/uc011_permission_system`).

.. mermaid::

   sequenceDiagram
       actor Client as HTTP Client
       participant Kelvin as Kelvin REST API
       participant LDAP as OpenLDAP

       Client->>Kelvin: POST /token (username, password)
       Kelvin->>LDAP: bind with credentials + read group membership
       LDAP-->>Kelvin: ok (admin / reader flags)
       Kelvin-->>Client: 200 {access_token: <HS256 JWT>}

       Client->>Kelvin: GET /v2/... (Authorization: Bearer <jwt>)
       Kelvin->>Kelvin: decode + verify JWT, check group
       Kelvin-->>Client: 200 OK / 401 Unauthorized

Relevant code: ``kelvin-api/ucsschool/kelvin/token_auth.py`` (JWT issue/verify,
dependency gates ``get_kelvin_admin`` / ``get_kelvin_reader``) and
``ldap.py`` (credential bind, group lookup). See also :doc:`api-reference`.

Interfaces
----------

Kelvin talks to the following external systems:

.. list-table::
   :header-rows: 1
   :widths: 2 2 3

   * - System
     - Protocol / format
     - Role
   * - UDM REST API (Nubus)
     - HTTPS / JSON
     - the write path; ``v2`` write operations. Kelvin acts as ``cn=admin``.
   * - OpenLDAP (Nubus)
     - LDAP (``ldap3`` / ``uldap3``)
     - authentication binds, group-membership lookups, and direct reads for
       attributes not exposed by UDM.
   * - Nubus Provisioning service
     - HTTPS / JSON (provisioning-consumer library)
     - the event source consumed by the Kelvin Connector.
   * - PostgreSQL
     - SQL (async SQLAlchemy + psycopg)
     - the ``v2`` Kelvin DB, a read cache.

The client-facing interface is HTTPS/JSON, documented via the generated OpenAPI
specification (see :doc:`api-reference`).
