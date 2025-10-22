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

