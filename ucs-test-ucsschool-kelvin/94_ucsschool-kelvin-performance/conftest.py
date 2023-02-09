# -*- coding: utf-8 -*-
#
# Copyright 2023 Univention GmbH
#
# http://www.univention.de/
#
# All rights reserved.
#
# The source code of this program is made available
# under the terms of the GNU Affero General Public License version 3
# (GNU AGPL V3) as published by the Free Software Foundation.
#
# Binary versions of this program provided by Univention to you as
# well as other copyrighted, protected or trademarked materials like
# Logos, graphics, fonts, specific documentations and configurations,
# cryptographic keys etc. are subject to a license agreement between
# you and Univention and not subject to the GNU AGPL V3.
#
# In the case you use this program under the terms of the GNU AGPL V3,
# the program is provided in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
# GNU Affero General Public License for more details.
#
# You should have received a copy of the GNU Affero General Public
# License with the Debian GNU/Linux or Univention distribution in file
# /usr/share/common-licenses/AGPL-3; if not, see
# <http://www.gnu.org/licenses/>.

import csv
import os
import os.path
import subprocess
import time
from pathlib import Path
from typing import Dict, Iterable, List

import psutil
import pytest
from locust_files.settings_kelvin import kelvin_host

BASE_DIR = Path("/var/lib/ucs-test-ucsschool-kelvin-performance")
VENV = BASE_DIR / "venv"
LOCUST_EXE = VENV / "bin" / "locust"
RESULT_DIR = BASE_DIR / "results"
LOCUST_WORKER = os.environ.get("UCS_ENV_LOCUST_WORKER", "0")

ENV_LOCUST_DEFAULTS: Dict[str, str] = {
    "LOCUST_LOGLEVEL": "INFO",
    "LOCUST_RUN_TIME": "10s",
    "LOCUST_SPAWN_RATE": "1",
    "LOCUST_STOP_TIMEOUT": "10",
    "LOCUST_USERS": "1",
    "LOCUST_WAIT_TIME": "0.05",
}


def set_locust_environment_vars(locust_env_vars: Dict[str, str]):
    for k, v in locust_env_vars.items():
        if not k.startswith("LOCUST_"):
            raise ValueError(f"Environment variable {k!r} is not a locust environment variable.")
        os.environ[k] = v


@pytest.fixture(scope="session")
def rows():
    def _func(csv_file: Path) -> Iterable[Dict[str, str]]:
        print(f"Reading '{csv_file!s}'...")
        with csv_file.open() as fp:
            yield from csv.DictReader(fp)

    return _func


@pytest.fixture(scope="session")
def get_one_row(rows):
    def _func(csv_file: Path, column_name: str, column_value: str) -> Dict[str, str]:
        for row in rows(csv_file):
            if row[column_name] == column_value:
                return row
        raise ValueError(
            "No row found that had a column {!r} with value {!r}.".format(column_name, column_value)
        )

    return _func


@pytest.fixture(scope="session")
def check_failure_count(rows):
    def _func(result_file_base_path: Path) -> None:
        csv_file = Path(f"{result_file_base_path!s}_stats.csv")
        col = "Failure Count"
        for row in rows(csv_file):
            value = int(row[col])
            assert value == 0

    return _func


@pytest.fixture(scope="session")
def check_rps(get_one_row):
    def _func(result_file_base_path: Path, url_name: str, expected_min: float) -> None:
        csv_file = Path(f"{result_file_base_path!s}_stats.csv")
        row = get_one_row(csv_file, "Name", url_name)
        col = "Requests/s"
        value = float(row[col])
        assert value > expected_min

    return _func


@pytest.fixture(scope="session")
def check_95_percentile(get_one_row):
    def _func(result_file_base_path: Path, url_name: str, expected_max: int) -> None:
        csv_file = Path(f"{result_file_base_path!s}_stats.csv")
        row = get_one_row(csv_file, "Name", url_name)
        col = "95%"
        value = int(row[col])
        assert value < expected_max

    return _func


@pytest.fixture(scope="session")
def check_95_percentile_multirow(get_one_row):
    def _func(result_file_base_path: Path, url_names: List[str], expected_max: int) -> None:
        value = 0
        csv_file = Path(f"{result_file_base_path!s}_stats.csv")
        for url_name in url_names:
            row = get_one_row(csv_file, "Name", url_name)
            col = "95%"
            value += int(row[col])
        assert value < expected_max

    return _func


@pytest.fixture(scope="session")
def execute_test():
    """
    Execute `Locust`. Configure by setting environment variables (`LOCUST_*`). See
    https://docs.locust.io/en/stable/configuration.html#all-available-configuration-options
    """

    def _func(
        locust_path: Path,
        locust_user_class: str,
        result_file_base_path: Path,
        host: str = None,
        loglevel: str = None,
    ) -> None:
        for k, v in ENV_LOCUST_DEFAULTS.items():
            if k not in os.environ:
                os.environ[k] = v
        if loglevel:
            os.environ["LOCUST_LOGLEVEL"] = loglevel
        result_file_base_path.parent.mkdir(parents=True, exist_ok=True)
        envs = {k: v for k, v in os.environ.items() if k.startswith("LOCUST_")}
        cmd = [
            str(LOCUST_EXE),
            "--locustfile",
            str(locust_path),
            "--host",
            host or kelvin_host(),
            "--headless",
            f"--csv={result_file_base_path!s}",
            f"--html={result_file_base_path!s}.html",
            "--print-stats",
            locust_user_class,
        ]

        if LOCUST_WORKER == "1":
            cmd.append("--master")

        logfile = Path(f"{result_file_base_path!s}.log")
        print(f"Executing {' '.join(cmd)!r}...")
        print(f"Redirecting stdout and stderr for Locust execution to {logfile!r}.")
        msg = f"Running with 'LOCUST_' environment variables: {envs!r}\nExecuting: {cmd!r}\n"
        print(msg)
        with logfile.open("w") as fp:
            fp.write(f"{msg}\n")
            fp.flush()
            process = subprocess.Popen(cmd, stdout=fp, stderr=fp)  # nosec
            process.communicate()

    return _func


@pytest.fixture(scope="session")
def verify_test_sent_requests(rows):
    def _func(result_file_base_path: str) -> None:
        csv_file = Path(f"{result_file_base_path}_stats.csv")
        col = "Name"
        for row in rows(csv_file):
            assert row[col] != "Aggregated"  # should be the last row, so no requests were sent
            break  # found a row with request statistics

    return _func


@pytest.fixture(scope="module")
def wait_for_replication():
    yield
    print("Waiting for replication...")
    try:
        from univention.testing.utils import wait_for_replication

        wait_for_replication()
    except ImportError:
        print("Cannot load univention.testing.utils.wait_for_replication(). Sleeping 10s...")
        time.sleep(10)
    print("done.")


@pytest.fixture(scope="module")
def sleep10():
    """Sleep 10 sec. if executed by 'ucs-test'. (Give system time to settle down.)"""
    yield
    this_proc = psutil.Process(os.getpid())
    next_proc = psutil.Process(this_proc.ppid())
    if next_proc.name() == "ucs-test":
        print("Sleeping 10s...")
        time.sleep(10)
