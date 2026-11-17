.. SPDX-FileCopyrightText: 2026 Univention GmbH
..
.. SPDX-License-Identifier: AGPL-3.0-only

Debugging
=========

Logging
-------

Kelvin consists of two processes with **different logging stacks**:

* The **REST API** uses the Python standard-library ``logging`` configured
  through the UCS\@school logging library
  (``ucsschool.lib.models.utils``). It is line-based (not JSON) and always logs
  to **stdout** (``get_stdout_handler``). ``setup_logging()``
  (``kelvin-api/ucsschool/kelvin/service/log.py``) is called once per worker
  from the FastAPI lifespan. The format includes the process id and the request
  correlation id:

  .. code-block:: text

     %(asctime)s %(levelname)-5s [<pid>][<correlation_id>] %(module)s.%(funcName)s:%(lineno)d  %(message)s

* The **Kelvin Connector** uses `loguru <https://loguru.readthedocs.io/en/stable/>`_ and
  logs to **stderr**.

The connector writes no log files. Its loguru output goes to stderr only, so
``docker logs`` on the connector container (compose service ``provisioning`` in
production, or ``connector`` in the local dev stack) is the place to read it.

The REST API logs to stdout, so ``docker logs`` on the API container is the most
direct place to read those logs. The API runs under gunicorn with uvicorn
workers, and its access and error logs go to stdout too. In addition, the API
writes the UCS\@school validation log to
``/var/log/univention/ucsschool-kelvin-rest-api/ucs-school-validation.log``
inside the container. The application rotates this file itself through a
``TimedRotatingFileHandler`` (hourly, keeping 60 files by default), so it needs
no ``logrotate`` configuration. UCR variable
``ucsschool/validation/logging/enabled`` controls this log and treats an unset
value as enabled.

In the App Center deployment, the API's access log is additionally routed on the
Docker host: an ``rsyslog`` rule writes messages tagged ``ucsschool-kelvin-rest-api``
to ``/var/log/univention/ucsschool-kelvin-rest-api/http.log``, and a generated
``logrotate`` configuration rotates that file. This host-side path doesn't exist
in the local dev stack.

Log levels
^^^^^^^^^^

.. list-table::
   :header-rows: 1
   :widths: 2 3 3

   * - Process
     - Setting
     - Default
   * - REST API
     - UCR ``ucsschool/kelvin/log_level`` /
       environment variable ``UCSSCHOOL_KELVIN_LOG_LEVEL`` (``DEBUG``/``INFO``/``WARNING``/``ERROR``)
     - ``ERROR`` on an unrecognized value; per-logger defaults in
       ``constants.py`` (``DEFAULT_LOG_LEVELS``) keep ``sqlalchemy`` /
       ``alembic`` at ``WARNING``
   * - Connector
     - environment variable ``KELVIN_CONNECTOR_LOG_LEVEL`` (loguru levels
       ``TRACE``…``CRITICAL``)
     - ``DEBUG``

The connector's levels are meaningful when debugging sync:
``TRACE``/``DEBUG`` = per-event flow and lookups, ``INFO`` = each successful
create/modify/delete and each skipped-as-irrelevant event, ``WARNING`` =
recoverable inconsistencies (for example object recreated on a modify), ``ERROR`` =
an event failed and is redelivered, ``CRITICAL`` = an event was dropped
after exhausting its delivery budget, or a fatal startup error.

Correlation IDs
^^^^^^^^^^^^^^^

The REST API integrates ``asgi-correlation-id``:

* A middleware accepts an incoming ``X-Request-ID`` (or generates one) and
  echoes it on the response, including error responses.
* The id is injected into every API log line (the ``correlation_id`` field).
* It is forwarded to the UDM REST client as ``request_id``, so a single request
  can be traced across **Kelvin → UDM**.

The connector does not use this scheme; it correlates by the Provisioning
``sequence_number`` and the object ``public_id``, which appear in its log lines.

Common problems
---------------

Slow / delayed LDAP reconnect
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

``ldap.py`` installs a custom ``FirstAttemptImmediateRestartableStrategy``
(``_install_immediate_reconnect_strategy``). ``ldap3``'s stock restartable
strategy sleeps *before* the first retry, so a stale-but-reachable connection
wasted seconds after an LDAP server restart. The subclass skips that initial
wait while keeping the normal interval for genuinely-down servers
(Bug #58263). Install failure is caught and logged as a warning (non-fatal).

UDM / validation errors
^^^^^^^^^^^^^^^^^^^^^^^^

Errors are reshaped by the handlers in
``kelvin-api/ucsschool/kelvin/service/exception_handler.py``:
``UdmError`` → its own status (fallback 500) as ``{"detail": [...]}`` with the
correlation-id header; UCS\@school ``ValidationError`` → 400; ``NoObject`` →
404; anything else → 500 (logged with a traceback). See :doc:`api-reference`
for the status-code and body conventions.

Stale ``v1`` school-existence cache
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

``routers/v1/school.py`` caches OU lookups in-process (``aiocache`` memory
cache, TTL from ``ucsschool/kelvin/cache_ttl``, default 300 s). Two pitfalls:

* The cache is **per gunicorn worker** — evicting an entry in one worker does
  not clear it in the others.
* Endpoints that must see fresh data evict explicitly first: school-create and
  the ``HEAD /{school_name}`` existence check call ``_remove_ou_from_cache()``
  before searching LDAP. (The ``HEAD`` eviction is the fix for the case where a
  ``HEAD`` request returned a stale cached result.)

Kelvin DB row diverges from LDAP (``v2``)
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

The Kelvin DB is self-healing: a modify event for a missing object recreates
it, and deferred references resolve when the referenced object's own event
arrives. If a row is persistently wrong, the remedy is a fresh Provisioning
event for that object (or re-prefilling the subscription), not manual editing.
See :doc:`synchronisation`.

Internal details
-----------------

Internal caches and mechanisms
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

Besides the ``v1`` OU cache above, the API keeps several in-process caches that
never expire within a worker's lifetime but are correctness-safe (they map
stable values): the URL⇄name lookups in ``urls.py``
(``cachetools.LRUCache``) and ``routers/v1/base.py`` (``functools.lru_cache``),
the per-version OpenAPI schema cache (``routers/v1/doc.py``), and ``lru_cache``
singletons for the LDAP configuration and loggers. The connector's DN → public_id
mapping is **not** an in-memory cache — it is persisted in SQL and is the usual
place to look when a reference "cannot be found".

Debug the sync flow
^^^^^^^^^^^^^^^^^^^

* Watch the connector container's logs; raise ``KELVIN_CONNECTOR_LOG_LEVEL`` to
  ``DEBUG`` or ``TRACE`` for per-event detail. The CCF logs every message
  (topic, ``seq=…``, object ID and DN), "Task enqueued" and the result of each
  task ("Monitoring entry created … SuccessCreated"); the callback logs what it
  did or why it skipped the object.
* Remember the connector only runs on the Primary
  (``LDAP_SERVER_TYPE=master``); elsewhere its setup fails on purpose and the
  CCF keeps retrying it without doing anything.
* Confirm the subscription is set up: the container needs
  ``PROVISIONING_NAME`` and ``PROVISIONING_PASSWORD``. The join script writes
  the password and ``DATABASE_URL`` to ``conf/provisioning/connector.env`` in the
  app's directory (from ``provisioning_config.json`` and the Kelvin DB
  credentials); if that file is empty, rerun the join script. The
  ``kelvin-connector`` subscription must be registered and prefilled. The queue can be inspected through
  the Provisioning REST API
  (``/v1/subscriptions/kelvin-connector/messages/next``).
* Startup: the CCF retries its setup, including the connector's setup
  function, every ``SETUP_RETRY_INTERVAL`` seconds (default 30) until it
  succeeds, logging "Setup failed; CCF keeps running and retries" with the
  reason whenever it changes (a missing environment variable, an unreachable
  DB, Kelvin's ``/health`` not answering yet, ...); ``kelvin-connector
  healthcheck`` shows ``Stuck in setup: …``. The container stays up, so it can
  be inspected while the configuration is fixed.
* "Setup failed, restart needed": the callback module could not be imported
  (e.g. a broken image). The CCF does not retry an import; fix the image and
  restart the container.
* Telltale log signatures: "not found on modify event, creating",
  "… not yet in mapper", "mapped but the … object is not in the Kelvin
  Database". A task that failed ``MAX_ALLOWED_ERRORS`` times (3) is moved to
  the ``ccf.morgue`` table.

See :doc:`synchronisation` for the full event flow and retry policy.
