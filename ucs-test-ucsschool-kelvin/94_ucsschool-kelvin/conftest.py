import datetime
import json
import logging
import os.path
import pprint
import random
import shutil
import sys
import time
from typing import TYPE_CHECKING, Any, Dict, List, Optional  # noqa: F401
from urllib.parse import urljoin

import pytest
import requests

from ucsschool.lib.models.utils import exec_cmd
from univention.testing.ucsschool.kelvin_api import HTTP_502_ERRORS, KELVIN_TOKEN_URL, RESOURCE_URLS

if TYPE_CHECKING:
    from ucsschool.importer.models.import_user import ImportUser  # noqa: F401

pytest_plugins = ["univention.testing.ucsschool.conftest"]
logger = logging.getLogger("univention.testing.ucsschool")

APP_ID = "ucsschool-kelvin-rest-api"
IMPORT_CONFIG = {
    "active": "/var/lib/ucs-school-import/configs/user_import.json",
    "bak": f"/var/lib/ucs-school-import/configs/user_import.json.bak"
    f'.{datetime.datetime.now().strftime("%Y-%m-%d_%H:%M:%S")}',
    "default": "/usr/share/ucs-school-import/configs/ucs-school-testuser-http-import.json",
}
MAPPED_UDM_PROPERTIES = (
    "title",
    "description",
    "displayName",
    "e-mail",
    "employeeType",
    "organisation",
    "phone",
    "uidNumber",
    "gidNumber",
)  # keep in sync with [ucs-repo(4.4|5.0)]/test/utils/ucsschool_id_connector.py
# if changed: check kelvin-api/tests/test_route_user.test_search_filter_udm_properties()
IMPORT_CONFIG_KWARGS = {
    "configuration_checks": ["defaults", "mapped_udm_properties"],
    "dry_run": False,
    "logfile": "/var/log/univention/ucsschool-kelvin-rest-api/http.log",
    "scheme": {
        "firstname": "<lastname>",
        "username": {"default": "<:lower>test.<firstname>[:2].<lastname>[:3]"},
    },
    "skip_tests": ["uniqueness"],
    "mapped_udm_properties": MAPPED_UDM_PROPERTIES,
    "source_uid": "TESTID",
    "verbose": True,
}
_ucs_school_import_framework_initialized = False
_ucs_school_import_framework_error = None  # type: Optional[InitialisationError]


class InitialisationError(Exception):
    pass


@pytest.fixture(scope="session")
def init_ucs_school_import_framework():
    # ucs-test-ucsschool must not depend on ucs-school-import package
    from ucsschool.importer.configuration import (
        Configuration,
        setup_configuration as _setup_configuration,
    )
    from ucsschool.importer.exceptions import UcsSchoolImportError
    from ucsschool.importer.factory import setup_factory as _setup_factory
    from ucsschool.importer.frontend.user_import_cmdline import (
        UserImportCommandLine as _UserImportCommandLine,
    )

    def _func(**config_kwargs):
        global _ucs_school_import_framework_initialized, _ucs_school_import_framework_error

        if _ucs_school_import_framework_initialized:
            return Configuration()
        if _ucs_school_import_framework_error:
            # prevent "Changing the configuration is not allowed." error if we
            # return here after raising an InitialisationError
            raise _ucs_school_import_framework_error

        _config_args = IMPORT_CONFIG_KWARGS
        _config_args.update(config_kwargs)
        _ui = _UserImportCommandLine()
        _config_files = _ui.configuration_files
        logger = logging.getLogger("univention.testing.ucsschool")
        try:
            config = _setup_configuration(_config_files, **_config_args)
            if "mapped_udm_properties" not in config.get("configuration_checks", []):
                raise UcsSchoolImportError(
                    'Missing "mapped_udm_properties" in configuration checks, e.g.: '
                    '{.., "configuration_checks": ["defaults", "mapped_udm_properties"], ..}'
                )
            _ui.setup_logging(config["verbose"], config["logfile"])
            _setup_factory(config["factory"])
        except UcsSchoolImportError as exc:
            logger.exception("Error initializing UCS@school import framework: %s", exc)
            etype, exc, etraceback = sys.exc_info()
            _ucs_school_import_framework_error = InitialisationError(str(exc))
            raise _ucs_school_import_framework_error
        logger.info("------ UCS@school import tool configured ------")
        logger.info("Used configuration files: %s.", config.conffiles)
        logger.info("Using command line arguments: %r", _config_args)
        logger.info("Configuration is:\n%s", pprint.pformat(config))
        _ucs_school_import_framework_initialized = True
        return config

    return _func


@pytest.fixture(scope="session")
def import_config(init_ucs_school_import_framework):
    return init_ucs_school_import_framework()


def get_access_token(username="Administrator", password="univention"):  # type: (str, str) -> str # nosec
    response = requests.post(
        url=KELVIN_TOKEN_URL,
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        data=dict(username=username, password=password),
    )
    assert response.status_code == 200, repr(response.__dict__)
    response_json = response.json()
    return response_json["access_token"]


@pytest.fixture(scope="session")
def auth_header():  # type: () -> Dict[str, str]
    token = get_access_token()
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture(scope="session")
def delete_ou(ucr_ldap_base):
    def _func(ou_name):  # type: (str) -> None
        print("Deleting OU {!r}...".format(ou_name))
        dn = "ou={},{}".format(ou_name, ucr_ldap_base)
        retries = 2
        while retries > 0:
            _, stdout, _ = exec_cmd(["/usr/sbin/udm", "container/ou", "remove", "--dn", dn], log=True)
            if "Operation not allowed on non-leaf" in stdout:
                retries -= 1
            else:
                break

    return _func


@pytest.fixture(scope="session")
def make_user_attrs(import_config, mail_domain, random_int, random_username):
    def _func(ous, partial=False, **kwargs):
        # type: (List[str], Optional[bool], **Any) -> Dict[str, Any]
        roles = kwargs.pop("roles", None) or random.choice(  # nosec
            (("staff",), ("staff", "teacher"), ("student",), ("teacher",), ("legal_guardian",))
        )
        if roles == ("staff",):
            school_classes = {}
        else:
            school_classes = {ou: sorted([random_username(4), random_username(4)]) for ou in sorted(ous)}
        res = {
            "name": "test{}".format(random_username()),
            "birthday": "19{}-0{}-{}{}".format(
                2 * random_int(), random_int(1, 9), random_int(0, 2), random_int(1, 8)
            ),
            "disabled": random.choice((True, False)),  # nosec
            "email": "{}@{}".format(random_username(), mail_domain),
            "firstname": random_username(),
            "lastname": random_username(),
            "password": random_username(64),
            "record_uid": random_username(),
            "roles": [urljoin(RESOURCE_URLS["roles"], role) for role in roles],
            "school": urljoin(RESOURCE_URLS["schools"], sorted(ous)[0]),
            "school_classes": school_classes,
            "schools": [urljoin(RESOURCE_URLS["schools"], ou) for ou in sorted(ous)],
            "source_uid": import_config["source_uid"],
            "udm_properties": {
                "phone": [random_username(), random_username()],
                "organisation": random_username(),
            },
        }
        if partial:
            # remove all but n attributes
            num_attrs = random.randint(1, 5)  # nosec
            removable_attrs = [
                "birthday",
                "disabled",
                "email",
                "firstname",
                "lastname",
                "password",
                "record_uid",
                "school",
                "school_classes",
                "schools",
                "source_uid",
            ]
            random.shuffle(removable_attrs)
            schools = res["schools"]
            for k in list(res):
                if k not in removable_attrs[:num_attrs]:
                    del res[k]
            if len(res.get("school_classes", {})) != 1 and "schools" not in res:
                # Prevent "School '...' in 'school_classes' is missing in the users 'school(s)'
                # attributes."
                # Case 1: "school_classes" not in res
                #         -> No 'school_classes' means: don't change existing school_classes. Thus, the
                #            OUs in school_classes.keys() must be kept.
                # Case 2: more than one OU in school_classes
                #         -> 'schools' must contain all OUs
                res["schools"] = schools
        assert all(
            urljoin(RESOURCE_URLS["schools"], ou) in res.get("schools", [])
            for ou in res.get("school_classes", {})
        )
        if "student" in roles:
            res["legal_guardians"] = []
        elif "legal_guardian" in roles:
            res["legal_wards"] = []
        res.update(kwargs)
        return res

    return _func


def empty_str2none(udm_props):  # type: (Dict[str, Any]) -> Dict[str, Any]
    res = {}
    for k, v in udm_props.items():
        if isinstance(v, dict):
            res[k] = empty_str2none(v)
        elif isinstance(v, list):
            res[k] = [None if vv == "" else vv for vv in v]
        elif v == "":
            res[k] = None
    return res


@pytest.fixture(scope="session")
def compare_import_user_and_resource(auth_header):
    def _func(import_user, resource, source="LDAP"):
        # type: (ImportUser, Dict[str, Any], Optional[str]) -> None
        logger.info("*** import_user (%s): %r", source, import_user.to_dict())
        logger.info("*** resource: %r", resource)
        dn = import_user.dn
        for k, v in resource.items():
            if k == "url":
                continue
            elif k == "dn":
                assert dn == v, "Expected DN {!r} got {!r}.".format(dn, v)
            elif k == "school":
                assert v == urljoin(RESOURCE_URLS["schools"], import_user.school)
            elif k == "schools":
                assert set(v) == {urljoin(RESOURCE_URLS["schools"], s) for s in import_user.schools}
            elif k == "disabled":
                assert v in (True, False), "Value of {!r} is {!r}.".format(k, v)
                val = "1" if v is True else "0"
                assert val == import_user.disabled, (
                    "Value of attribute {!r} in {} is {!r} and in resource is {!r} -> {!r} "
                    "({!r}).".format(k, source, import_user.disabled, v, val, dn),
                )
            elif k == "roles":
                import_user_roles = {"student" if r == "pupil" else r for r in import_user.roles}
                assert set(v) == {urljoin(RESOURCE_URLS["roles"], r) for r in import_user_roles}
            elif k == "school_classes":
                if source == "LDAP":
                    val = {
                        school: ["{}-{}".format(school, kls) for kls in classes]
                        for school, classes in v.items()
                    }
                else:
                    val = v
                msg = (
                    "Value of attribute {!r} in {} is {!r} and in resource is "
                    "v={!r} -> val={!r} ({!r}).".format(k, source, getattr(import_user, k), v, val, dn)
                )
                assert getattr(import_user, k) == val, msg
            elif k == "udm_properties":
                # Could be the same test as for 'school_classes', but lists are not necessarily in
                # order (for example phone, e-mail, etc), so converting them to sets:
                assert set(import_user.udm_properties.keys()) == set(v.keys())
                udm_properties = empty_str2none(import_user.udm_properties)
                for udm_k, udm_v in udm_properties.items():
                    msg = "Value of attribute {!r} in {} is {!r} and in resource is {!r} ({!r}).".format(
                        k, source, getattr(import_user, k), v, dn
                    )
                    if isinstance(udm_v, list):
                        assert set(udm_v) == set(v[udm_k]), msg
                    elif isinstance(udm_v, dict):
                        assert udm_v == v[udm_k], msg
                    else:
                        assert udm_v == v[udm_k], msg
            elif getattr(import_user, k) is None and v == "":
                continue
            else:
                if isinstance(v, list):
                    import_user_val = set(getattr(import_user, k))
                    resource_val = set(v)
                else:
                    import_user_val = getattr(import_user, k)
                    resource_val = v
                assert (
                    import_user_val == resource_val
                ), "Value of attribute {!r} in {} is {!r} and in resource is {!r} ({!r}).".format(
                    k, source, getattr(import_user, k), v, dn
                )

    return _func


def restart_kelvin_api_server():  # type: () -> None
    cmd = [
        "/usr/bin/univention-app",
        "restart",
        APP_ID,
    ]
    logger.info("*** Restarting Kelvin API server: %r", cmd)
    exec_cmd(cmd, log=True)
    while True:
        time.sleep(0.5)
        try:
            get_access_token()
            break
        except AssertionError:
            # Kelvin API not ready -> 502 Proxy Error
            pass
    logger.info("*** done.")


@pytest.fixture(scope="session")
def add_to_import_config():  # noqa: C901
    def _func(**kwargs):
        if os.path.exists(IMPORT_CONFIG["active"]):
            logger.info("Checking if %r contains %r...", IMPORT_CONFIG["active"], kwargs)
            restart = False
            with open(IMPORT_CONFIG["active"], "r") as fp:
                config = json.load(fp)
            for k, v in kwargs.items():
                if isinstance(v, list):
                    new_value = set(v)
                    old_value = set(config.get(k, []))
                    if not new_value.issubset(old_value):
                        restart = True
                else:
                    new_value = v
                    old_value = config.get(k)
                    if old_value != new_value:
                        restart = True
            if not restart:
                logger.info("Not restarting server, import config already contains: %r", kwargs)
                return
            if not os.path.exists(IMPORT_CONFIG["bak"]):
                logger.info("Moving %r to %r.", IMPORT_CONFIG["active"], IMPORT_CONFIG["bak"])
                shutil.move(IMPORT_CONFIG["active"], IMPORT_CONFIG["bak"])
            config.update(kwargs)
        else:
            config = kwargs
        with open(IMPORT_CONFIG["active"], "w") as fp:
            json.dump(config, fp, indent=4)
        logger.info("Wrote config to %r: %r", IMPORT_CONFIG["active"], config)
        restart_kelvin_api_server()

    yield _func

    if os.path.exists(IMPORT_CONFIG["bak"]):
        logger.info("Moving %r to %r.", IMPORT_CONFIG["bak"], IMPORT_CONFIG["active"])
        shutil.move(IMPORT_CONFIG["bak"], IMPORT_CONFIG["active"])
        restart_kelvin_api_server()


@pytest.fixture(scope="session")
def setup_import_config(add_to_import_config):
    add_to_import_config(**IMPORT_CONFIG_KWARGS)


@pytest.fixture(autouse=True, scope="session")
def log_http_502_amount():
    log_file = "/tmp/http502.log"  # nosec
    msg = f"{datetime.datetime.now().isoformat()} HTTP 502: {len(HTTP_502_ERRORS)} times"
    print("{}, see {!r}.".format(msg, log_file))
    with open(log_file, "a") as fp:
        fp.write(f"{msg}.\n")
        for msg in HTTP_502_ERRORS:
            fp.write(f"{msg}\n")
