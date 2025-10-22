#!/usr/share/ucs-test/runner /usr/bin/pytest-3 -l -v
## -*- coding: utf-8 -*-
## desc: Test performance of GET /ucsschool/kelvin/v1/schools/
## tags: [kelvin, performance]
## exposure: safe
## packages: []
## bugs: []

import pytest
from conftest import LocustEnvironmentVariables, PerformanceTestParameters, execute_test

test_parameter = PerformanceTestParameters(
    target_locust_class="GetAllSchools",
    target_locust_file_name="schools.py",
    route="schools/",
    result_files_name="001-get-all-schools",
    locust_environment_variables=LocustEnvironmentVariables(),
)


@pytest.fixture(scope="module", autouse=True)
def run_test(verify_test_sent_requests):
    execute_test(test_parameter)
    verify_test_sent_requests(test_parameter.result_file_base_path)


def test_failure_count(check_failure_count):
    check_failure_count(test_parameter.result_file_base_path)


def test_rps(check_rps):
    check_rps(test_parameter.result_file_base_path, test_parameter.url_name, 4)


def test_99_percentile(check_99_percentile):
    check_99_percentile(test_parameter.result_file_base_path, test_parameter.url_name, 1000)
