# Performance Tests for the Kelvin REST API

The performance Debian package contains Univention pytest tests,
related locustfiles and a Python package, `ucs_test_ucsschool_kelvin_performance`,
which install locust and dependencies. The Python package is
installed in a virtual environment, `/var/lib/ucs-test-ucsschool-kelvin-performance/venv`,
in the post install step of the Debian package.

When the pytest tests are run on the backup server for the first time,
test data is retrieved via a pytest fixture from LDAP and stored in a cache.
For each test `0*.py`, a locust process is spawned using `locust` in the virtual environment
and one of the locust files in `locust_files/`.
Results are stored in `/var/lib/ucs-test-ucsschool-kelvin-performance/results/`.
The `*_stats.csv` files stored there are then used by the pytest tests to evaluate if the endpoint
fulfills the performance requirements.

## Selecting the API version (v1 / v2)

Like the `kelvin-api` unit tests, the performance tests can target the `v1` or `v2`
Kelvin API endpoints (or both). The version is selected via:

- the `--api-version` pytest option (`v1`, `v2` or `both`), or
- the `UCS_ENV_KELVIN_API_VERSION` environment variable (same values).

When neither is set, both versions are tested. `ucs-test` cannot forward pytest
options, so under `ucs-test` (and in CI) the `UCS_ENV_KELVIN_API_VERSION`
environment variable is the way to control this; see
`.gitlab-ci/branch_performance_tests.cfg`.

When `both` is selected, every test runs Locust once per version and writes its
results to a version-suffixed file (e.g. `010-get-all-users-v1_stats.csv` and
`010-get-all-users-v2_stats.csv`), so the two runs never overwrite each other.

## Waiting for the v2 database (`wait_for_db_full.py`)

The v2 API serves from a separate database that the connector fills by consuming
the provisioning queue. With a large pre-filled LDAP, that database is empty when
the app starts and catches up asynchronously — there is no queue-depth endpoint,
so `wait_for_db_full.py` polls instead: it reads the expected per-school user
counts from LDAP and waits until the Kelvin v2 REST API reports the same counts.

It uses the host's **system** Python (for `univention.admin.uldap`), not the
Locust virtualenv, so it is run directly:

```bash
python3 /usr/share/ucs-test/94_ucsschool-kelvin-performance/wait_for_db_full.py
```

CI runs it in `branch_performance_tests.cfg` after the app restart and before
`ucs-test`. It exits non-zero (failing the run) if replication does not complete
within the timeout, and is a no-op when `UCS_ENV_KELVIN_API_VERSION=v1`.

The timeout must be large: the provisioning service pre-fills its **own** queue
(NATS) before delivering anything to the connector, which can take hours — during
that phase the v2 count legitimately stays at 0. Tunables:
`UCS_ENV_DB_FILL_TIMEOUT` (default 21600s = 6h), `UCS_ENV_DB_FILL_INTERVAL`
(30s), `UCS_ENV_DB_FILL_MIN_RATIO` (1.0). The CI job's own `timeout` must exceed
this plus the Locust run time.

