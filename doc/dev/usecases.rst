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
2. UCS\@school bulk import software
3. UCS\@school user interface software
4. API Operator
5. School Management Software
6. Nubus (Kelvin Connector is triggered by Nubus)

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

Searching
=========

UC-003a: Simple search
----------------------

UC-003b: Complex search
-----------------------

Monitoring
==========

.. _uc010_:

UC-004a: Health Check
---------------------

Returns a list of health checks
Health check:
- Connectivity to database
- Connectivity to directory service
- Percentage of successful operations above a certain threshold


.. _uc011_:

UC-004b: Statistics
-------------------

How many successful operations have been performed in the last minute, hour, day.
How many unsuccessful operations have been performed in the last minute, hour, day.


Extensions and Customization
============================

Hooks
-----
