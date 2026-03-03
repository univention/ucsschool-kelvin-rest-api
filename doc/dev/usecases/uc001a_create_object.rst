.. _uc001a_create_object:

.. preview-start

:ref:`UC-001a: Create Object<uc001a_create_object>`
---------------------------------------------------

:Actor: All actors
:Priority: Must-have
:Related Requirements: FR-001, NFR-S02

Description
^^^^^^^^^^^

   An actor creates a new object.

.. preview-end

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
