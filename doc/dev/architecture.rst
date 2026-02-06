.. SPDX-FileCopyrightText: 2026 Univention GmbH
..
.. SPDX-License-Identifier: AGPL-3.0-only

Architecture
============

System overview
---------------

* What does the system look like from a bird's eye view?
* Which external systems are involved (PostgreSQL, Guardian, Keycloak?, UDM REST, Provisioning service)?
* How do the components interact?
* C4 context diagram? (system within context)
* C4 container diagram? (API, DB, Kelvin Connector, Provisioning Service, ...)

Components
----------
* What layers are there (router, service, repository)?
* What are the responsibilities of each layer?
* What is the data flow for a typical request?

Data model
----------

* What entities exist and how are they related?
* What is the canonical data representation?

Authentication & Authorization
------------------------------

* How does the auth flow work (API token? OIDC?)?
* How are group memberships checked?
* What roles/permissions are there?
* Sequence diagram for auth flow

Interfaces
----------

* Which protocols/formats are used?
* What dependencies on external systems exist?
