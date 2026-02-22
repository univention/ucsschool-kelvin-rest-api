.. _uc002b_bulk_update:

.. preview-start

:ref:`UC-002b: Bulk Update Object<uc002b_bulk_update>`
------------------------------------------------------

:Actor: All actors
:Priority: Should-have

An actor updates multiple objects.
.. preview-end

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
