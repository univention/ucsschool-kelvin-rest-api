.. _uc010_multiple_instances:

.. preview-start

:ref:`UC-010: Operating Multiple Instances<uc010_multiple_instances>`
---------------------------------------------------------------------

:Actor: Operators
:Priority: Must-have

It must be possible to operate multiple API instances in parallel.

For example in a failure scenario, if an API instance
(or an entire node/availability zone) becomes unavailable or unhealthy, the API
gateway/load balancer detects the failure via health checks and/or outlier detection, removes the
affected instance(s) from the routing pool, and transparently redirects new requests to remaining
healthy replicas; in-flight requests are retried only when safe (idempotent operations or requests
carrying an idempotent key) and otherwise fail fast with a controlled 503/502 response, while
auto-scaling/auto-healing replaces failed capacity and observability emits metrics/alerts so
operators can verify that availability and latency stayed within the defined SLO.

.. preview-end

Preconditions
^^^^^^^^^^^^^

   - At least N ≥ 2 healthy service instances exist (ideally across failure domains like AZs).
   - Load balancer/gateway has health checks configured and can exclude unhealthy targets.
   - API supports idem-potency for repeatable operations (or clearly marks non-idempotent ones).

Trigger
^^^^^^^

A service instance becomes unavailable or degraded (crash, node failure, network partition, overload, AZ outage).
