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

import contextlib
import csv
import os
import subprocess
import time
from collections.abc import Iterable
from dataclasses import asdict, dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import Callable

import psutil
import pytest
from diskcache import Index

import univention.testing.ucr
from univention.admin.uldap import getAdminConnection
from univention.testing.umc import Client

BASE_DIR = Path("/var/lib/ucs-test-ucsschool-kelvin-performance")
VENV = BASE_DIR / "venv"
LOCUST_EXE = VENV / "bin" / "locust"
RESULT_DIR = BASE_DIR / "results"
LOCUST_WORKER = os.environ.get("UCS_ENV_LOCUST_WORKER", "0")
LOCUST_FILE_PATH: Path = Path(__file__).parent / "locust_files"

KELVIN_HOST_ENV = "UCS_ENV_KELVIN_HOST"
KELVIN_HOST_FALLBACK = "primary.ucsschool.test"
KELVIN_URL_BASE = "/ucsschool/kelvin/v1"
TEST_DATA_PATH = "/var/lib/test-data"
KELVIN_WORKER_COUNT = 4

ucr = univention.testing.ucr.UCSTestConfigRegistry()
ucr.load()


@dataclass
class LocustEnvironmentVariables:
    LOCUST_LOGLEVEL: str = "INFO"
    LOCUST_RUN_TIME: str = "3m"
    LOCUST_SPAWN_RATE: str = "0.1"
    LOCUST_STOP_TIMEOUT: str = "15"
    LOCUST_USERS: str = str(KELVIN_WORKER_COUNT)
    LOCUST_WAIT_TIME: str = "0.05"


@dataclass
class PerformanceTestParameters:
    target_locust_file_name: str
    target_locust_class: str
    result_files_name: str
    route: str
    locust_environment_variables: LocustEnvironmentVariables = field(
        default_factory=LocustEnvironmentVariables
    )
    # post init
    target_locust_file_path: Path = field(init=False)
    result_file_base_path: Path = field(init=False)
    url_name: str = field(init=False)

    def __post_init__(self):
        self.target_locust_file_path = LOCUST_FILE_PATH / self.target_locust_file_name
        self.result_file_base_path = RESULT_DIR / self.result_files_name
        self.url_name = f"{KELVIN_URL_BASE}/{self.route}"


@lru_cache(maxsize=1)
def kelvin_host() -> str:
    with contextlib.suppress(KeyError):
        host = os.environ[KELVIN_HOST_ENV]
        print(f"Using Kelvin host from environment variable {KELVIN_HOST_ENV!r}: {host!r}")
        return host
    with contextlib.suppress(ImportError):
        import univention.testing.ucr

        ucr = univention.testing.ucr.UCSTestConfigRegistry()
        ucr.load()
        host = ucr["ldap/master"]
        print(f"Using primary domain controller as Kelvin host (from UCR): {host!r}")
        return host
    print(f"Using hard coded fallback as Kelvin host: {KELVIN_HOST_FALLBACK!r}")
    return KELVIN_HOST_FALLBACK


@pytest.fixture(scope="session")
def rows():
    def _func(csv_file: Path) -> Iterable[dict[str, str]]:
        print(f"Reading '{csv_file!s}'...")
        with csv_file.open() as fp:
            yield from csv.DictReader(fp)

    return _func


@pytest.fixture(scope="session")
def get_one_row(rows: Callable[[Path | str], list[dict[str, str]]]):
    def _func(csv_file: Path, column_name: str, column_value: str) -> dict[str, str]:
        for row in rows(csv_file):
            if row[column_name] == column_value:
                return row
        raise ValueError(
            "No row found that had a column {!r} with value {!r}.".format(column_name, column_value)
        )

    return _func


@pytest.fixture(scope="session")
def check_failure_count(rows: Callable[[Path | str], list[dict[str, str]]]):
    def _func(result_file_base_path: Path) -> None:
        csv_file = Path(f"{result_file_base_path!s}_stats.csv")
        col = "Failure Count"
        for row in rows(csv_file):
            value = int(row[col])
            assert value == 0

    return _func


@pytest.fixture(scope="session")
def check_rps(get_one_row: Callable[[Path | str, str, str], dict[str, str]]):
    def _func(result_file_base_path: Path, url_name: str, expected_min: float) -> None:
        csv_file = Path(f"{result_file_base_path!s}_stats.csv")
        row = get_one_row(csv_file, "Name", url_name)
        col = "Requests/s"
        value = float(row[col])
        assert value > expected_min

    return _func


@pytest.fixture(scope="session")
def check_95_percentile(get_one_row: Callable[[Path | str, str, str], dict[str, str]]):
    def _func(result_file_base_path: Path, url_name: str, expected_max: int) -> None:
        csv_file = Path(f"{result_file_base_path!s}_stats.csv")
        row = get_one_row(csv_file, "Name", url_name)
        col = "95%"
        value = int(row[col])
        assert value < expected_max

    return _func


@pytest.fixture(scope="session")
def check_99_percentile(get_one_row: Callable[[Path | str, str, str], dict[str, str]]):
    def _func(result_file_base_path: Path, url_name: str, expected_max: int) -> None:
        csv_file = Path(f"{result_file_base_path!s}_stats.csv")
        row = get_one_row(csv_file, "Name", url_name)
        col = "99%"
        value = int(row[col])
        assert value < expected_max

    return _func


def execute_test(
    test_parameter: PerformanceTestParameters,
    host: str | None = None,
    loglevel: str | None = None,
):
    """
    Execute `Locust`. Configure by setting environment variables (`LOCUST_*`). See
    https://docs.locust.io/en/stable/configuration.html#all-available-configuration-options
    """

    for k, v in asdict(test_parameter.locust_environment_variables).items():
        if k not in os.environ:
            os.environ[k] = v
    if loglevel:
        os.environ["LOCUST_LOGLEVEL"] = loglevel
    result_file_base_path = test_parameter.result_file_base_path
    result_file_base_path.parent.mkdir(parents=True, exist_ok=True)
    envs = {k: v for k, v in os.environ.items() if k.startswith("LOCUST_")}
    cmd = [
        str(LOCUST_EXE),
        "--locustfile",
        str(test_parameter.target_locust_file_path),
        "--host",
        host or kelvin_host(),
        f"--csv={result_file_base_path!s}",
        f"--html={result_file_base_path!s}.html",
        "--autostart",
        "--autoquit=10",
        "--print-stats",
        test_parameter.target_locust_class,
    ]

    if LOCUST_WORKER == "1":
        cmd.append("--master")

    logfile = Path(f"{result_file_base_path!s}.log")
    print(f"Executing {' '.join(cmd)!r}...")
    print(f"Redirecting stdout and stderr for Locust execution to {logfile!r}.")
    msg = f"Running with 'LOCUST_' environment variables: {envs!r}\nExecuting: {cmd!r}\n"
    print(msg)
    with logfile.open("w") as fp:
        _ = fp.write(f"{msg}\n")
        fp.flush()
        process = subprocess.Popen(cmd, stdout=fp, stderr=fp)  # nosec
        _ = process.communicate()


@pytest.fixture(scope="session")
def verify_test_sent_requests(rows: Callable[[Path | str], list[dict[str, str]]]):
    def _func(result_file_base_path: str) -> None:
        csv_file = Path(f"{result_file_base_path}_stats.csv")
        col = "Name"
        for row in rows(csv_file):
            assert row[col] != "Aggregated"  # should be the last row, so no requests were sent
            break  # found a row with request statistics

    return _func


@pytest.fixture(scope="module", autouse=True)
def sleep10():
    """Sleep 10 sec. if executed by 'ucs-test'. (Give system time to settle down.)"""
    yield
    this_proc = psutil.Process(os.getpid())
    next_proc = psutil.Process(this_proc.ppid())
    if next_proc.name() == "ucs-test":
        print("Sleeping 10s...")
        time.sleep(10)


@pytest.fixture(scope="session", autouse=True)
def check_expected_process_count():
    KELVIN_PERF_UCR = "test/kelvin-performance/cpu-count"
    client = Client.get_test_connection(kelvin_host())
    response_appcenter = client.umc_command(
        "appcenter/config", {"app": "ucsschool-kelvin-rest-api", "phase": "Settings"}, "appcenter"
    )
    processes = response_appcenter.result["values"]["ucsschool/kelvin/processes"]
    assert processes in (KELVIN_WORKER_COUNT, 0)

    response_ucr = client.umc_command("ucr/get", [KELVIN_PERF_UCR], "ucr")

    assert len(response_ucr.result) == 1
    assert response_ucr.result[0]["key"] == KELVIN_PERF_UCR
    cpu_count = int(response_ucr.result[0]["value"])
    assert KELVIN_WORKER_COUNT == cpu_count


@pytest.fixture(scope="session", autouse=True)
def create_test_data():
    if Path(TEST_DATA_PATH).exists():
        return
    db = Index(TEST_DATA_PATH)
    lo, _ = getAdminConnection()
    result = lo.search("(&(ou=school*)(ucsschoolRole=school:school*))", attr=("ou",))
    schools = [school["ou"][0].decode() for _, school in result]
    db["schools"] = schools

    for school in schools:
        school_data = {}
        result = lo.search(
            "(&(ucsschoolRole=student:school*))",
            attr=("uid",),
            base=f"ou={school},{ucr.get('ldap/base')}",
        )
        students = [student["uid"][0].decode() for _, student in result]
        school_data["students"] = students

        result = lo.search(
            "(&(ucsschoolRole=teacher:school*))",
            attr=("uid",),
            base=f"ou={school},{ucr.get('ldap/base')}",
        )
        teachers = [teacher["uid"][0].decode() for _, teacher in result]
        school_data["teachers"] = teachers

        result = lo.search(
            "(&(ucsschoolRole=staff:school*))", attr=("uid",), base=f"ou={school},{ucr.get('ldap/base')}"
        )
        staffs = [staff["uid"][0].decode() for _, staff in result]
        school_data["staffs"] = staffs

        result = lo.search(
            "(&(ucsschoolRole=legal_guardian:school*))",
            attr=("uid",),
            base=f"ou={school},{ucr.get('ldap/base')}",
        )
        legal_guardians = [legal_guardian["uid"][0].decode() for _, legal_guardian in result]
        school_data["legal_guardians"] = legal_guardians

        users = []
        users.extend(students)
        users.extend(teachers)
        users.extend(staffs)
        users.extend(legal_guardians)
        school_data["users"] = users

        result = lo.search(
            f"(&(ucsschoolRole=school_class:school:{school}))",
            attr=("cn",),
            base=f"ou={school},{ucr.get('ldap/base')}",
        )
        school_classes = [school_class["cn"][0].decode().split("-", 1)[1] for _, school_class in result]
        school_data["school_classes"] = school_classes

        result = lo.search(
            f"(&(ucsschoolRole=workgroup:school:{school}))",
            attr=("cn",),
            base=f"ou={school},{ucr.get('ldap/base')}",
        )
        workgroups = [work_group["cn"][0].decode().split("-", 1)[1] for _, work_group in result]
        school_data["workgroups"] = workgroups

        db[school] = school_data
