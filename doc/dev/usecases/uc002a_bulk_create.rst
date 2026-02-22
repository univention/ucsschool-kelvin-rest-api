.. _uc002a_bulk_create:

.. preview-start

:ref:`UC-002a: Bulk Create Object<uc002a_bulk_create>`
------------------------------------------------------

:Actor: All actors
:Priority: Should-have

An actor deletes multiple objects.
If an object already exists, it is skipped.
If an error occurs, no objects are created.

.. preview-end

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
