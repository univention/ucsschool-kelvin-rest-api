
.. _uc003b_complex_search:

.. preview-start

:ref:`UC-003b: Complex search<uc003b_complex_search>`
-----------------------------------------------------

:Actor: All actors
:Priority: Must-have

An actor searches for objects using one or more of the following criteria:

- Attribute filters (exact match on one or more fields)
- Wildcard and substring matching on string fields
- Full-text search across indexed text fields
- Nested or relational filters (e.g. all users belonging to a specific class)
- Logical operators (``AND``, ``OR``, ``NOT``) to combine filter conditions

Results are paginated and sorted.

.. preview-end

Preconditions
^^^^^^^^^^^^^
- Actor is authenticated

Main Flow
^^^^^^^^^
1. Actor submits a search request with one or more filter expressions and optional ``page``, ``page_size``, and ``sort`` parameters
2. System validates and parses the filter expressions (field names, operators, values)
3. System verifies that actor has permission to search the resource
4. System executes the query against the database using indexed filters
5. System returns the paginated result set together with pagination metadata (total count, current page, page size)

Alternative Flows
^^^^^^^^^^^^^^^^^

**4a. No objects match the search criteria:**
   1. System returns ``200 OK`` with an empty result list and a total count of 0
   2. Use case ends

Exception Flows
^^^^^^^^^^^^^^^

**2a. Validation or filter parsing fails:**
   1. System returns 422 Unprocessable Entity with validation errors indicating the invalid field, operator, or value
   2. Use case ends
**2b. Query targets non-indexed or unbounded fields:**
   1. System returns 400 Bad Request
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

      A ->>API: GET /<object>?school=X&roles=teacher&name=Max*&page=1&page_size=50
      API ->>API: Validate and parse filter expressions
      break ValidationError
            API ->>A: 422 Unprocessable Content
      end
      break UnindexedFieldError
            API ->>A: 400 Bad Request
      end
      API ->>API: Verify permissions
      break PermissionError
            API ->>A: 403 Forbidden
      end
      API ->>PostgreSQL: Query objects (filtered, paginated, sorted)
      API ->>A: 200 OK (result set + pagination metadata)
