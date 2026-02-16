.. SPDX-FileCopyrightText: 2026 Univention GmbH
..
.. SPDX-License-Identifier: AGPL-3.0-only

Non-functional requirements
===========================

All non-functional requirements should be listed and named, so it's easier to reference them later on.

Performance
-----------

Operation Classes
^^^^^^^^^^^^^^^^^

This chapter defines the operation classes used to specify performance, timing, and synchronization requirements.

Unless stated otherwise, all performance targets assume steady-state operation under normal production workload conditions.


DB Access Operations
""""""""""""""""""""

These are **internal operation classes** (not API-facing) but extremely useful as **supporting quality requirements**.

DB - Read (Point Lookup)
~~~~~~~~~~~~~~~~~~~~~~~~

Single-row or primary-key lookup.

    Assumption: warm buffer cache
    Cold-cache behavior (e.g. immediately after restarts or failover)
    is intentionally out of scope for performance SLOs.

DB - Read (Range / Query)
~~~~~~~~~~~~~~~~~~~~~~~~~

Indexed range queries, filtered queries, joins with bounded result sets.

This operation class explicitly excludes unbounded table scans and ad-hoc
reporting or exploratory queries (e.g. queries without selective predicates
or appropriate indices). Such queries are not considered part of the
interactive API workload and are therefore **not covered by performance SLOs**.

DB - Write (Single Row / Transaction)
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Insert or update of one logical object in a single transaction.

    Assumption: no blocking locks caused by concurrent schema or index changes,
    maintenance jobs, or unusually long-running transactions
    (i.e. outside the normal OLTP workload).


DB - Write (Batch / Bulk)
~~~~~~~~~~~~~~~~~~~~~~~~~

Batched inserts/updates (e.g. sync, resync, migrations).


API Operations
""""""""""""""

Read - Single Resource
~~~~~~~~~~~~~~~~~~~~~~

Retrieval of one resource by identifier.

*Example:* ``GET /ucsschool/kelvin/v2/schools/{school_name}``

Read - Collection (Simple Search)
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Paginated and sorted list retrieval without additional filters.

*Example:* ``GET /ucsschool/kelvin/v2/schools/?page=1&page_size=50&sort=name``

    Pagination is assumed to use either stable keyset pagination
    or OFFSET-based pagination backed by appropriate indices,
    with a strictly bounded page_size.

Read - Collection (Filtered Search)
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Paginated and sorted list retrieval with one or more filters.

*Example:* ``GET /ucsschool/kelvin/v2/users/?school=EXAMPLE_SCHOOL&roles=teacher&page=1&page_size=50&sort=lastname``

    Filters are assumed to be backed by appropriate indices; queries that degrade
    into full-table scans are not considered part of the interactive API workload
    and are therefore out of scope for the defined performance targets.

    Queries on *custom extended attributes* are considered and are expected to meet
    the same performance targets as queries on built-in attributes.

Write - Create
~~~~~~~~~~~~~~

Creation of a new resource.

*Example:* ``POST /ucsschool/kelvin/v2/users/``

Write - Partial Update
~~~~~~~~~~~~~~~~~~~~~~

Partial modification of an existing resource.

*Example:* ``PATCH /ucsschool/kelvin/v2/classes/{school}/{class_name}``

Write - Full Replace (Idempotent Update)
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Full replacement of an existing resource.

*Example:* ``PUT /ucsschool/kelvin/v2/workgroups/{school}/{workgroup_name}``

Sync Operations of Nubus ↔ UCS@school
"""""""""""""""""""""""""""""""""""""

Sync - Propagation Delay (Regular / Background)
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Time until a change in one system becomes visible in the other system.

*Examples:*

* User creation
* User school change
* Nubus change → visible via ``GET /ucsschool/kelvin/v2/users/{username}``
* Kelvin change → visible in Nubus (e.g. new user)

Sync - Propagation Delay (Interactive / User-Wait)
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Time until a change becomes visible in the other system **while a user is waiting for completion**.

*Examples:*

* Password reset triggered
* Workgroup membership changes

Sync - Processing Throughput (Steady State)
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Processing rate during normal synchronization without backlog growth.

*Examples:*

* Continuous stream of Nubus updates processed by Kelvin
* Continuous stream of Kelvin updates processed by Nubus

Sync - Resynchronization / Catch-up
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Bulk synchronization after outages or detected inconsistencies.

*Examples:*

* Full resync from Nubus to Kelvin after downtime
* Full resync from Kelvin to Nubus after connector restart

Sync - Outtake / Error Handling
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Isolation, visibility, and retry of failed synchronization items.

*Examples:*

* Nubus → Kelvin update fails and is routed to outtake
* Kelvin → Nubus update fails and is retried later


Reference environments
^^^^^^^^^^^^^^^^^^^^^^

Each reference environment defines a reproducible combination of dataset and
infrastructure sizing.
The environments are used to validate performance, scalability, and synchronization
requirements under different operational contexts.

Unless stated otherwise, all reference environments use the same logical
dataset model consisting of the following pre-defined entity types:
schools, classes, workgroups, users, and roles.
Only the scale, distribution, and infrastructure sizing differ between the
environments.

    Each user has 60 extended attributes.

    *The figure of 60 extended attributes is only a rough estimate. The actual number
    depends heavily on the amount and types of software installed. See also the
    discussion* `here <https://git.knut.univention.de/univention/dev/education/ucsschool-kelvin-rest-api/-/merge_requests/187#note_612596>`_.

    The following KPIs will be revisited when support for custom roles is added to the Kelvin API.


SERVER_LARGE (L)
""""""""""""""""

**Application context: Whole country (future)**

This dataset represents a future, nationwide deployment across all federal states.
It is used for long-term capacity planning, scalability validation, and to assess
architectural limits under projected peak load after 10 years of growth plus an
additional 5% safety margin.
Results obtained with this dataset are used to evaluate whether the system
architecture remains viable under country-wide usage and to identify the need
for structural changes (e.g. partitioning, sharding, or architectural refactoring).

- Dataset scale (shared logical model):

  - Schools: ``42.000``

  - Groups: ``920.000``
    - Classes: ``500.000`` (27 per student)
    - Working groups: ``420.000`` (10 per school)

  - Users: ``34.140.000``
    - students: ``12.000.000``
    - legal guardians: ``21.000.000`` (1.7 × students)
    - teachers: ``800.000`` (1 per 15 students)
    - admins: ``130.000`` (3 per school)
    - staff: ``210.000`` (5 per school)

- Infra sizing:

  - ``1`` Primary Directory Node
  - ``42.000`` Replica Directory Nodes (one per school)
  - ``20`` Backup Directory Nodes

    This dataset is retained for future-proof performance tests in later iterations.
    At the moment, loading this scale into LDAP may be too slow to be practical.


SERVER_MEDIUM (M)
"""""""""""""""""

**Application context: Biggest Federal State NRW (current measurement)**

This dataset represents a realistic, present-day deployment for a large federal state
(North Rhine-Westphalia).
It is used as the primary reference for current performance measurements and SLO
validation, reflecting real-world data distributions and usage patterns.
This environment serves as the main baseline for performance testing, tuning,
and stakeholder alignment.

- Dataset scale (shared logical model):

  - Schools: ``6.000``

  - Groups: ``155.000``
    - Classes: ``100.000`` (27 per student)
    - Working groups: ``55.000`` (10 per school)

  - Users: ``8.250.000``
    - students: ``3.000.000``
    - legal guardians: ``5.000.000`` (1.7 x students)
    - teachers: ``200.000`` (1 per 14 students)
    - admins: ``20.000`` (3 per school)
    - staff: ``30.000`` (5 per school)

- Infra sizing:

  - ``1`` Primary Directory Node
  - ``6.000`` Replica Directory Nodes (one per school)
  - ``8`` Backup Directory Nodes

SERVER_DEV (S)
""""""""""""""

**Application context: Dev / CI**

This dataset represents a reduced-scale deployment used in development and CI
environments.
It is optimized for fast execution of automated tests, performance regression
detection, and local developer workflows, while still preserving realistic data
relationships and distributions.
Results from this dataset are not used for absolute performance validation, but
to detect relative changes and regressions over time.

- Dataset scale (shared logical model):

  - Schools: ``550``

  - Groups: ``18.000``
    - Classes: ``12.000`` (27 per student)
    - Working groups: ``5.500`` (10 per school)

  - Users: ``835.000``
    - students: ``300.000``
    - legal guardians: ``510.000`` (1.7 × students)
    - teachers: ``20.000`` (1 per 15 students)
    - admins: ``1.700`` (3 per school)
    - staff: ``2.800`` (5 per school)

- Infra sizing:

  - ``1`` Primary Directory Node
  - ``550`` Replica Directory Nodes (one per school)
  - ``2`` Backup Directory Nodes


Performance targets
^^^^^^^^^^^^^^^^^^^

DB Access Operation (SERVER_MEDIUM; draft)
""""""""""""""""""""""""""""""""""""""""""

    *About "draft": First define numbers with stakeholders. Then prototype and challenge them.*

+---------------------------------------+------------+--------------+--------------+-------------------------------------+
| Operation Class                       | Metric     | Target (p95) | Target (p99) | Notes                               |
+=======================================+============+==============+==============+=====================================+
| DB - Read (Point Lookup)              | Latency    | ≤ 20 ms      | ≤ 50 ms      | PK lookup, warm cache               |
+---------------------------------------+------------+--------------+--------------+-------------------------------------+
| DB - Read (Range / Query)             | Latency    | ≤ 100 ms     | ≤ 300 ms     | Indexed queries, bounded result set |
+---------------------------------------+------------+--------------+--------------+-------------------------------------+
| DB - Write (Single Row / Transaction) | Latency    | ≤ 100 ms     | ≤ 300 ms     | Commit included                     |
+---------------------------------------+------------+--------------+--------------+-------------------------------------+
| DB - Write (Batch / Bulk)             | Throughput | ≥ 500 rows/s | ≥ 200 rows/s | Sustained ≥ 1 min, tuned batch size |
+---------------------------------------+------------+--------------+--------------+-------------------------------------+


API Operations (SERVER_MEDIUM; draft)
"""""""""""""""""""""""""""""""""""""

    *About "draft": First define numbers with stakeholders. Then prototype and challenge them.*

The following performance targets apply under expected peak load,
assuming approximately 50-100 concurrent API requests.

+-------------------------------------+---------+--------------+--------------+-----------------------------+
| Operation Class                     | Metric  | Target (p95) | Target (p99) | Notes / Assumptions         |
+=====================================+=========+==============+==============+=============================+
| Read - Single Resource              | Latency | ≤ 300 ms     | ≤ 800 ms     | By-id lookup, small payload |
+-------------------------------------+---------+--------------+--------------+-----------------------------+
| Read - Collection (Simple Search)   | Latency | ≤ 500 ms     | ≤ 1 s        | page_size=50, 1 sort key    |
+-------------------------------------+---------+--------------+--------------+-----------------------------+
| Read - Collection (Filtered Search) | Latency | ≤ 600 ms     | ≤ 1.2 s      | ≤3 indexed filters          |
+-------------------------------------+---------+--------------+--------------+-----------------------------+
| Write - Create                      | Latency | ≤ 500 ms     | ≤ 1 s        | Validation + single write   |
+-------------------------------------+---------+--------------+--------------+-----------------------------+
| Write - Partial Update              | Latency | ≤ 500 ms     | ≤ 1 s        | PATCH semantics             |
+-------------------------------------+---------+--------------+--------------+-----------------------------+
| Write - Full Replace                | Latency | ≤ 700 ms     | ≤ 1.5 s      | PUT, full validation        |
+-------------------------------------+---------+--------------+--------------+-----------------------------+


Sync Operations Nubus ↔ UCS@school (SERVER_MEDIUM; draft)
"""""""""""""""""""""""""""""""""""""""""""""""""""""""""

    *About "draft": First define numbers with stakeholders. Then prototype and challenge them.*

+----------------------------------------------------+-----------+------------------+---------------+---------------+-----------------------------+
| Operation Class                                    | Direction | Metric           | Target (p95)  | Target (p99)  | Notes                       |
+====================================================+===========+==================+===============+===============+=============================+
| Sync - Propagation Delay (Regular / Background)    | Both      | Delay            | ≤ 30 s        | ≤ 2 min       | Machine-to-machine          |
+----------------------------------------------------+-----------+------------------+---------------+---------------+-----------------------------+
| Sync - Propagation Delay (Interactive / User-Wait) | Both      | Delay            | ≤ 2 s         | ≤ 5 s         | User waits                  |
+----------------------------------------------------+-----------+------------------+---------------+---------------+-----------------------------+
| Sync - Processing Throughput                       | Both      | Items/sec        | ≥ 20          | ≥ 10          | Steady state, no backlog    |
+----------------------------------------------------+-----------+------------------+---------------+---------------+-----------------------------+
| Sync - Resynchronization / Catch-up                | Both      | Backlog drain    | ≤ 6.7 min/10k | ≤ 13.4 min/10k| Average-sized sync items    |
+----------------------------------------------------+-----------+------------------+---------------+---------------+-----------------------------+
| Sync - Outtake / Error Handling                    | Both      | Time to isolation| ≤ 5 s         | ≤ 15 s        | Failed items must not block |
+----------------------------------------------------+-----------+------------------+---------------+---------------+-----------------------------+
| Sync - Outtake / Error Handling                    | Both      | Retry success    | ≥ 99 %        | —             | After correction            |
+----------------------------------------------------+-----------+------------------+---------------+---------------+-----------------------------+

- Regular sync: machine-to-machine operations, typically nightly or scheduled
- Interactive sync: user-facing operations where latency is directly perceived
- Measurement window for throughput: sustained for at least 10 minutes under steady-state conditions without backlog growth.

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
