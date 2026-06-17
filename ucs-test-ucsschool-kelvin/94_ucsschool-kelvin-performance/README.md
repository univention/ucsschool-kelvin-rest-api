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

## Waiting for the v2 database

The v2 API serves from a separate database that the connector fills by consuming
the provisioning queue. With a large pre-filled LDAP this catches up only slowly
(the provisioning service even pre-fills its own queue first, which can take
hours). To keep that wait out of the performance run, the **golden image** is
built with a fully-replicated v2 database: the image build (in the
`ucsschool-images` repo) blocks on `ucsschool.kelvin.wait_for_db_full`, which
ships inside the Kelvin container:

```bash
univention-app shell ucsschool-kelvin-rest-api python3 -m ucsschool.kelvin.wait_for_db_full
```

It compares the ucsschool user count in LDAP with the user-row count in the v2
database and blocks until they match. Because the database is already full in the
image, the performance tests here do not need to wait.

