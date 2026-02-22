.. _uc002c_bulk_delete:

.. preview-start

:ref:`UC-002c: Bulk Delete Object<uc002c_bulk_delete>`
------------------------------------------------------

:Actor: All actors
:Priority: Should-have

An actor deletes multiple objects.

.. preview-end

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
