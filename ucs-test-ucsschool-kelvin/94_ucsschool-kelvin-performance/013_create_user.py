#!/usr/share/ucs-test/runner /usr/bin/pytest-3 -l -v
## -*- coding: utf-8 -*-
## desc: Test performance of POST /ucsschool/kelvin/v1/users/
## tags: [kelvin, performance]
## exposure: dangerous
## packages: []
## bugs: []


import pytest
from conftest import LocustEnvironmentVariables, PerformanceTestParameters, execute_test

test_parameter = PerformanceTestParameters(
    target_locust_class="CreateUser",
    target_locust_file_name="users.py",
    route="users/",
    result_files_name="013-create-user",
    locust_environment_variables=LocustEnvironmentVariables(),
)


@pytest.fixture(scope="module", autouse=True)
def run_test(verify_test_sent_requests):
    execute_test(test_parameter)
    # fail in fixture, so pytest prints the output of Locust,
    # regardless which test_*() function started Locust
    verify_test_sent_requests(test_parameter.result_file_base_path)


def test_failure_count(check_failure_count):
    check_failure_count(test_parameter.result_file_base_path)


def test_rps(check_rps):
    check_rps(test_parameter.result_file_base_path, test_parameter.url_name, 1.0)


def test_99_percentile(check_99_percentile):
    check_99_percentile(test_parameter.result_file_base_path, test_parameter.url_name, 5000)
