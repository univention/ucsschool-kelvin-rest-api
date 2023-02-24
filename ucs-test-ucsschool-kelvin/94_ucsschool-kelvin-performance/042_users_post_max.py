#!/usr/share/ucs-test/runner /usr/bin/pytest-3 -l -v
## -*- coding: utf-8 -*-
## desc: Test performance of POST /ucsschool/kelvin/v1/users/ (max)
## tags: [kelvin, performance]
## exposure: dangerous
## packages: []
## bugs: []

import copy
from pathlib import Path

import pytest
from conftest import ENV_LOCUST_DEFAULTS, RESULT_DIR, set_locust_environment_vars
from locust_files.settings_kelvin import KELVIN_URL_BASE

LOCUST_ENV_VARIABLES = copy.deepcopy(ENV_LOCUST_DEFAULTS)
LOCUST_ENV_VARIABLES["LOCUST_RUN_TIME"] = "2m"
LOCUST_ENV_VARIABLES["LOCUST_STOP_TIMEOUT"] = "15"
LOCUST_ENV_VARIABLES["LOCUST_SPAWN_RATE"] = "0.2"  # add a user every 5s
LOCUST_ENV_VARIABLES["LOCUST_USERS"] = str(4 * 1 * 4)  # 4 clients per CPU on 1 machine with 4 CPUs

RESULT_FILES_NAME = "042-users-post-max"
RESULT_FILE_BASE_PATH = RESULT_DIR / RESULT_FILES_NAME
LOCUST_FILE_PATH = Path(__file__).parent / "locust_files" / "04_users_post.py"
URL_NAME = f"{KELVIN_URL_BASE}/users/"


@pytest.fixture(scope="module")
def run_test(execute_test, verify_test_sent_requests, wait_for_replication, sleep10):
    set_locust_environment_vars(LOCUST_ENV_VARIABLES)
    execute_test(LOCUST_FILE_PATH, "CreateUser", RESULT_FILE_BASE_PATH)
    # fail in fixture, so pytest prints the output of Locust,
    # regardless which test_*() function started Locust
    verify_test_sent_requests(RESULT_FILE_BASE_PATH)


def test_failure_count(check_failure_count, run_test):
    check_failure_count(RESULT_FILE_BASE_PATH)


def test_rps(check_rps, run_test):
    check_rps(RESULT_FILE_BASE_PATH, URL_NAME, 1.5)


def test_95_percentile(check_95_percentile, run_test):
    check_95_percentile(RESULT_FILE_BASE_PATH, URL_NAME, 10000)
