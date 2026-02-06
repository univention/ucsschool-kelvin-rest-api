.. SPDX-FileCopyrightText: 2026 Univention GmbH
..
.. SPDX-License-Identifier: AGPL-3.0-only

Use Cases
=========

* 🚧 Actor: Who initiates this use case (user role, external system, scheduler)?
* 🚧 Preconditions: What must be true before this use case can execute?
* 🚧 Trigger: What event starts this use case?
* 🚧 Main Flow: What are the step-by-step interactions?
* 🚧 Alternative Flows: What variations exist (optional steps, different paths)?
* 🚧 Exception Flows: What happens when something goes wrong?
* 🚧 Postconditions: What is guaranteed to be true after successful execution?
* 🚧 Business Rules: What domain rules apply during this use case?



.. _uc001_create_user:

UC-001: Create User
-------------------

:Actor: Administrator
:Priority: Must-have
:Related Requirements: FR-001, NFR-S02

Description
^^^^^^^^^^^
An administrator creates a new user account and assigns initial group memberships.

Preconditions
^^^^^^^^^^^^^
- Actor is authenticated
- Actor has administrator privileges (member of ``admin`` group)

Main Flow
^^^^^^^^^
1. Actor submits user data (email, display name, initial groups)
2. System validates input data
3. System checks that email is unique
4. System creates user record in database
5. System publishes ``user.created`` event
6. Sync service receives event and creates user in directory service
7. System returns created user with assigned ID

Alternative Flows
^^^^^^^^^^^^^^^^^

**3a. Email already exists:**
   1. System returns 409 Conflict with error details
   2. Use case ends

**6a. Directory service unavailable:**
   1. Event is queued for retry
   2. Main flow continues (eventual consistency)

Exception Flows
^^^^^^^^^^^^^^^

**2a. Validation fails:**
   1. System returns 422 Unprocessable Entity with validation errors
   2. Use case ends

Postconditions
^^^^^^^^^^^^^^
- User exists in database with status ``active``
- User will be synchronized to directory service (eventually)
- Audit log entry created

Sequence Diagram
^^^^^^^^^^^^^^^^
.. code-block:: text
   :caption: Example for plantuml content
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
