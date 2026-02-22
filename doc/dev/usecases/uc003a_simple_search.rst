.. _uc003a_simple_search:

.. preview-start

:ref:`UC-003a: Simple search<uc003a_simple_search>`
---------------------------------------------------

:Actor: All actors
:Priority: Must-have

An actor retrieves a paginated and sorted list of objects without additional filter criteria.
... preview-end

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
