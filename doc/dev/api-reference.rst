.. SPDX-FileCopyrightText: 2026 Univention GmbH
..
.. SPDX-License-Identifier: AGPL-3.0-only

API reference
=============

Kelvin is a FastAPI application (``kelvin-api/ucsschool/kelvin/main.py``)
that mounts two API versions side by side. ``v2`` keeps the ``v1`` endpoints and
data shape but serves reads from the SQL cache and runs no read-hooks
(see :doc:`introduction` and :doc:`architecture`).

This chapter documents the conventions. The authoritative, always-current
contract is the generated OpenAPI specification (see `OpenAPI and interactive
docs`_ below).

Conventions
-----------

URL structure
^^^^^^^^^^^^^

All paths live under ``/ucsschool/kelvin`` (defined in ``constants.py``):

.. list-table::
   :header-rows: 1
   :widths: 2 3

   * - Path
     - Purpose
   * - ``/ucsschool/kelvin/token``
     - obtain an access token
   * - ``/ucsschool/kelvin/v1/<resource>/``
     - version 1 endpoints
   * - ``/ucsschool/kelvin/v2/<resource>/``
     - version 2 endpoints

Resource segments are plural nouns. In ``v2`` the mounted resources are:

.. list-table::
   :header-rows: 1
   :widths: 2 3 3

   * - Resource
     - ``v2`` path
     - Router
   * - Users
     - ``/v2/users``
     - ``routers/v2/user.py``
   * - Schools
     - ``/v2/schools``
     - ``routers/v2/school.py``
   * - School classes
     - ``/v2/classes``
     - ``routers/v2/school_class.py``
   * - Workgroups
     - ``/v2/workgroups``
     - ``routers/v2/workgroup.py``
   * - Roles
     - ``/v2/roles``
     - ``routers/v2/role.py``

.. note::

   Computer rooms / servers / clients exist only under ``v1``; they are not
   mounted into the ``v2`` router.

Every ``v2`` route additionally passes through a ``check_db_compatibility``
dependency that verifies the PostgreSQL schema is at the current Alembic head
(see `Error handling`_).

HTTP methods
^^^^^^^^^^^^

.. list-table::
   :header-rows: 1
   :widths: 2 2 4

   * - Method
     - Success
     - Meaning
   * - ``GET`` (collection)
     - 200
     - search / list with query-parameter filters
   * - ``GET`` (item)
     - 200
     - retrieve one object
   * - ``HEAD`` (item)
     - 200 / 404
     - existence check (schools only)
   * - ``POST``
     - 201
     - create
   * - ``PATCH``
     - 200
     - partial update (JSON body; **not** RFC-6902 JSON-Patch)
   * - ``PUT``
     - 200
     - complete replace
   * - ``DELETE``
     - 204
     - delete

Not every resource supports every method: schools support only
``GET``/``HEAD``/``POST``; roles are read-only (``GET`` only).

Filtering, sorting, pagination
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

* **Filtering** is done with per-attribute query parameters, not a generic
  filter language. For example, users can be filtered by ``school``, ``name``,
  ``firstname``, ``lastname``, ``email``, ``record_uid``, ``source_uid``,
  ``birthday``, ``expiration_date`` and ``disabled``, plus any configured
  mapped UDM property (e.g. ``?uidNumber=12345``). Class and workgroup searches
  **require** the ``school`` parameter.
* **Case-insensitive wildcard search**: ``name``, ``school``, ``firstname``,
  ``lastname`` and ``email`` are matched case-insensitively, and ``*`` acts as a
  wildcard (implemented in ``routers/v2/_filters.py``; backed at the DB layer by
  the pg_trgm trigram indexes — see :doc:`database`). ``record_uid`` and
  ``source_uid`` are matched case-sensitively.
* **Sorting** is fixed: results are returned sorted alphabetically by name;
  there is no client-controllable sort parameter.

.. attention::

   ``v2`` search has **no pagination** — no ``limit`` / ``offset`` / ``page``
   parameters. User search caps results at 10 000 internally and sorts in
   Python. This is a known limitation worth designing around for large result
   sets.

Headers
^^^^^^^

* ``Authorization: Bearer <jwt>`` — required on all resource endpoints.
* ``Content-Type: application/x-www-form-urlencoded`` on the token endpoint;
  ``application/json`` for resource request bodies. Responses are JSON.
* ``X-Request-ID`` — a correlation-id middleware accepts an incoming
  ``X-Request-ID`` (or generates one) and echoes it on responses, including
  error responses. The same id is forwarded to the UDM REST client. See
  :doc:`debugging`.

Authentication
--------------

Access requires a `JSON Web Token (JWT) <https://en.wikipedia.org/wiki/JSON_Web_Token>`_
obtained from ``POST /ucsschool/kelvin/token`` using an OAuth2 password form:

.. code-block:: console

   $ curl -k -X POST https://<fqdn>/ucsschool/kelvin/token \
       -H "Content-Type: application/x-www-form-urlencoded" \
       -d "username=Administrator" -d "password=s3cr3t"

   {"access_token": "eyJ0eXAiOiJKV1Qi...", "token_type": "bearer"}

The token is a self-issued **HS256** JWT (PyJWT) signed with a symmetric secret
read from a file on the app host — there is no external OIDC / Keycloak flow.
It is valid for a configurable time (default 60 minutes; the ``exp`` claim holds
the expiry). See :doc:`architecture` for the authentication and authorization
flow.

Authorization is by membership in two LDAP groups:

``ucsschool-kelvin-rest-api-admins``
   full read and write access.

``ucsschool-kelvin-rest-api-readers``
   read-only access (``GET`` / ``HEAD``).

A user in neither group cannot obtain a usable token. If a user is in both, the
admin group wins. See :doc:`usecases/uc012_read_only_kelvin` and the end-user
`authentication docs
<https://docs.software-univention.de/ucsschool-kelvin-rest-api/authentication-authorization.html>`_.

.. note::

   Authorization failures (e.g. a reader calling a write endpoint) return
   **401 Unauthorized**, not 403. All operations are executed against
   UDM/LDAP as the ``cn=admin`` account regardless of the authenticated user;
   the group membership is the only authorization layer today. A finer-grained,
   Guardian-based permission system is a planned use case
   (:doc:`usecases/uc011_permission_system`).

Error handling
--------------

Status codes
^^^^^^^^^^^^

.. list-table::
   :header-rows: 1
   :widths: 1 4

   * - Code
     - When
   * - ``400``
     - UCS\@school validation error
   * - ``401``
     - authentication failure, inactive user, or authorization denial
   * - ``404``
     - object not found
   * - ``422``
     - request-schema validation error (FastAPI)
   * - ``500``
     - unhandled server error
   * - ``503``
     - (``v2`` only) the DB schema is not at the current Alembic head; the
       instance reports itself deprecated / pending upgrade

Response format
^^^^^^^^^^^^^^^

Error handlers are registered in
``kelvin-api/ucsschool/kelvin/service/exception_handler.py``.

.. attention::

   The error body shape is **not uniform**:

   * UDM errors and FastAPI's own validation errors use a
     ``{"detail": [...]}`` / ``{"detail": "<string>"}`` shape.
   * UCS\@school validation errors and *object not found* use
     ``{"message": "<string>"}``.

   Clients should not assume a single field.

OpenAPI and interactive docs
----------------------------

FastAPI's built-in docs are disabled on the root app; docs are served per
version by a custom implementation (``routers/v1/doc.py``, reused for ``v2``):

.. list-table::
   :header-rows: 1
   :widths: 3 3

   * - URL
     - Content
   * - ``/ucsschool/kelvin/v2/docs``
     - Swagger UI (``v2``)
   * - ``/ucsschool/kelvin/v2/redoc``
     - ReDoc (``v2``)
   * - ``/ucsschool/kelvin/v2/openapi.json``
     - OpenAPI spec (``v2``)
   * - ``/ucsschool/kelvin/docs``
     - combined page with a ``v1`` / ``v2`` selector

The spec is generated at runtime from the routes matching each version prefix
and cached in-process. The Swagger/ReDoc assets are served from a local static
directory (offline-friendly).

Endpoints per resource
----------------------

The available operations and their required group are:

.. list-table::
   :header-rows: 1
   :widths: 2 4 2

   * - Resource
     - Operations
     - Write access
   * - users
     - ``GET`` (search), ``GET``/{username}, ``POST``, ``PATCH``, ``PUT``,
       ``DELETE``
     - admins
   * - schools
     - ``GET`` (search), ``GET``/{name}, ``HEAD``/{name}, ``POST``
     - admins
   * - classes
     - ``GET`` (search, ``school`` required), ``GET``/{school}/{name},
       ``POST``, ``PATCH``, ``PUT``, ``DELETE``
     - admins
   * - workgroups
     - same shape as classes
     - admins
   * - roles
     - ``GET`` (search), ``GET``/{name}
     - — (read-only)

Read operations require membership in the readers *or* admins group; write
operations require the admins group. In ``v2``, write operations are handled by
the ``v1`` handlers, so their behavior matches ``v1`` (including running write
hooks).
