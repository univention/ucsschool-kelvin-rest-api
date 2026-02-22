.. _uc004a_health_check:

.. preview-start

:ref:`UC-004a: Health Check<uc004a_health_check>`
-------------------------------------------------

:Actor: API Operator (monitoring systems, load balancers)
:Priority: Must-have

A caller queries the health of the API service.
The endpoint returns the status of each individual health check so that operators
and monitoring systems can determine whether the service is functioning correctly
and is ready to serve requests.

The following checks are performed:

- **Database connectivity**: The service can reach and query the database.
- **Directory service connectivity**: The service can reach the directory service.
- **Operation success rate**: The percentage of successful operations within a recent
    time window is above a configured threshold.

.. preview-end

Preconditions
^^^^^^^^^^^^^
- No authentication required (health check endpoints are publicly accessible)

Main Flow
^^^^^^^^^
1. Caller requests the health status via ``GET /health``
2. System runs all health checks in parallel
3. System aggregates the individual check results
4. If all checks pass, system returns ``200 OK`` with the list of check results
5. If one or more checks fail, system returns ``503 Service Unavailable`` with the
   list of check results, indicating which checks failed

Alternative Flows
^^^^^^^^^^^^^^^^^

**2a. A health check times out:**
   1. The timed-out check is marked as failed with a ``timeout`` status
   2. Main flow continues at step 3

Exception Flows
^^^^^^^^^^^^^^^

*None. The endpoint always returns a response; failures are expressed as
check-level statuses within the response body.*

Postconditions
^^^^^^^^^^^^^^
- No state is changed

Sequence Diagram
^^^^^^^^^^^^^^^^

.. mermaid::

   sequenceDiagram
      participant Monitor as API Operator

       Monitor ->>API: GET /health
       API ->>API: Run health checks in parallel
       API ->>PostgreSQL: Connectivity check
       API ->>DirectoryService: Connectivity check
       API ->>API: Evaluate operation success rate
       alt All checks pass
           API ->>Monitor: 200 OK (all checks: pass)
       else One or more checks fail
           API ->>Monitor: 503 Service Unavailable (failed checks listed)
       end
