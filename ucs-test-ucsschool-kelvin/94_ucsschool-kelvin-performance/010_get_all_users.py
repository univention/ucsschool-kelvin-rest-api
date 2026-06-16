#!/usr/share/ucs-test/runner /usr/bin/pytest-3 -l -v
## -*- coding: utf-8 -*-
## desc: Test performance of GET /ucsschool/kelvin/<version>/users/
## tags: [kelvin, performance]
## exposure: safe
## packages: []
## bugs: []

import pytest
from conftest import LocustEnvironmentVariables, PerformanceTestParameters, execute_test

test_parameter = PerformanceTestParameters(
    target_locust_class="GetAllUsers",
    target_locust_file_name="users.py",
    route="users/",
    result_files_name="010-get-all-users",
    locust_environment_variables=LocustEnvironmentVariables(),
)


@pytest.fixture(scope="module", autouse=True)
def run_test(api_version, verify_test_sent_requests):
    execute_test(test_parameter, api_version)
    # fail in fixture, so pytest prints the output of Locust,
    # regardless which test_*() function started Locust
    verify_test_sent_requests(test_parameter.result_file_base_path(api_version))


def test_failure_count(api_version, check_failure_count):
    check_failure_count(test_parameter.result_file_base_path(api_version))


def test_rps(api_version, check_rps):
    check_rps(test_parameter.result_file_base_path(api_version), test_parameter.url_name(api_version), 2)


def test_99_percentile(api_version, check_99_percentile):
    check_99_percentile(
        test_parameter.result_file_base_path(api_version), test_parameter.url_name(api_version), 2000
    )
