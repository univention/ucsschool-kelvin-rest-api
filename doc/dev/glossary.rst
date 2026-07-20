.. SPDX-FileCopyrightText: 2026 Univention GmbH
..
.. SPDX-License-Identifier: AGPL-3.0-only

Glossary
========

Explanation of domain-specific terms and abbreviations.

.. glossary::

   UCS
      Univention Corporate Server — a Debian-based Linux distribution with an
      integrated identity and access management system (Nubus).

   Nubus
      The identity and access management at the heart of UCS. Stores all
      identity data (users, groups, computers, …) in OpenLDAP and is the
      authoritative source of truth for the data Kelvin manages.

   UCS\@school
      An add-on / app on top of UCS providing data models, functions and UIs
      for the educational sector.

   UDM
      Univention Directory Manager — Nubus's data model and Python library over
      OpenLDAP.

   UDM REST API
      The HTTP interface to UDM. Kelvin's ``v1`` path and ``v2`` write path use
      it to read and persist data. Also called the *UDM HTTP REST API*.

   OpenLDAP
      The LDAP directory server used by Nubus for persistence. Kelvin (and the
      UCS\@school libraries) sometimes access it directly for performance or for
      attributes not exposed by UDM.

   Kelvin
      The UCS\@school Kelvin REST API — the HTTP frontend for managing
      UCS\@school objects (``kelvin-api/``).

   Kelvin Connector
      The Provisioning Consumer sidecar that keeps the ``v2`` SQL cache
      eventually consistent with LDAP by applying change events from the Nubus
      Provisioning service (``kelvin-connector/``). See :doc:`synchronisation`.

   ``ucsschool-objects``
      The ``v2`` read-cache library — a persistence-agnostic, ports-and-adapters
      package with a SQLAlchemy/PostgreSQL adapter. It has no UDM, LDAP, FastAPI
      or Pydantic dependencies (``ucsschool-objects/``).

   Provisioning Service
      The Nubus event system that emits change events whenever LDAP data is
      modified. The Kelvin Connector consumes these events. See the
      `Nubus Provisioning documentation
      <https://docs.software-univention.de/manual/5.2/en/domain-ldap/nubus-provisioning-service.html>`_.

   Role
      A function a user has in a school, e.g. ``teacher``, ``student``,
      ``staff`` or ``school_admin``. Roles are a fixed set in Kelvin.

   School
      A UCS\@school organizational unit (OU) grouping users, classes and
      workgroups.

   School class
      A group of students within a school, typically corresponding to a class in
      the school's timetable.

   Workgroup
      A group within a school that is not a school class, e.g. a project or club.

   Read cache
      The PostgreSQL database introduced in ``v2`` from which read and search
      requests are served instead of querying LDAP / UDM. A denormalized
      projection of the authoritative LDAP state, not the source of truth. See
      :doc:`database`.

   Read-hook
      A UCS\@school (import) library hook run on read operations in ``v1``.
      ``v2`` reads bypass those libraries, so read-hooks are **not** executed in
      ``v2``.

   JWT
      JSON Web Token — the bearer token used to authenticate to the API. Kelvin
      issues a self-signed HS256 JWT from its token endpoint.
