#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 Univention GmbH
# SPDX-License-Identifier: AGPL-3.0-only
"""
Run the Kelvin tests on a UCS test VM -- mainly a tool for coding agents.

Most Kelvin tests (the ones marked `in_container`) only run inside the Kelvin app container on a UCS
system with UCS@school and the Kelvin app installed. This script brings the working tree onto such a VM
and runs tests there, without the manual steps a human would do.

    deploy     build the images from the working tree, load them on the VM, reinitialize the app
    sync       copy the package sources and tests into the running containers, reload Kelvin (seconds)
    test       sync, then run pytest in the Kelvin container; results go to dev/_agent_test_results/
    host-test  run host-side ucs-test files (ucs-test-ucsschool-kelvin) on the VM
    prepare    one-time test setup on the VM (import config, mapped UDM properties, ucs-test packages)
    check      show the state of the VM
    revert     switch the app back to the images it had before the first deploy

The VM: --host or KELVIN_TEST_VM. SSH as root; set KELVIN_TEST_VM_PASSWORD to log in with a password
(needs sshpass), otherwise SSH keys are used. `sync` refuses to run when uv.lock differs from the one in
the deployed image: dependency changes need `deploy`.
"""

import argparse
import hashlib
import os
import shlex
import subprocess
import sys
import tarfile
import tempfile
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import cast

REPO = Path(__file__).resolve().parent.parent
RESULTS_DIR = REPO / "dev" / "_agent_test_results"
APP = "ucsschool-kelvin-rest-api"
API_CONTAINER = f"{APP}_api_1"
CONNECTOR_CONTAINER = f"{APP}_provisioning_1"
REGISTRY = "artifacts.software-univention.de/ucsschool"
API_IMAGE = f"{REGISTRY}/ucsschool-kelvin-rest-api"
CONNECTOR_IMAGE = f"{REGISTRY}/ucsschool-kelvin-connector"
LOCAL_API_IMAGE = "kelvin-agent-test:latest"
LOCAL_CONNECTOR_IMAGE = "kelvin-connector-agent-test:latest"
ORIG_SUFFIX = "-orig"
AGENT_LABEL = "agent-vm-test"
REMOTE_DIR = "/root/agent-vm-test"
COMPOSE_FILE = f"/var/lib/univention-appcenter/apps/{APP}/compose/docker-compose.yml"

API_SYNC_PATHS = [
    "kelvin-api/ucsschool",
    "kelvin-api/tests",
    "ucs-school-lib/modules",
    "ucs-school-import/modules",
    "ucsschool-objects/src",
    "kelvin-connector/src",
    "univention-directory-manager-modules-slim",
    "univention-lib-slim",
    "alembic",
]
CONNECTOR_SYNC_PATHS = ["kelvin-connector/src", "ucsschool-objects/src", "alembic"]
SYNC_MARKER = ".agent-vm-test-synced"
SUITES = {"kelvin-api": "/kelvin/kelvin-api", "lib": "/kelvin/ucs-school-lib/modules"}

MAPPED_UDM_PROPERTIES = """{
    "user": ["description", "displayName", "e-mail", "employeeType", "gidNumber", "organisation",
             "phone", "title", "uidNumber"],
    "school_class": ["gidNumber", "mailAddress"],
    "workgroup": ["gidNumber", "mailAddress"],
    "school": ["description", "userPath"]
}"""

RELOAD_KELVIN = rf"""
workers() {{
    docker exec -i {API_CONTAINER} python3 - <<'PY'
import pathlib
for proc in pathlib.Path("/proc").iterdir():
    try:
        stat = (proc / "stat").read_text()
        cmdline = (proc / "cmdline").read_bytes()
    except (OSError, ValueError):
        continue
    if proc.name.isdigit() and stat.rsplit(")", 1)[1].split()[1] == "1" and b"gunicorn" in cmdline:
        print(proc.name)
PY
}}
old="$(workers)"
docker exec {API_CONTAINER} kill -HUP 1
for _ in $(seq 1 240); do
    sleep 0.5
    remaining="$(comm -12 <(echo "$old" | sort) <(workers | sort))"
    [ -n "$remaining" ] && continue
    code="$(curl -s -o /dev/null -w '%{{http_code}}' http://localhost/ucsschool/kelvin/docs)"
    [ "$code" = 200 ] && break
done
if [ "$code" != 200 ]; then
    echo "Kelvin did not come back after reloading" >&2
    exit 1
fi
"""

REINITIALIZE = f"""
if ! univention-app reinitialize {APP} > {REMOTE_DIR}-reinitialize.log 2>&1; then
    tail -20 {REMOTE_DIR}-reinitialize.log
    exit 1
fi
"""

WAIT_FOR_KELVIN = """
for _ in $(seq 1 120); do
    code="$(curl -s -o /dev/null -w '%{http_code}' http://localhost/ucsschool/kelvin/docs)"
    [ "$code" = 200 ] && exit 0
    sleep 2
done
echo "Kelvin is not healthy" >&2
exit 1
"""


@dataclass(frozen=True)
class Options:
    ucs_test: bool = False
    no_connector: bool = False
    no_sync: bool = False
    suite: str = "kelvin-api"
    pytest_args: list[str] = field(default_factory=list)
    files: list[str] = field(default_factory=list)


class Remote:
    def __init__(self, host: str) -> None:
        self.host: str = host
        self.password: str | None = os.environ.get("KELVIN_TEST_VM_PASSWORD")

    def _ssh(self) -> list[str]:
        control_dir = Path(tempfile.gettempdir()) / f"agent-vm-test-{os.getuid()}"
        control_dir.mkdir(mode=0o700, exist_ok=True)
        opts = [
            *("-o", "StrictHostKeyChecking=accept-new", "-o", "ConnectTimeout=15"),
            *(
                "-o",
                "ControlMaster=auto",
                "-o",
                f"ControlPath={control_dir}/%C",
                "-o",
                "ControlPersist=300",
            ),
        ]
        if self.password:
            return ["sshpass", "-e", "ssh", "-o", "PubkeyAuthentication=no", *opts, f"root@{self.host}"]
        return ["ssh", *opts, f"root@{self.host}"]

    def _env(self) -> dict[str, str]:
        env = dict(os.environ)
        if self.password:
            env["SSHPASS"] = self.password
        return env

    def run(
        self, script: str, data: bytes | None = None, check: bool = True, capture: bool = False
    ) -> subprocess.CompletedProcess[bytes]:
        """Run a bash script as root on the VM; `data` is passed to it on stdin."""
        if data is None:
            cmd, stdin = [*self._ssh(), "bash -s"], script.encode()
        else:
            cmd, stdin = [*self._ssh(), f"bash -c {shlex.quote(script)}"], data
        result = subprocess.run(  # noqa: S603
            cmd, input=stdin, env=self._env(), capture_output=capture, check=False
        )
        if check and result.returncode:
            if capture:
                sys.stderr.write(result.stderr.decode(errors="replace"))
            raise SystemExit(f"Command on {self.host} failed with exit code {result.returncode}.")
        return result

    def run_from(self, source: subprocess.Popen[bytes], script: str) -> None:
        """Run a bash script as root on the VM with the stdout of `source` on its stdin."""
        result = subprocess.run(  # noqa: S603
            [*self._ssh(), f"bash -c {shlex.quote(script)}"],
            stdin=source.stdout,
            env=self._env(),
            check=False,
        )
        if result.returncode or source.wait():
            raise SystemExit(f"Command on {self.host} failed with exit code {result.returncode}.")

    def output(self, script: str) -> str:
        return self.run(script, capture=True).stdout.decode().strip()


def log(msg: str) -> None:
    print(f"[agent-vm-test] {msg}", flush=True)


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def code_hash(paths: list[str]) -> str:
    """Hash of the synced files, without tests: tests take effect without reloading Kelvin."""
    digest = hashlib.sha256()
    for path in paths:
        for file in sorted((REPO / path).rglob("*")):
            parts = file.relative_to(REPO).parts
            if not file.is_file() or "__pycache__" in parts or "tests" in parts or file.suffix == ".pyc":
                continue
            digest.update(str(file.relative_to(REPO)).encode())
            digest.update(file.read_bytes())
    return digest.hexdigest()


def tar_paths(paths: list[str]) -> bytes:
    def skip(info: tarfile.TarInfo) -> tarfile.TarInfo | None:
        name = Path(info.name).name
        if name == "__pycache__" or name.endswith(".pyc") or name.startswith(".coverage"):
            return None
        return info

    with tempfile.TemporaryFile() as fp:
        with tarfile.open(fileobj=fp, mode="w", dereference=True) as tar:
            for path in paths:
                tar.add(REPO / path, arcname=path, filter=skip)
        fp.seek(0)
        return fp.read()


def release_tag(remote: Remote) -> str:
    tag = remote.output(f"grep -m1 -oP 'image: {API_IMAGE}:\\K\\S+' {COMPOSE_FILE}")
    if not tag:
        raise SystemExit(f"Can't find the image of {APP} in {COMPOSE_FILE}. Is the app installed?")
    return tag


def cmd_check(remote: Remote, _options: Options) -> None:
    local_lock = sha256(REPO / "uv.lock")
    print(
        remote.output(
            f"""
ucs="$(ucr get version/version)-$(ucr get version/patchlevel)"
echo "host:              $(hostname -f) ($(ucr get server/role), UCS $ucs)"
app="appcenter/apps/{APP}"
echo "kelvin app:        $(ucr get $app/version) ($(ucr get $app/status))"
docker ps --format '{{{{.Names}}}}: {{{{.Image}}}} ({{{{.Status}}}})' \
    | grep '{APP}' | sed 's/^/container:         /'
echo "agent images:      $(docker images -q {LOCAL_API_IMAGE} | head -1 || true)"
lock="$(docker exec {API_CONTAINER} sha256sum /kelvin/uv.lock 2>/dev/null | cut -d' ' -f1)"
if [ "$lock" = "{local_lock}" ]; then
    echo "uv.lock:           same as local (sync possible)"
else
    echo "uv.lock:           differs from local (deploy needed)"
fi
echo "udm rest api:      $(systemctl is-active univention-directory-manager-rest)"
s4="$(univention-ldapsearch -LLL '(univentionService=S4 Connector)' cn | sed -n 's/^cn: //p')"
echo "s4 connectors:     $(echo $s4)"
ucs_test="$(dpkg-query -W -f='${{Version}}' ucs-test-ucsschool-kelvin 2>/dev/null)"
echo "ucs-test-kelvin:   ${{ucs_test:-not installed (prepare --ucs-test)}}"
"""
        )
    )


def cmd_prepare(remote: Remote, options: Options) -> None:
    log("Preparing the VM for the tests...")
    remote.run(
        f"""
set -e
udm_rest=univention-directory-manager-rest
systemctl is-active -q $udm_rest || systemctl start $udm_rest
cp /usr/share/ucs-school-import/configs/ucs-school-testuser-import.json \
    /var/lib/ucs-school-import/configs/user_import.json
cat > /etc/ucsschool/kelvin/mapped_udm_properties.json <<'EOF'
{MAPPED_UDM_PROPERTIES}
EOF
univention-app restart {APP}
{WAIT_FOR_KELVIN}
"""
    )
    if options.ucs_test:
        log("Installing ucs-test packages...")
        remote.run(
            f"""
set -e
export DEBIAN_FRONTEND=noninteractive
ucr set repository/online/unmaintained=yes >/dev/null
trap 'ucr set repository/online/unmaintained=no >/dev/null' EXIT
apt-get -qq update
apt-get -y -qq install ucs-test-checks ucs-test-ucsschool >/dev/null
mkdir -p {REMOTE_DIR}/deb && rm -f {REMOTE_DIR}/deb/*.deb
deb="$(docker exec {API_CONTAINER} sh -c 'ls /kelvin/ucs-test-ucsschool-kelvin_*.deb')"
docker cp "{API_CONTAINER}:$deb" {REMOTE_DIR}/deb/
apt-get -y -qq install {REMOTE_DIR}/deb/ucs-test-ucsschool-kelvin_*.deb >/dev/null
"""
        )
    log("Done.")


def cmd_deploy(remote: Remote, _options: Options) -> None:
    for target, image in (("kelvin-prod", LOCAL_API_IMAGE), ("connector-prod", LOCAL_CONNECTOR_IMAGE)):
        log(f"Building {image} ({target})...")
        subprocess.run(  # noqa: S603
            [  # noqa: S607
                "docker",
                "build",
                "--network",
                "host",
                "-q",
                "--label",
                f"{AGENT_LABEL}=true",
                "--target",
                target,
                "-t",
                image,
                "-f",
                "docker/Dockerfile",
                ".",
            ],
            cwd=REPO,
            check=True,
            stdout=subprocess.DEVNULL,
        )
    log(f"Loading the images on {remote.host}...")
    save = subprocess.Popen(  # noqa: S603
        ["docker", "save", LOCAL_API_IMAGE, LOCAL_CONNECTOR_IMAGE],  # noqa: S607
        stdout=subprocess.PIPE,
    )
    gzip = subprocess.Popen(["gzip", "-1"], stdin=save.stdout, stdout=subprocess.PIPE)  # noqa: S603, S607
    remote.run_from(gzip, "gunzip | docker load >/dev/null")
    if save.wait():
        raise SystemExit("docker save failed.")
    tag = release_tag(remote)
    log(f"Replacing the app's images ({tag}) and reinitializing the app...")
    remote.run(
        f"""
set -e
for pair in "{API_IMAGE} {LOCAL_API_IMAGE}" "{CONNECTOR_IMAGE} {LOCAL_CONNECTOR_IMAGE}"; do
    set -- $pair
    if ! docker image inspect "$1{ORIG_SUFFIX}:{tag}" >/dev/null 2>&1; then
        label="$(docker image inspect -f '{{{{index .Config.Labels "{AGENT_LABEL}"}}}}' "$1:{tag}")"
        if [ "$label" = true ]; then
            echo "$1:{tag} is an agent build, but $1{ORIG_SUFFIX}:{tag} doesn't exist." >&2
            exit 1
        fi
        docker tag "$1:{tag}" "$1{ORIG_SUFFIX}:{tag}"
    fi
    docker tag "$2" "$1:{tag}"
done
{REINITIALIZE}
{WAIT_FOR_KELVIN}
"""
    )
    log("Deployed.")


def cmd_sync(remote: Remote, options: Options) -> None:
    state = remote.output(
        f"""
docker exec {API_CONTAINER} sha256sum /kelvin/uv.lock | cut -d' ' -f1
docker exec {API_CONTAINER} cat /kelvin/{SYNC_MARKER} 2>/dev/null || echo none
docker exec {CONNECTOR_CONTAINER} cat /app/{SYNC_MARKER} 2>/dev/null || echo none
"""
    ).splitlines()
    remote_lock, api_synced, connector_synced = (state + ["none"] * 3)[:3]
    if remote_lock != sha256(REPO / "uv.lock"):
        raise SystemExit("uv.lock differs from the deployed image: run `deploy` first.")
    api_hash = code_hash(API_SYNC_PATHS)
    remote.run(f"docker cp - {API_CONTAINER}:/kelvin", data=tar_paths(API_SYNC_PATHS))
    if api_hash != api_synced:
        log("Code changed: reloading Kelvin...")
        marker = f"/kelvin/{SYNC_MARKER}"
        remote.run(
            f"{RELOAD_KELVIN}\necho {api_hash} | docker exec -i {API_CONTAINER} tee {marker} >/dev/null"
        )
    connector_hash = code_hash(CONNECTOR_SYNC_PATHS)
    if not options.no_connector and connector_hash != connector_synced:
        log("Connector code changed: restarting the connector...")
        remote.run(f"docker cp - {CONNECTOR_CONTAINER}:/app", data=tar_paths(CONNECTOR_SYNC_PATHS))
        marker = f"/app/{SYNC_MARKER}"
        remote.run(
            f"docker restart -t 2 {CONNECTOR_CONTAINER} >/dev/null\n"
            f"echo {connector_hash} | docker exec -i {CONNECTOR_CONTAINER} tee {marker} >/dev/null"
        )
    log("Synced.")


def fetch_results(remote: Remote, run_id: str, files: list[str]) -> Path:
    out = RESULTS_DIR / run_id
    out.mkdir(parents=True, exist_ok=True)
    for name in files:
        result = remote.run(f"cat {REMOTE_DIR}/{run_id}/{name}", capture=True, check=False)
        if result.returncode == 0:
            (out / name).write_bytes(result.stdout)
    return out


def follow(remote: Remote, run_id: str) -> int:
    """Print the remote log until the run finished; the run survives a lost connection."""
    offset = 0
    while True:
        result = remote.run(
            f"tail -c +{offset + 1} {REMOTE_DIR}/{run_id}/output.log 2>/dev/null;"
            f" test -f {REMOTE_DIR}/{run_id}/rc && echo @@RC@@ && cat {REMOTE_DIR}/{run_id}/rc",
            capture=True,
            check=False,
        )
        chunk, marker, rc = result.stdout.partition(b"@@RC@@")
        sys.stdout.write(chunk.decode(errors="replace"))
        sys.stdout.flush()
        offset += len(chunk)
        if marker:
            return int(rc.strip())
        time.sleep(1)


def cmd_test(remote: Remote, options: Options) -> None:
    if not options.no_sync:
        cmd_sync(remote, options)
    run_id = datetime.now().strftime("%Y%m%d-%H%M%S")
    workdir = SUITES[options.suite]
    pytest = shlex.join(
        [
            "python3",
            "-m",
            "pytest",
            "-p",
            "no:cacheprovider",
            "-rfEs",
            f"--junit-xml=/tmp/agent-vm-test-{run_id}.xml",
            *options.pytest_args,
        ]
    )
    log(f"Run {run_id}: {options.suite}: {shlex.join(options.pytest_args) or '(all tests)'}")
    remote.run(
        f"""
mkdir -p {REMOTE_DIR}/{run_id}
cat > {REMOTE_DIR}/{run_id}/run.sh <<'EOF'
docker exec -w {workdir} {API_CONTAINER} {pytest} > {REMOTE_DIR}/{run_id}/output.log 2>&1
rc=$?
docker cp {API_CONTAINER}:/tmp/agent-vm-test-{run_id}.xml {REMOTE_DIR}/{run_id}/junit.xml 2>/dev/null
echo $rc > {REMOTE_DIR}/{run_id}/rc
EOF
nohup bash {REMOTE_DIR}/{run_id}/run.sh >/dev/null 2>&1 &
"""
    )
    rc = follow(remote, run_id)
    out = fetch_results(remote, run_id, ["output.log", "junit.xml"])
    log(f"Exit code {rc}. Results: {out.relative_to(REPO)}")
    raise SystemExit(rc)


def cmd_host_test(remote: Remote, options: Options) -> None:
    run_id = datetime.now().strftime("%Y%m%d-%H%M%S") + "-host"
    files = shlex.join(options.files)
    log(f"Run {run_id}: host-side ucs-test: {files}")
    remote.run(
        f"""
if ! test -d /usr/share/ucs-test/94_ucsschool-kelvin; then
    echo "ucs-test-ucsschool-kelvin not installed: run prepare --ucs-test" >&2
    exit 1
fi
mkdir -p {REMOTE_DIR}/{run_id}
cat > {REMOTE_DIR}/{run_id}/run.sh <<'EOF'
cd /usr/share/ucs-test/94_ucsschool-kelvin
pytest-3 -l -v -p no:cacheprovider --junit-xml={REMOTE_DIR}/{run_id}/junit.xml {files} \
    > {REMOTE_DIR}/{run_id}/output.log 2>&1
echo $? > {REMOTE_DIR}/{run_id}/rc
EOF
nohup bash {REMOTE_DIR}/{run_id}/run.sh >/dev/null 2>&1 &
"""
    )
    rc = follow(remote, run_id)
    out = fetch_results(remote, run_id, ["output.log", "junit.xml"])
    log(f"Exit code {rc}. Results: {out.relative_to(REPO)}")
    raise SystemExit(rc)


def cmd_revert(remote: Remote, _options: Options) -> None:
    tag = release_tag(remote)
    log(f"Restoring the original images ({tag}) and reinitializing the app...")
    remote.run(
        f"""
set -e
for image in {API_IMAGE} {CONNECTOR_IMAGE}; do
    if ! docker image inspect "$image{ORIG_SUFFIX}:{tag}" >/dev/null 2>&1; then
        echo "No original image for $image" >&2
        exit 1
    fi
    docker tag "$image{ORIG_SUFFIX}:{tag}" "$image:{tag}"
done
{REINITIALIZE}
{WAIT_FOR_KELVIN}
"""
    )
    log("Reverted.")


def main() -> None:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument(
        "--host", default=os.environ.get("KELVIN_TEST_VM"), help="the UCS VM (KELVIN_TEST_VM)"
    )
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("check", help="show the state of the VM")
    prepare = sub.add_parser("prepare", help="one-time test setup on the VM")
    prepare.add_argument("--ucs-test", action="store_true", help="also install the ucs-test packages")
    sub.add_parser("deploy", help="build and deploy the images from the working tree")
    sync = sub.add_parser("sync", help="copy sources into the containers and reload Kelvin")
    sync.add_argument("--no-connector", action="store_true", help="don't sync and restart the connector")
    test = sub.add_parser("test", help="sync, then run pytest in the Kelvin container")
    test.add_argument("--suite", choices=SUITES, default="kelvin-api", help="pytest working directory")
    test.add_argument("--no-sync", action="store_true", help="run against what is in the container")
    test.add_argument("--no-connector", action="store_true", help="don't sync and restart the connector")
    test.add_argument("pytest_args", nargs=argparse.REMAINDER, help="arguments for pytest, after --")
    host_test = sub.add_parser("host-test", help="run host-side ucs-test files with pytest-3")
    host_test.add_argument("files", nargs="+", help="files in /usr/share/ucs-test/94_ucsschool-kelvin")
    sub.add_parser("revert", help="switch the app back to its original images")
    values: dict[str, object] = vars(parser.parse_args())
    host = values["host"]
    if not isinstance(host, str) or not host:
        parser.error("no VM given: use --host or set KELVIN_TEST_VM")

    def strings(name: str) -> list[str]:
        value = values.get(name)
        return [str(item) for item in cast(list[object], value)] if isinstance(value, list) else []

    pytest_args = strings("pytest_args")
    options = Options(
        ucs_test=values.get("ucs_test") is True,
        no_connector=values.get("no_connector") is True,
        no_sync=values.get("no_sync") is True,
        suite=str(values.get("suite") or "kelvin-api"),
        pytest_args=pytest_args[1:] if pytest_args[:1] == ["--"] else pytest_args,
        files=strings("files"),
    )
    commands: dict[str, Callable[[Remote, Options], None]] = {
        "check": cmd_check,
        "prepare": cmd_prepare,
        "deploy": cmd_deploy,
        "sync": cmd_sync,
        "test": cmd_test,
        "host-test": cmd_host_test,
        "revert": cmd_revert,
    }
    commands[str(values["command"])](Remote(host), options)


if __name__ == "__main__":
    main()
