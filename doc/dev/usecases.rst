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
4. Kelvin Connector
5. API Operator
6. School Management Software


Manage Users
============

.. _uc001_create_user:

UC-001: Create User
-------------------

:Actor: All actors (besides Kelvin Connector?)
:Priority: Must-have
:Related Requirements: FR-001, NFR-S02

Description
^^^^^^^^^^^
An actor creates a new user account and assigns initial group memberships.

Preconditions
^^^^^^^^^^^^^
- Actor is authenticated
- Actor has administrator privileges (member of ``admin`` group)

Main Flow
^^^^^^^^^
1. Actor submits user data (email, display name, initial groups)
2. System validates input data
3. System creates user record in database
4. System publishes ``user.created`` event
5. Sync service receives event and creates user in directory service
6. System returns created user with assigned ID

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
**3a. Database returns an integrity error:**
   1. System checks which constraint failed (e.g. unique constraints like username or email already exists, groups within which the user is a member do not exist, etc.)
   2. System returns 409 Conflict with error details
   3. Use case ends

Postconditions
^^^^^^^^^^^^^^
- User exists in database with status ``active``
- User will be synchronized to directory service (eventually)
- Audit log entry created

Sequence Diagram
^^^^^^^^^^^^^^^^

.. TODO
   UML rendering see https://git.knut.univention.de/univention/dev/docs/sphinx-docker/-/merge_requests/60

.. code-block:: text
   :caption: User creation
   :name: uc-chapter-example

   @startuml
   actor Admin
   participant API
   database PostgreSQL
   queue MessageBroker
   participant SyncService
   participant DirectoryService

   Admin -> API: POST /users
   API -> API: Validate input
   API -> PostgreSQL: Insert user
   API -> MessageBroker: Publish user.created
   API --> Admin: 201 Created

   MessageBroker -> SyncService: user.created
   SyncService -> DirectoryService: Create user
   @enduml

.. _uc002_modify_user:

UC-002: Modify User
-------------------

:Actor: All actors (besides Kelvin Connector?)
:Priority: Must-have
:Related Requirements: FR-001, NFR-S02

Description
^^^^^^^^^^^
An actor modifies an existing user account

Preconditions
^^^^^^^^^^^^^
- Actor is authenticated
- Actor has administrator privileges (member of ``admin`` group)

Main Flow
^^^^^^^^^
1. Actor submits changed user data
2. System validates input data
3. System modifies user record in database
4. System publishes ``user.modified`` event
5. Sync service receives event and creates user in directory service
6. System returns modified user

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
**3a. Database returns an integrity error:**
   1. System checks which constraint failed (e.g. unique constraints like username or email already exists, groups within which the user is a member do not exist, etc.)
   2. System returns 409 Conflict with error details
   3. Use case ends

Postconditions
^^^^^^^^^^^^^^
- User is modified in database
- User changes will be synchronized to directory service (eventually)
- Audit log entry created

Sequence Diagram
^^^^^^^^^^^^^^^^
.. TODO
   UML rendering

.. uml::
   :caption: User modification
   :name: uc-user-modification

   @startuml
   actor Admin
   participant API
   database PostgreSQL
   queue MessageBroker
   participant SyncService
   participant DirectoryService

   Admin -> API: PUT/PATCH /users
   API -> API: Validate input
   API -> PostgreSQL: Update user
   API -> MessageBroker: Publish user.modified
   API --> Admin: 200 OK

   MessageBroker -> SyncService: user.modified
   SyncService -> DirectoryService: Modify user
   @enduml

.. _uc003_delete_user:

UC-003: Delete User
-------------------


Manage Schools
==============

.. _uc004_:

UC-004: Create School
---------------------

.. _uc005_:

UC-005: Modify School
---------------------

.. _uc006_:

UC-006: Delete School
---------------------

Manage Groups
=============

.. _uc007_:

UC-007: Create Group
--------------------

.. _uc008_:

UC-008: Modify Group
--------------------

.. _uc009_:

UC-009: Delete Group
--------------------

