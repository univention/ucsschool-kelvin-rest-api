.. SPDX-FileCopyrightText: 2026 Univention GmbH
..
.. SPDX-License-Identifier: AGPL-3.0-only


*********
Use Cases
*********

* 🚧 Actor: Who initiates this use case (user role, external system, scheduler)?
* 🚧 Preconditions: What must be true before this use case can execute?
* 🚧 Trigger: What event starts this use case?
* 🚧 Main Flow: What are the step-by-step interactions?
* 🚧 Alternative Flows: What variations exist (optional steps, different paths)?
* 🚧 Exception Flows: What happens when something goes wrong?
* 🚧 Postconditions: What is guaranteed to be true after successful execution?
* 🚧 Business Rules: What domain rules apply during this use case?


Actor List
==========

1. Administrators

   Human administrators who manage UCS\@school domain data (users, groups, schools).
   They may work through a GUI (UMC modules) or automate tasks through direct HTTP
   API usage or command line interface provided by Kelvin.

2. UCS\@school bulk import software

   The UCS\@school import interface (CLI) used for bulk provisioning from external
   source data (e.g., CSV). It reads and normalizes records, generates unique
   usernames and email addresses, calculates changes (add/modify/delete), and
   applies them automatically.

3. UCS\@school user interface software

   Graphical user interfaces used by administrators to manage the same objects as
   the API, for example UCS web interfaces (UMC modules / user management UI).
   In this context, the UI acts as an HTTP client of the Kelvin REST API.

4. API Operator

   The person or team operating the Kelvin REST API service.

   Typical responsibilities include installation/updates, configuration (e.g. log
   level, token validity), certificate/CA management, monitoring, and incident
   response via service log files (see
   https://docs.software-univention.de/ucsschool-kelvin-rest-api/installation-configuration.html and
   https://docs.software-univention.de/ucsschool-kelvin-rest-api/what-to-do-in-case-of-errors.html).

5. School Management Software

   An external school information system (SIS) or school management application
   that provisions and maintains identities and groups in UCS\@school.
   It typically integrates via Kelvin REST API endpoints (CRUD and search) as an
   automated HTTP client.

6. Nubus (Kelvin Connector is triggered by Nubus)

   Nubus components can initiate changes on the directory side (UDM/LDAP). In the
   Kelvin v2 architecture, such changes are synchronized asynchronously into the
   School domain (and vice versa) through dedicated synchronization processes
   (often referred to as connector/provisioning consumers).

   Nubus is therefore an *event source and sync peer* impacting UCS\@school data
   consistency, rather than a typical interactive end user of the Kelvin HTTP API.

.. _uc_section_crud:

Manage Single Objects
=====================


The following objects are managed via CRUD operations:

- Users
- Groups
- Schools

.. _uc001a_create_object:

UC-001a: Create Object
----------------------

:Actor: All actors
:Priority: Must-have
:Related Requirements: FR-001, NFR-S02

Description
^^^^^^^^^^^
An actor creates a new object.

Preconditions
^^^^^^^^^^^^^
- Actor is authenticated

Main Flow
^^^^^^^^^
1. Actor submits object data
2. System validates input data
3. System verifies that actor has permission to create the object
4. System creates object record in database
5. System publishes ``object.created`` event
6. Sync service receives event and creates object in directory service
7. System returns created object with assigned ID

Alternative Flows
^^^^^^^^^^^^^^^^^

**5a. Directory service unavailable:**
   1. Event is queued for retry
   2. Main flow continues (eventual consistency)

Exception Flows
^^^^^^^^^^^^^^^

**2a. Validation fails:**
   1. System returns 422 Unprocessable Entity with validation errors
   2. Use case ends
**3a. Actor does not have permission:**
   1. System returns 403 Forbidden
   2. Use case ends
**4a. Database returns an integrity error:**
   1. System checks which constraint failed (e.g. unique constraints like username or email already exists)
   2. System returns 409 Conflict with error details
   3. Use case ends

Postconditions
^^^^^^^^^^^^^^
- Object exists in database
- Object will be synchronized to directory service (eventually)
- Audit log entry created

Sequence Diagram
^^^^^^^^^^^^^^^^

.. mermaid::

   sequenceDiagram
       Admin ->>API: POST /<object>
       API ->>API: Validate input
       break ValidationError
           API ->>Admin: 422 Unprocessable Content
       end
       API ->>API: Verify permissions
       break PermissionError
           API ->>Admin: 403 Forbidden
       end
       API ->>PostgreSQL: Insert object
       break IntegrityError
           API ->>Admin: 409 Conflict
       end
       API ->>MessageBroker: Publish object.created
       API ->>Admin: 201 Created

       MessageBroker ->> SyncService: object.created
       SyncService ->> DirectoryService: Create object

.. _uc001b_read_object:

UC-001b: Read Object
--------------------

:Actor: All actors
:Priority: Must-have
:Related Requirements:

Description
^^^^^^^^^^^
An actor read an object with a given ID.

Preconditions
^^^^^^^^^^^^^
- Actor is authenticated

Main Flow
^^^^^^^^^
1. Actor requests object data
2. System validates input data (ID)
3. System verifies that actor has permission to read the object
4. System retrieves object from database

Exception Flows
^^^^^^^^^^^^^^^

**2a. Validation fails:**
   1. System returns 422 Unprocessable Entity with validation errors
   2. Use case ends
**3a. Actor does not have permission:**
   1. System returns 403 Forbidden
   2. Use case ends
**4a. Object does not exist:**
   1. System returns 404 Not Found
   2. Use case ends

Postconditions
^^^^^^^^^^^^^^
- Audit log entry created

Sequence Diagram
^^^^^^^^^^^^^^^^

.. mermaid::

   sequenceDiagram
       Admin ->>API: GET /<object>
       API ->>API: Validate input
       break ValidationError
           API ->>Admin: 422 Unprocessable Content
       end
       API ->>API: Verify permissions
       break PermissionError
           API ->>Admin: 403 Forbidden
       end
       API ->>PostgreSQL: Retrieve object
       break IntegrityError
           API ->>Admin: 404 Not Found
       end
       API ->>Admin: 200 OK

.. _uc001c_update_object:

UC-001c: Update Object (partial/full)
-------------------------------------

:Actor: All actors
:Priority: Must-have
:Related Requirements:

Description
^^^^^^^^^^^
An actor updates an object.

Preconditions
^^^^^^^^^^^^^
- Actor is authenticated

Main Flow
^^^^^^^^^
1. Actor submits object data
2. System validates input data
3. System verifies that actor has permission to update the object
4. System creates object record in database
5. System publishes ``object.updated`` event
6. Sync service receives event and updates object in directory service
7. System returns updated object with assigned ID

Alternative Flows
^^^^^^^^^^^^^^^^^

**5a. Directory service unavailable:**
   1. Event is queued for retry
   2. Main flow continues (eventual consistency)

Exception Flows
^^^^^^^^^^^^^^^

**2a. Validation fails:**
   1. System returns 422 Unprocessable Entity with validation errors
   2. Use case ends
**3a. Actor does not have permission:**
   1. System returns 403 Forbidden
   2. Use case ends
**4a. Database returns an integrity error:**
   1. System checks which constraint failed (e.g. unique constraints like username or email already exists)
   2. System returns 409 Conflict with error details
   3. Use case ends

Postconditions
^^^^^^^^^^^^^^
- Object is updated in database
- Object changes will be synchronized to directory service (eventually)
- Audit log entry created

Sequence Diagram
^^^^^^^^^^^^^^^^

.. mermaid::

   sequenceDiagram
       Admin ->>API: PATCH or PUT /<object>
       API ->>API: Validate input
       break ValidationError
           API ->>Admin: 422 Unprocessable Content
       end
       API ->>API: Verify permissions
       break PermissionError
           API ->>Admin: 403 Forbidden
       end
       API ->>PostgreSQL: Update object
       break IntegrityError
           API ->>Admin: 409 Conflict
       end
       API ->>MessageBroker: Publish object.updated
       API ->>Admin: 200 OK

       MessageBroker ->> SyncService: object.updated
       SyncService ->> DirectoryService: Update object

.. _uc001d_delete_object:

UC-001d: Delete Object
----------------------

:Actor: All actors
:Priority: Must-have
:Related Requirements:

Description
^^^^^^^^^^^
An actor deletes an object.

Preconditions
^^^^^^^^^^^^^
- Actor is authenticated

Main Flow
^^^^^^^^^
1. Actor submits object id
2. System validates input data
3. System verifies that actor has permission to delete the object
4. System deletes object record from database
5. System publishes ``object.deleted`` event
6. Sync service receives event and deletes object in directory service

Alternative Flows
^^^^^^^^^^^^^^^^^

**5a. Directory service unavailable:**
   1. Event is queued for retry
   2. Main flow continues (eventual consistency)

Exception Flows
^^^^^^^^^^^^^^^

**2a. Validation fails:**
   1. System returns 422 Unprocessable Entity with validation errors
   2. Use case ends
**3a. Actor does not have permission:**
   1. System returns 403 Forbidden
   2. Use case ends
**4a. Database returns an integrity error:**
   1. System checks which constraint failed (e.g. unique constraints like username or email already exists)
   2. System returns 409 Conflict with error details
   3. Use case ends

Postconditions
^^^^^^^^^^^^^^
- Object is deleted in database
- Object deletions will be synchronized to directory service (eventually)
- Audit log entry created

Sequence Diagram
^^^^^^^^^^^^^^^^

.. mermaid::

   sequenceDiagram
       Admin ->>API: DELETE /<object>
       API ->>API: Validate input
       break ValidationError
           API ->>Admin: 422 Unprocessable Content
       end
       API ->>API: Verify permissions
       break PermissionError
           API ->>Admin: 403 Forbidden
       end
       API ->>PostgreSQL: Update object
       break IntegrityError
           API ->>Admin: 409 Conflict
       end
       API ->>MessageBroker: Publish object.deleted
       API ->>Admin: 200 OK

       MessageBroker ->> SyncService: object.deleted
       SyncService ->> DirectoryService: Delete object


.. _uc_section_bulk_operations:

Bulk manage objects
===================


.. _uc-002a_bulk_create:

UC-002a: Bulk Create Object
---------------------------

:Actor: All actors
:Priority: Should-have
:Related Requirements:

Description
^^^^^^^^^^^
An actor deletes multiple objects.
If an object already exists, it is skipped.
If an error occurs, no objects are created.

Preconditions
^^^^^^^^^^^^^
- Actor is authenticated

Main Flow
^^^^^^^^^
1. Actor submits object ids
2. System validates input data
3. System verifies that actor has permission to create the objects
4. System creates object records in database
5. System publishes ``object.created`` event for each object
6. Sync service receives event and creates objects in directory service

Alternative Flows
^^^^^^^^^^^^^^^^^

**5a. Directory service unavailable:**
   1. Events are queued for retry
   2. Main flow continues (eventual consistency)

Exception Flows
^^^^^^^^^^^^^^^

**2a. Validation fails:**
   1. System returns 422 Unprocessable Entity with validation errors
   2. Use case ends
**3a. Actor does not have permission for any of the objects:**
   1. System returns 403 Forbidden
   2. Use case ends
**4a. Database returns an integrity error:**
   1. System checks which constraint failed (e.g. unique constraints like username or email already exists)
   2. System returns 409 Conflict with error details
   3. Use case ends

Postconditions
^^^^^^^^^^^^^^
- Objects are created in database
- Object creations will be synchronized to directory service (eventually)
- Audit log entry created

Sequence Diagram
^^^^^^^^^^^^^^^^

.. mermaid::

   sequenceDiagram
       Admin ->>API: POST /<object>/bulk
       API ->>API: Validate input
       break ValidationError
           API ->>Admin: 422 Unprocessable Content
       end
       API ->>API: Verify permissions
       break PermissionError
           API ->>Admin: 403 Forbidden
       end
       API ->>PostgreSQL: Create object
       break IntegrityError
           API ->>Admin: 409 Conflict
       end
       API ->>MessageBroker: Publish object.created events
       API ->>Admin: 201 Created

       MessageBroker ->> SyncService: object.created
       SyncService ->> DirectoryService: Create objects


.. _uc002b_bulk_update:

UC-002b: Bulk Update Object
---------------------------

:Actor: All actors
:Priority: Should-have
:Related Requirements: FR-001, NFR-S02

Description
^^^^^^^^^^^
An actor updates multiple objects.

Preconditions
^^^^^^^^^^^^^
- Actor is authenticated

Main Flow
^^^^^^^^^
1. Actor submits object data
2. System validates input data
3. System verifies that actor has permission to update the objects
4. System deletes object records from database
5. System publishes ``object.updated`` event for each object
6. Sync service receives event and updates objects in directory service

Alternative Flows
^^^^^^^^^^^^^^^^^

**5a. Directory service unavailable:**
   1. Events are queued for retry
   2. Main flow continues (eventual consistency)

Exception Flows
^^^^^^^^^^^^^^^

**2a. Validation fails:**
   1. System returns 422 Unprocessable Entity with validation errors
   2. Use case ends
**3a. Actor does not have permission for any of the objects:**
   1. System returns 403 Forbidden
   2. Use case ends
**4a. Database returns an integrity error:**
   1. System checks which constraint failed (e.g. unique constraints like username or email already exists)
   2. System returns 409 Conflict with error details
   3. Use case ends

Postconditions
^^^^^^^^^^^^^^
- Objects are updated in database
- Object changes will be synchronized to directory service (eventually)
- Audit log entry created

Sequence Diagram
^^^^^^^^^^^^^^^^

.. mermaid::

   sequenceDiagram
       Admin ->>API: DELETE /<object>/bulk
       API ->>API: Validate input
       break ValidationError
           API ->>Admin: 422 Unprocessable Content
       end
       API ->>API: Verify permissions
       break PermissionError
           API ->>Admin: 403 Forbidden
       end
       API ->>PostgreSQL: Delete object
       break IntegrityError
           API ->>Admin: 409 Conflict
       end
       API ->>MessageBroker: Publish object.deleted events
       API ->>Admin: 200 OK

       MessageBroker ->> SyncService: object.deleted
       SyncService ->> DirectoryService: Delete objects


.. _uc002c_bulk_delete:

UC-002c: Bulk Delete Object
---------------------------

:Actor: All actors
:Priority: Should-have
:Related Requirements:

Description
^^^^^^^^^^^
An actor deletes multiple objects.

Preconditions
^^^^^^^^^^^^^
- Actor is authenticated

Main Flow
^^^^^^^^^
1. Actor submits object ids
2. System validates input data
3. System verifies that actor has permission to delete the objects
4. System deletes object records from database
5. System publishes ``object.deleted`` event for each object
6. Sync service receives event and deletes objects in directory service

Alternative Flows
^^^^^^^^^^^^^^^^^

**5a. Directory service unavailable:**
   1. Events are queued for retry
   2. Main flow continues (eventual consistency)

Exception Flows
^^^^^^^^^^^^^^^

**2a. Validation fails:**
   1. System returns 422 Unprocessable Entity with validation errors
   2. Use case ends
**3a. Actor does not have permission for any of the objects:**
   1. System returns 403 Forbidden
   2. Use case ends
**4a. Database returns an integrity error:**
   1. System checks which constraint failed
   2. System returns 409 Conflict with error details
   3. Use case ends

Postconditions
^^^^^^^^^^^^^^
- Objects are deleted in database
- Object deletions will be synchronized to directory service (eventually)
- Audit log entry created

Sequence Diagram
^^^^^^^^^^^^^^^^

.. mermaid::

   sequenceDiagram
       Admin ->>API: DELETE /<object>/bulk
       API ->>API: Validate input
       break ValidationError
           API ->>Admin: 422 Unprocessable Content
       end
       API ->>API: Verify permissions
       break PermissionError
           API ->>Admin: 403 Forbidden
       end
       API ->>PostgreSQL: Delete object
       break IntegrityError
           API ->>Admin: 409 Conflict
       end
       API ->>MessageBroker: Publish object.deleted events
       API ->>Admin: 200 OK

       MessageBroker ->> SyncService: object.deleted
       SyncService ->> DirectoryService: Delete objects


.. _uc_section_search_operations:

Searching
=========

.. _uc003a_simple_search:

UC-003a: Simple search
----------------------

:Actor: All actors
:Priority: Must-have
:Related Requirements:

Description
^^^^^^^^^^^
An actor retrieves a paginated and sorted list of objects without additional filter criteria.

Preconditions
^^^^^^^^^^^^^
- Actor is authenticated

Main Flow
^^^^^^^^^
1. Actor requests a list of objects with optional ``page``, ``page_size``, and ``sort`` parameters
2. System validates the pagination and sorting parameters
3. System verifies that actor has permission to list the resource
4. System retrieves the requested page of objects from the database, applying the requested sort order
5. System returns the result set together with pagination metadata (total count, current page, page size)

Exception Flows
^^^^^^^^^^^^^^^

**2a. Validation fails:**
   1. System returns 422 Unprocessable Entity with validation errors
   2. Use case ends
**3a. Actor does not have permission:**
   1. System returns 403 Forbidden
   2. Use case ends

Postconditions
^^^^^^^^^^^^^^
- Audit log entry created

Sequence Diagram
^^^^^^^^^^^^^^^^

.. mermaid::

   sequenceDiagram
      participant A as Actor

      A ->>API: GET /<object>?page=1&page_size=50&sort=name
      API ->>API: Validate input
      break ValidationError
          API ->>A: 422 Unprocessable Content
      end
      API ->>API: Verify permissions
      break PermissionError
          API ->>A: 403 Forbidden
      end
      API ->>PostgreSQL: Query objects (paginated, sorted)
      API ->>A: 200 OK (result set + pagination metadata)

.. _uc003b_complex_search:

UC-003b: Complex search
-----------------------

:Actor: All actors
:Priority: Must-have
:Related Requirements:

Description
^^^^^^^^^^^
An actor searches for objects using one or more of the following criteria:

- Attribute filters (exact match on one or more fields)
- Wildcard and substring matching on string fields
- Full-text search across indexed text fields
- Nested or relational filters (e.g. all users belonging to a specific class)
- Logical operators (``AND``, ``OR``, ``NOT``) to combine filter conditions

Results are paginated and sorted.

Preconditions
^^^^^^^^^^^^^
- Actor is authenticated

Main Flow
^^^^^^^^^
1. Actor submits a search request with one or more filter expressions and optional ``page``, ``page_size``, and ``sort`` parameters
2. System validates and parses the filter expressions (field names, operators, values)
3. System verifies that actor has permission to search the resource
4. System executes the query against the database using indexed filters
5. System returns the paginated result set together with pagination metadata (total count, current page, page size)

Alternative Flows
^^^^^^^^^^^^^^^^^

**4a. No objects match the search criteria:**
   1. System returns ``200 OK`` with an empty result list and a total count of 0
   2. Use case ends

Exception Flows
^^^^^^^^^^^^^^^

**2a. Validation or filter parsing fails:**
   1. System returns 422 Unprocessable Entity with validation errors indicating the invalid field, operator, or value
   2. Use case ends
**2b. Query targets non-indexed or unbounded fields:**
   1. System returns 400 Bad Request
   2. Use case ends
**3a. Actor does not have permission:**
   1. System returns 403 Forbidden
   2. Use case ends

Postconditions
^^^^^^^^^^^^^^
- Audit log entry created

Sequence Diagram
^^^^^^^^^^^^^^^^

.. mermaid::

   sequenceDiagram
      participant A as Actor

      A ->>API: GET /<object>?school=X&roles=teacher&name=Max*&page=1&page_size=50
      API ->>API: Validate and parse filter expressions
      break ValidationError
            API ->>A: 422 Unprocessable Content
      end
      break UnindexedFieldError
            API ->>A: 400 Bad Request
      end
      API ->>API: Verify permissions
      break PermissionError
            API ->>A: 403 Forbidden
      end
      API ->>PostgreSQL: Query objects (filtered, paginated, sorted)
      API ->>A: 200 OK (result set + pagination metadata)


.. _uc_section_monitoring:

Monitoring
==========

.. _uc004a_health_check:

UC-004a: Health Check
---------------------

:Actor: API Operator (monitoring systems, load balancers)
:Priority: Must-have
:Related Requirements:

Description
^^^^^^^^^^^
A caller queries the health of the API service.
The endpoint returns the status of each individual health check so that operators
and monitoring systems can determine whether the service is functioning correctly
and is ready to serve requests.

The following checks are performed:

- **Database connectivity**: The service can reach and query the database.
- **Directory service connectivity**: The service can reach the directory service.
- **Operation success rate**: The percentage of successful operations within a recent
  time window is above a configured threshold.

Preconditions
^^^^^^^^^^^^^
- No authentication required (health check endpoints are publicly accessible)

Main Flow
^^^^^^^^^
1. Caller requests the health status via ``GET /health``
2. System runs all health checks in parallel
3. System aggregates the individual check results
4. If all checks pass, system returns ``200 OK`` with the list of check results
5. If one or more checks fail, system returns ``503 Service Unavailable`` with the
   list of check results, indicating which checks failed

Alternative Flows
^^^^^^^^^^^^^^^^^

**2a. A health check times out:**
   1. The timed-out check is marked as failed with a ``timeout`` status
   2. Main flow continues at step 3

Exception Flows
^^^^^^^^^^^^^^^

*None. The endpoint always returns a response; failures are expressed as
check-level statuses within the response body.*

Postconditions
^^^^^^^^^^^^^^
- No state is changed

Sequence Diagram
^^^^^^^^^^^^^^^^

.. mermaid::

   sequenceDiagram
      participant Monitor as API Operator

       Monitor ->>API: GET /health
       API ->>API: Run health checks in parallel
       API ->>PostgreSQL: Connectivity check
       API ->>DirectoryService: Connectivity check
       API ->>API: Evaluate operation success rate
       alt All checks pass
           API ->>Monitor: 200 OK (all checks: pass)
       else One or more checks fail
           API ->>Monitor: 503 Service Unavailable (failed checks listed)
       end


.. _uc004b_statistics:

UC-004b: Statistics
-------------------

:Actor: API Operator (monitoring systems, dashboards)
:Priority: Should-have
:Related Requirements:

Description
^^^^^^^^^^^
A caller retrieves aggregated operation statistics for the API service.
The endpoint returns counters for successful and unsuccessful operations,
broken down by time window (last minute, last hour, last day).
This enables operators and dashboards to observe trends and detect anomalies
in API usage and error rates.

Preconditions
^^^^^^^^^^^^^
- Actor is authenticated

Main Flow
^^^^^^^^^
1. Caller requests statistics via ``GET /stats``
2. System verifies that the caller has permission to read statistics
3. System reads aggregated counters from the metrics store for each time window
4. System returns the counters for successful and unsuccessful operations per
   time window (minute, hour, day)

Exception Flows
^^^^^^^^^^^^^^^

**2a. Actor does not have permission:**
   1. System returns 403 Forbidden
   2. Use case ends
**3a. Metrics store is unavailable:**
   1. System returns 503 Service Unavailable
   2. Use case ends

Postconditions
^^^^^^^^^^^^^^
- No state is changed

Sequence Diagram
^^^^^^^^^^^^^^^^

.. mermaid::

   sequenceDiagram
      participant Monitor as API Operator

      Monitor ->>API: GET /stats
      API ->>API: Verify permissions
      break PermissionError
          API ->>Monitor: 403 Forbidden
      end
      API ->>MetricsStore: Read operation counters (1 min, 1 h, 1 d)
      break MetricsStoreUnavailable
          API ->>Monitor: 503 Service Unavailable
      end
      API ->>Monitor: 200 OK (successful/unsuccessful counts per time window)


Extensions and Customization
============================

Hooks
-----
