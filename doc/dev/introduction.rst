.. SPDX-FileCopyrightText: 2026 Univention GmbH
..
.. SPDX-License-Identifier: AGPL-3.0-only

Introduction
============

The *UCS\@school Kelvin REST API* provides HTTP endpoints to create and manage UCS\@school domain objects like school users, school classes, schools (OUs) and computer rooms.

This is the **developer** documentation.
For usage and configuration, see the
`end-user documentation <https://docs.software-univention.de/ucsschool-kelvin-rest-api/>`_.

Project goal
------------

Kelvin is the programmatic entry point for managing UCS\@school data. The same
objects can also be managed through the UMC web interface and a Python API, but
Kelvin is the stable HTTP interface intended for automation and integration.

It solves two problems:

* It exposes UCS\@school domain objects (users, school classes, workgroups,
  schools, roles, computer rooms) over a versioned, documented REST API, so
  external systems — school information systems, provisioning tools, the
  UCS\@school import, and custom clients — can read and write them without
  talking to LDAP or UDM directly.
* In ``v2`` it additionally solves the *read-performance* problem: reads and
  searches are served from a local SQL cache instead of round-tripping to
  LDAP / the UDM REST API on every request.

Typical clients / consumers are:

* the official `Python client <https://kelvin-rest-api-client.readthedocs.io/en/latest/>`_,
* the UCS\@school import mechanism and UMC modules acting as HTTP clients,
* external school management / information systems (SIS),
* monitoring or reporting systems using read-only access.

See :doc:`usecases` for the detailed use cases and :doc:`architecture` for how
the pieces fit together.

Versions
--------

``v1``
   A thin frontend over the UCS\@school and UCS\@school import libraries, which
   read and write through the UDM REST API (and occasionally LDAP directly).
   Every request hits UDM / LDAP.

``v2``
   Keeps the ``v1`` endpoints and data representation, but adds an SQL **read
   cache** and drops support for read-hooks. Writes still go through the ``v1``
   path (UCS\@school import → UDM REST API); read and search requests are served
   from the cache. Because the read path no longer runs the UCS\@school
   libraries, their **read-hooks are not executed** in ``v2`` — a breaking
   behavioral change even though the data shape stays ``v1``-compatible.

   The cache is kept eventually consistent with LDAP by a companion service, the
   *Kelvin Connector* (see :doc:`synchronisation`).

Quick start
-----------

To run Kelvin locally you need ``uv``, Docker, and access to a running UCS host
(for the UDM REST API and credentials). Then:

.. code-block:: shell

   uv sync
   make fetch-vm-data TARGET="<IP/FQDN of a UCS host>"
   make dev-server

The API is then available at ``http://127.0.0.1:8911/ucsschool/kelvin/``.
See :doc:`development` for the full setup, project layout, and testing.

First request
^^^^^^^^^^^^^

All resource endpoints require a bearer token. Retrieve one from the token
endpoint (OAuth2 password form), then call a resource:

.. code-block:: console

   $ TOKEN=$(curl -s -k -X POST http://127.0.0.1:8911/ucsschool/kelvin/token \
       -H "Content-Type: application/x-www-form-urlencoded" \
       -d "username=Administrator" -d "password=s3cr3t" \
       | python3 -c "import sys, json; print(json.load(sys.stdin)['access_token'])")

   $ curl -s -k http://127.0.0.1:8911/ucsschool/kelvin/v2/schools/ \
       -H "Authorization: Bearer $TOKEN"

Interactive API documentation (Swagger UI / ReDoc) is served per version at
``.../ucsschool/kelvin/v2/docs`` and ``.../ucsschool/kelvin/v2/redoc``.
See :doc:`api-reference` for the API conventions, authentication and
authorization.
