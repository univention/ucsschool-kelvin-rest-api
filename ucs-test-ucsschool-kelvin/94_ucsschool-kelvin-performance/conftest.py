# -*- coding: utf-8 -*-
#
# SPDX-FileCopyrightText: 2023-2026 Univention GmbH
# SPDX-License-Identifier: AGPL-3.0-only

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
from urllib.parse import parse_qs, urlparse

import psutil
import psycopg
import pytest
from diskcache import Index

import univention.testing.ucr
from univention.testing.umc import Client

BASE_DIR = Path("/var/lib/ucs-test-ucsschool-kelvin-performance")
VENV = BASE_DIR / "venv"
LOCUST_EXE = VENV / "bin" / "locust"
RESULT_DIR = BASE_DIR / "results"
LOCUST_WORKER = os.environ.get("UCS_ENV_LOCUST_WORKER", "0")
LOCUST_FILE_PATH: Path = Path(__file__).parent / "locust_files"

KELVIN_HOST_ENV = "UCS_ENV_KELVIN_HOST"
KELVIN_HOST_FALLBACK = "primary.ucsschool.test"
KELVIN_API_VERSION_ENV = "UCS_ENV_KELVIN_API_VERSION"
TEST_DATA_PATH = "/var/lib/test-data"
KELVIN_WORKER_COUNT = 4

# Kelvin DB connection. On the host the config files live in this folder; the
# UCSSCHOOL_KELVIN_DB_* environment variables (shared with kelvin-cache-seeder
# and ucsschool_objects) are the fallback. See the Kelvin API's own
# ``ucsschool/kelvin/database.py`` for the reference resolution.
KELVIN_CONFIG_DIR = Path("/etc/ucsschool/kelvin")
KELVIN_DB_URI_FILE = KELVIN_CONFIG_DIR / "postgresql-kelvin.uri"
KELVIN_DB_SECRET_FILE = KELVIN_CONFIG_DIR / "postgresql-kelvin.secret"
KELVIN_DB_USERNAME_FALLBACK = "ucsschool-kelvin-rest-api"


def kelvin_url_base(api_version: str) -> str:
    return f"/ucsschool/kelvin/{api_version}"


ucr = univention.testing.ucr.UCSTestConfigRegistry()
ucr.load()


def pytest_addoption(parser):
    parser.addoption(
        "--api-version",
        action="store",
        default=None,
        choices=["v1", "v2", "both"],
        help=(
            "Which API version(s) to test: v1, v2, or both. "
            f"Defaults to ${KELVIN_API_VERSION_ENV} or 'both' if unset."
        ),
    )


def _resolve_api_versions(config) -> list[str]:
    selection = config.getoption("--api-version") or os.environ.get(KELVIN_API_VERSION_ENV, "both")
    return ["v1", "v2"] if selection == "both" else [selection]


def pytest_generate_tests(metafunc):
    if "api_version" in metafunc.fixturenames:
        metafunc.parametrize("api_version", _resolve_api_versions(metafunc.config), scope="module")


@pytest.fixture(scope="module")
def api_version(request) -> str:
    """The Kelvin API version (``v1``/``v2``) the current test run targets."""
    return request.param


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

    def __post_init__(self):
        self.target_locust_file_path = LOCUST_FILE_PATH / self.target_locust_file_name

    def result_file_base_path(self, api_version: str) -> Path:
        """Result files are kept per API version so v1 and v2 runs don't overwrite each other."""
        return RESULT_DIR / f"{self.result_files_name}-{api_version}"

    def url_name(self, api_version: str) -> str:
        """The request name Locust reports in the stats CSV for this route (see ``base.py``)."""
        return f"{kelvin_url_base(api_version)}/{self.route}"


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
    api_version: str,
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
    # Tell the Locust subprocess (and its workers) which API version to target.
    os.environ[KELVIN_API_VERSION_ENV] = api_version
    result_file_base_path = test_parameter.result_file_base_path(api_version)
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


def _read_file(path: Path) -> str | None:
    with contextlib.suppress(OSError):
        return path.read_text().strip()
    return None


def _resolve_secret(config_file: Path, env_var: str, env_file_var: str) -> str | None:
    """Resolve a value: ``/etc/ucsschool/kelvin`` file first, then env, then env-pointed file."""
    value = _read_file(config_file)
    if value:
        return value
    value = os.environ.get(env_var)
    if value:
        return value
    env_file = os.environ.get(env_file_var)
    if env_file:
        return _read_file(Path(env_file))
    return None


def _kelvin_db_connect_kwargs() -> dict[str, str]:
    """Resolve Kelvin DB connection parameters for a synchronous ``psycopg`` connect.

    The config files under ``/etc/ucsschool/kelvin/`` take precedence; the
    ``UCSSCHOOL_KELVIN_DB_*`` environment variables (as used by
    ``kelvin-cache-seeder``) and UCR are the fallbacks.
    """
    uri = _resolve_secret(
        KELVIN_DB_URI_FILE, "UCSSCHOOL_KELVIN_DB_URI", "UCSSCHOOL_KELVIN_DB_URI_FILE"
    ) or ucr.get("ucsschool/kelvin/db/uri")
    if not uri:
        raise RuntimeError(
            "Could not determine the Kelvin DB URI (tried "
            f"{KELVIN_DB_URI_FILE!s}, $UCSSCHOOL_KELVIN_DB_URI[_FILE] and UCR "
            "ucsschool/kelvin/db/uri)."
        )

    password = _resolve_secret(
        KELVIN_DB_SECRET_FILE, "UCSSCHOOL_KELVIN_DB_PASSWORD", "UCSSCHOOL_KELVIN_DB_PASSWORD_FILE"
    )
    if not password:
        raise RuntimeError(
            "Could not determine the Kelvin DB password (tried "
            f"{KELVIN_DB_SECRET_FILE!s} and $UCSSCHOOL_KELVIN_DB_PASSWORD[_FILE])."
        )

    username = (
        os.environ.get("UCSSCHOOL_KELVIN_DB_USERNAME")
        or ucr.get("ucsschool/kelvin/db/username")
        or KELVIN_DB_USERNAME_FALLBACK
    )

    parsed = urlparse(uri)
    kwargs = {
        "host": parsed.hostname,
        "dbname": parsed.path.lstrip("/"),
        "user": username,
        "password": password,
    }
    if parsed.port:
        kwargs["port"] = str(parsed.port)
    # Forward query params such as ``sslmode=require`` straight to libpq.
    for key, values in parse_qs(parsed.query).items():
        kwargs[key] = values[-1]
    return kwargs


def _fetch_grouped(cur: "psycopg.Cursor", query: str, role: str) -> dict[str, list[str]]:
    """Run ``query`` (yielding ``(school, name)`` rows) for ``role``; bucket by school."""
    grouped: dict[str, list[str]] = {}
    cur.execute(query, (role,))
    for school, name in cur.fetchall():
        grouped.setdefault(school, []).append(name)
    return grouped


@pytest.fixture(scope="session", autouse=True)
def create_test_data():
    if Path(TEST_DATA_PATH).exists():
        return
    db = Index(TEST_DATA_PATH)

    user_query = """
        SELECT s.name, u.name
        FROM "user" u
        JOIN school_membership sm ON sm.user_id = u.id
        JOIN school s ON s.id = sm.school_id
        JOIN school_membership_role_association smra ON smra.school_membership_id = sm.id
        JOIN role r ON r.id = smra.role_id
        WHERE r.name = %s
    """
    group_query = """
        SELECT s.name, g.name
        FROM "group" g
        JOIN school s ON s.id = g.school_id
        JOIN group_role_association gra ON gra.group_id = g.id
        JOIN role r ON r.id = gra.role_id
        WHERE r.name = %s
    """

    with psycopg.connect(**_kelvin_db_connect_kwargs()) as conn, conn.cursor() as cur:
        cur.execute("SELECT name FROM school")
        schools = [name for (name,) in cur.fetchall()]

        students = _fetch_grouped(cur, user_query, "student")
        teachers = _fetch_grouped(cur, user_query, "teacher")
        staffs = _fetch_grouped(cur, user_query, "staff")
        legal_guardians = _fetch_grouped(cur, user_query, "legal_guardian")
        school_classes = _fetch_grouped(cur, group_query, "school_class")
        workgroups = _fetch_grouped(cur, group_query, "workgroup")

    db["schools"] = schools

    for school in schools:
        school_students = students.get(school, [])
        school_teachers = teachers.get(school, [])
        school_staffs = staffs.get(school, [])
        school_guardians = legal_guardians.get(school, [])
        db[school] = {
            "students": school_students,
            "teachers": school_teachers,
            "staffs": school_staffs,
            "legal_guardians": school_guardians,
            "users": [
                *school_students,
                *school_teachers,
                *school_staffs,
                *school_guardians,
            ],
            # ``group.name`` is stored as ``<school>-<shortname>``; keep only the shortname.
            "school_classes": [name.split("-", 1)[1] for name in school_classes.get(school, [])],
            "workgroups": [name.split("-", 1)[1] for name in workgroups.get(school, [])],
        }
