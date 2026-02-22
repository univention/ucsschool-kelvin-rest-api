.. _uc001b_read_object:

.. preview-start

:ref:`UC-001b: Read Object<uc001b_read_object>`
-----------------------------------------------

:Actor: All actors
:Priority: Must-have

An actor reads an object with a given ID.

.. preview-end

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
