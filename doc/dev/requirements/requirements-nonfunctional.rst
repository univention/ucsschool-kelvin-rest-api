.. SPDX-FileCopyrightText: 2026 Univention GmbH
..
.. SPDX-License-Identifier: AGPL-3.0-only

Non-functional requirements
===========================

All non-functional requirements should be listed and named, so it's easier to reference them later on.

Performance
-----------

* 🚧 What response time is acceptable (p95, p99)?
* 🚧 How many concurrent users must be supported?
* 🚧 What throughput is expected (requests/second)?

Scalability
-----------

* 🚧 How should the system scale (vertical/horizontal)?
* 🚧 What growth is anticipated?

Availability
------------

* 🚧 What uptime is required?
* 🚧 What is the acceptable downtime for maintenance?

Security
--------

* 🚧 What data protection requirements exist?
* 🚧 What compliance standards apply (GDPR, etc.)?
* 🚧 How must secrets be handled?

Reliability
-----------

* 🚧 How must the sync handle failures?
* 🚧 What retry/recovery mechanisms are required?
* 🚧 What is the acceptable data loss window (RPO)?

Maintainability
---------------

* 🚧 What logging/monitoring is required?
* 🚧 What documentation standards apply?
* 🚧 What code quality metrics must be met?

Compatibility
-------------

* 🚧 What API versioning strategy is required? (versioning via URL)
* 🚧 What backward compatibility guarantees exist?


Example structure
-----------------

.. code-block:: text
   :caption: Example for chapter content
   :name: nfr-chapter-example

    Performance
    -----------

    .. list-table::
       :header-rows: 1
       :widths: 10 30 20 20

       * - ID
         - Requirement
         - Target
         - Measurement
       * - NFR-P01
         - API response time for simple queries
         - < 100ms (p95)
         - Load testing
       * - NFR-P02
         - API response time for complex queries
         - < 500ms (p95)
         - Load testing
       * - NFR-P03
         - Concurrent user support
         - 500 users
         - Load testing

    Security
    --------

    NFR-S01: Authentication
    ^^^^^^^^^^^^^^^^^^^^^^^

    :Priority: Must-have

    All API endpoints (except health checks) must require valid authentication
    via API token or OpenID Connect.

    NFR-S02: Authorization
    ^^^^^^^^^^^^^^^^^^^^^^

    :Priority: Must-have

    Access to resources must be restricted based on group membership.
    Unauthorized access attempts must be logged.
