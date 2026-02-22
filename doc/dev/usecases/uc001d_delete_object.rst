.. _uc001d_delete_object:

.. preview-start

:ref:`UC-001d: Update Object<uc001d_delete_object>`
---------------------------------------------------

:Actor: All actors
:Priority: Must-have

An actor deletes an object.

.. preview-end

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


Special Use Cases
=================

These use cases are special cases of the main CRUD use cases.
