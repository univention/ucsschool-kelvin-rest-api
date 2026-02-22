.. _uc004b_statistics:

.. preview-start

:ref:`UC-004b: Statistics<uc004b_statistics>`
---------------------------------------------


:Actor: API Operator (monitoring systems, dashboards)
:Priority: Should-have

A caller retrieves aggregated operation statistics for the API service.
The endpoint returns counters for successful and unsuccessful operations,
broken down by time window (last minute, last hour, last day).
This enables operators and dashboards to observe trends and detect anomalies
in API usage and error rates.

.. preview-end

Preconditions
^^^^^^^^^^^^^
- Actor is authenticated

Main Flow
^^^^^^^^^
1. Caller requests statistics via ``GET /stats``
2. System verifies that the caller has permission to read statistics
3. System reads aggregated counters from the metrics store for each time window
4. System returns the counters for successful and unsuccessful operations per
   time window (minute, hour, day)

Exception Flows
^^^^^^^^^^^^^^^

**2a. Actor does not have permission:**
   1. System returns 403 Forbidden
   2. Use case ends
**3a. Metrics store is unavailable:**
   1. System returns 503 Service Unavailable
   2. Use case ends

Postconditions
^^^^^^^^^^^^^^
- No state is changed

Sequence Diagram
^^^^^^^^^^^^^^^^

.. mermaid::

   sequenceDiagram
      participant Monitor as API Operator

      Monitor ->>API: GET /stats
      API ->>API: Verify permissions
      break PermissionError
          API ->>Monitor: 403 Forbidden
      end
      API ->>MetricsStore: Read operation counters (1 min, 1 h, 1 d)
      break MetricsStoreUnavailable
          API ->>Monitor: 503 Service Unavailable
      end
      API ->>Monitor: 200 OK (successful/unsuccessful counts per time window)
