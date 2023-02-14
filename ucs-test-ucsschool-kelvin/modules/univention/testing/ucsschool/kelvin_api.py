# -*- coding: utf-8 -*-
#
# Univention UCS@school
#
# Copyright 2019-2023 Univention GmbH
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

"""
Test base code.
"""

from __future__ import unicode_literals

import datetime
import inspect
import json
import logging
import os
import pprint
import random
import shutil
import subprocess
import sys
import time
import uuid
from typing import Any, Callable, Dict, List, Optional, Text, Tuple  # noqa: F401
from unittest import TestCase
from urllib.parse import urljoin

import requests
from urllib3.exceptions import InsecureRequestWarning

import univention.testing.strings as uts
import univention.testing.ucsschool.ucs_test_school as utu
from ucsschool.importer.configuration import Configuration, setup_configuration as _setup_configuration
from ucsschool.importer.exceptions import UcsSchoolImportError
from ucsschool.importer.factory import setup_factory as _setup_factory
from ucsschool.importer.frontend.user_import_cmdline import (
    UserImportCommandLine as _UserImportCommandLine,
)
from ucsschool.importer.models.import_user import (
    ImportStaff,
    ImportStudent,
    ImportTeacher,
    ImportTeachersAndStaff,
    ImportUser,
)
from ucsschool.lib.models.group import SchoolClass
from ucsschool.lib.models.utils import get_stream_handler, ucr
from univention.config_registry import handler_set
from univention.testing.ucsschool.importusers_cli_v2 import ImportTestbase

IMPORT_CONFIG = {
    "active": "/var/lib/ucs-school-import/configs/user_import.json",
    "bak": "/var/lib/ucs-school-import/configs/user_import.json.bak.{}".format(
        datetime.datetime.now().strftime("%Y-%m-%d_%H:%M:%S")
    ),
    "default": "/usr/share/ucs-school-import/configs/ucs-school-testuser-http-import.json",
}
APP_ID = "ucsschool-kelvin-rest-api"
URL_BASE_PATH = "/ucsschool/kelvin/v1/"
_localhost_root_url = "https://{}.{}{}".format(ucr["hostname"], ucr["domainname"], URL_BASE_PATH)
API_ROOT_URL = ucr.get("tests/ucsschool/http-api/root_url", _localhost_root_url).rstrip("/") + "/"
OPENAPI_JSON_URL = urljoin(API_ROOT_URL, "openapi.json")
RESOURCE_URLS = {
    "roles": urljoin(API_ROOT_URL, "roles/"),
    "schools": urljoin(API_ROOT_URL, "schools/"),
    "users": urljoin(API_ROOT_URL, "users/"),
    "workgroups": urljoin(API_ROOT_URL, "workgroups/"),
}
KELVIN_TOKEN_URL = API_ROOT_URL.replace("/v1/", "/token")
HTTP_502_ERRORS = []
_ucs_school_import_framework_initialized = False
_ucs_school_import_framework_error = None
requests.packages.urllib3.disable_warnings(category=InsecureRequestWarning)
logger = logging.getLogger("univention.testing.ucsschool")


print("*** API_ROOT_URL={!r} ***".format(API_ROOT_URL))
print("*** OPENAPI_JSON_URL={!r} ***".format(OPENAPI_JSON_URL))
print("*** KELVIN_TOKEN_URL={!r} ***".format(KELVIN_TOKEN_URL))
print("*** RESOURCE_URLS={!r} ***".format(RESOURCE_URLS))


def setup_logging():
    # set log level on loggers we're interested in
    for _name in (
        None,
        "requests",
        "univention",
        "ucsschool",
    ):
        logger = logging.getLogger(_name)
        logger.setLevel(logging.DEBUG)
    # capture output of root logger
    logger = logging.getLogger()
    handler = get_stream_handler(logging.DEBUG)
    logger.addHandler(handler)


setup_logging()


class InitialisationError(Exception):
    pass


class HttpApiUserTestBase(TestCase):
    mapped_udm_properties = [
        "description",
        "gidNumber",
        "employeeType",
        "organisation",
        "phone",
        "title",
        "uidNumber",
    ]  # keep in sync with kelvin-api/tests/conftest.py::MAPPED_UDM_PROPERTIES
    # until the import configuration can be set / bind mounted into the container
    ucrvs2set = []
    should_restart_api_server = True
    logger = logging.getLogger("univention.testing.ucsschool")

    @classmethod
    def setUpClass(cls):
        cls.set_up_import_config()
        cls.import_config = init_ucs_school_import_framework()
        cls.logger.info("*** Initialized import framework.")
        cls.itb = ImportTestbase()
        cls.itb.ou_C = None
        # cls.itb.use_ou_cache = False
        cls.itb.setup_testenv(utu.UCSTestSchool())
        cls.itb.create_ous(cls.itb.schoolenv)
        cls.schoolenv = cls.itb.schoolenv
        cls.lo = cls.itb.lo
        cls.ucr = cls.itb.ucr
        cls.auth_headers = {"Authorization": "{} {}".format(*cls.get_token())}
        logger("*** auth_headers={!r}".format(cls.auth_headers))
        handler_set(cls.ucrvs2set)
        if cls.should_restart_api_server:
            # for testing through HTTP (using WSGI directly not affected)
            cls.restart_api_server()

    @classmethod
    def tearDownClass(cls):
        cls.itb.cleanup()
        cls.revert_import_config()
        if cls.should_restart_api_server:
            cls.restart_api_server()

    @classmethod
    def get_token(cls):  # type: () -> Tuple[str, str]
        resp = requests.post(
            KELVIN_TOKEN_URL, data={"username": "Administrator", "password": "univention"}
        )
        if resp.ok:
            res = resp.json()
            logger.info("*** Got a token via HTTP from the Kelvin API. ***")
            return res["token_type"], res["access_token"]
        else:
            raise RuntimeError(
                "Failed retrieving token from Kelvin API at {!r}: ({!r}) {!r}".format(
                    resp.url, resp.status_code, resp.reason
                )
            )

    @classmethod
    def set_up_import_config(cls):
        logger.info("*** HttpApiUserTestBase.set_up_import_config()")
        # set_up_import_config()
        # return
        if os.path.exists(IMPORT_CONFIG["active"]):
            logger.info("Moving %r to %r.", IMPORT_CONFIG["active"], IMPORT_CONFIG["bak"])
            shutil.move(IMPORT_CONFIG["active"], IMPORT_CONFIG["bak"])
            config_file = IMPORT_CONFIG["bak"]
        else:
            config_file = IMPORT_CONFIG["default"]
        with open(config_file, "r") as fp:
            config = json.load(fp)
        config["configuration_checks"] = ["defaults", "mapped_udm_properties"]
        config["mapped_udm_properties"] = cls.mapped_udm_properties
        config["scheme"] = {
            "firstname": "<lastname>",
            "username": {"default": "<:lower>test.<firstname>[:2].<lastname>[:3]"},
        }
        config["source_uid"] = "TESTID"
        config["verbose"] = True
        with open(IMPORT_CONFIG["active"], "w") as fp:
            json.dump(config, fp, indent=4)
        logger.info("Wrote config to %r: %r", IMPORT_CONFIG["active"], config)

    @classmethod
    def revert_import_config(cls):
        if os.path.exists(IMPORT_CONFIG["bak"]):
            logger.info("Moving %r to %r.", IMPORT_CONFIG["bak"], IMPORT_CONFIG["active"])
            shutil.move(IMPORT_CONFIG["bak"], IMPORT_CONFIG["active"])
        else:
            logger.info("Removing %r.", IMPORT_CONFIG["active"])
            os.remove(IMPORT_CONFIG["active"])

    def compare_import_user_and_resource(self, import_user, resource, source="LDAP"):
        # type: (ImportUser, Dict[Text, Any], Optional[Text]) -> None
        self.logger.info("*** import_user (%s): %r", source, import_user.to_dict())
        self.logger.info("*** resource: %r", resource)
        dn = import_user.dn
        for k, v in resource.items():
            if k == "url":
                continue
            elif k == "dn":
                self.assertEqual(dn, v, "Expected DN {!r} got {!r}.".format(dn, v))
            elif k == "school":
                response = requests.get(v, headers=self.auth_headers)
                self.assertEqual(
                    response.status_code,
                    200,
                    "response.status_code = {} for URL {!r} -> {!r}".format(
                        response.status_code, response.url, response.text
                    ),
                )
                obj = response.json()
                self.assertEqual(
                    obj.get("name"),
                    import_user.school,
                    "Value of attribute {!r} in {} is {!r} and in resource is {!r} -> {!r} "
                    "({!r}).".format(k, source, import_user.school, v, obj.get("name"), dn),
                )
            elif k == "schools":
                objs = []
                for url in v:
                    response = requests.get(url, headers=self.auth_headers)
                    self.assertEqual(
                        response.status_code,
                        200,
                        "response.status_code = {} for URL {!r} -> {!r}".format(
                            response.status_code, response.url, response.text
                        ),
                    )
                    objs.append(response.json())
                school_names = set(obj.get("name") for obj in objs)
                self.assertEqual(
                    school_names,
                    set(import_user.schools),
                    "Value of attribute {!r} in {} is {!r} and in resource is {!r} -> {!r} "
                    "({!r}).".format(k, source, import_user.schools, v, school_names, dn),
                )
            elif k == "disabled":
                self.assertIn(v, (True, False), "Value of {!r} is {!r}.".format(k, v))
                val = "1" if v is True else "0"
                self.assertEqual(
                    val,
                    import_user.disabled,
                    "Value of attribute {!r} in {} is {!r} and in resource is {!r} -> {!r} "
                    "({!r}).".format(k, source, import_user.disabled, v, val, dn),
                )
            elif k == "roles":
                objs = []
                for url in v:
                    response = requests.get(url, headers=self.auth_headers)
                    self.assertEqual(
                        response.status_code,
                        200,
                        "response.status_code = {} for URL {!r} -> {!r}".format(
                            response.status_code, response.url, response.text
                        ),
                    )
                    objs.append(response.json())
                role_names = set(
                    "pupil" if obj.get("name") == "student" else obj.get("name") for obj in objs
                )
                self.assertEqual(
                    role_names,
                    set(import_user.roles),
                    "Value of attribute {!r} in {} is {!r} and in resource is {!r} -> {!r} "
                    "({!r}).".format(k, source, import_user.roles, v, role_names, dn),
                )
            elif k == "school_classes":
                if source == "LDAP":
                    val = dict(
                        (school, ["{}-{}".format(school, kls) for kls in classes])
                        for school, classes in v.items()
                    )
                else:
                    val = v
                msg = (
                    "Value of attribute {!r} in {} is {!r} and in resource is "
                    "v={!r} -> val={!r} ({!r}).".format(k, source, getattr(import_user, k), v, val, dn)
                )
                self.assertDictEqual(getattr(import_user, k), val, msg)
            elif k == "udm_properties":
                # Could be the same test as for 'school_classes', but lists are not necessarily in
                # order (for example phone, e-mail, etc), so converting them to sets:
                self.assertSetEqual(set(import_user.udm_properties.keys()), set(v.keys()))
                udm_properties = empty_str2none(import_user.udm_properties)
                for udm_k, udm_v in udm_properties.items():
                    msg = "Value of attribute {!r} in {} is {!r} and in resource is {!r} ({!r}).".format(
                        k, source, getattr(import_user, k), v, dn
                    )
                    if isinstance(udm_v, list):
                        self.assertSetEqual(set(udm_v), set(v[udm_k]), msg)
                    elif isinstance(udm_v, dict):
                        self.assertDictEqual(udm_v, v[udm_k], msg)
                    else:
                        self.assertEqual(udm_v, v[udm_k], msg)
            elif getattr(import_user, k) is None and v == "":
                continue
            else:
                if isinstance(v, list):
                    import_user_val = set(getattr(import_user, k))
                    resource_val = set(v)
                else:
                    import_user_val = getattr(import_user, k)
                    resource_val = v
                self.assertEqual(
                    import_user_val,
                    resource_val,
                    "Value of attribute {!r} in {} is {!r} and in resource is {!r} ({!r}).".format(
                        k, source, getattr(import_user, k), v, dn
                    ),
                )

    def make_user_attrs(self, ous, partial=False, **kwargs):
        # type: (List[Text], Optional[bool], **Any) -> Dict[Text, Any]
        roles = kwargs.pop("roles", None) or random.choice(  # nosec
            (("staff",), ("staff", "teacher"), ("student",), ("teacher",))
        )
        res = {
            "name": "test{}".format(uts.random_username()),
            "birthday": "19{}-0{}-{}{}".format(
                2 * uts.random_int(), uts.random_int(1, 9), uts.random_int(0, 2), uts.random_int(1, 8)
            ),
            "disabled": random.choice((True, False)),  # nosec
            "email": "{}@{}".format(uts.random_username(), self.itb.maildomain),
            "firstname": uts.random_username(),
            "lastname": uts.random_username(),
            "password": uts.random_username(16),
            "record_uid": uts.random_username(),
            "roles": [urljoin(RESOURCE_URLS["roles"], role) for role in roles],
            "school": urljoin(RESOURCE_URLS["schools"], sorted(ous)[0]),
            "school_classes": {}
            if roles == ("staff",)
            else dict(
                (ou, sorted([uts.random_username(4), uts.random_username(4)])) for ou in sorted(ous)
            ),
            "schools": [urljoin(RESOURCE_URLS["schools"], ou) for ou in sorted(ous)],
            "source_uid": self.import_config["source_uid"],
            "udm_properties": {
                "phone": [uts.random_username(), uts.random_username()],
                "organisation": uts.random_username(),
            },
        }
        assert all(len(set(kl)) == 2 for kl in res["school_classes"].values())
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
            random.shuffle(removable_attrs)  # nosec
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
            [
                urljoin(RESOURCE_URLS["schools"], ou) in res.get("schools", [])
                for ou in res.get("school_classes", {})
            ]
        )
        res.update(kwargs)
        return res

    @classmethod
    def restart_api_server(cls):
        cmd = [
            "/usr/bin/univention-app",
            "shell",
            APP_ID,
            "/etc/init.d/ucsschool-kelvin-rest-api",
            "restart",
        ]
        cls.logger.info("*** Restarting Kelvin API server: %r", cmd)
        subprocess.call(cmd)  # nosec
        while True:
            time.sleep(0.5)
            response = requests.get("{}/foobar".format(API_ROOT_URL))
            if response.status_code == 404:
                break
        # else: 502 Proxy Error
        cls.logger.info("*** done.")

    @staticmethod
    def get_class_dn(class_name, school, lo):
        # copied from models.user as static version
        school_class = SchoolClass.cache(class_name, school)
        if school_class.get_relative_name() == school_class.name:
            if not school_class.exists(lo):
                class_name = "%s-%s" % (school, class_name)
                school_class = SchoolClass.cache(class_name, school)
        return school_class.dn

    def extract_class_dns(self, attrs):
        school_class_objs = []
        for school, school_classes in attrs.get("school_classes", {}).items():
            school_class_objs.extend(SchoolClass.cache(sc, school) for sc in school_classes)
        return [self.get_class_dn(sc.name, sc.school, self.lo) for sc in school_class_objs]

    def get_import_user(self, dn, school=None):  # type: (str, Optional[str]) -> ImportUser
        user = ImportUser.from_dn(dn, school, self.lo)
        udm_obj = user.get_udm_object(self.lo)
        user.udm_properties = dict((k, udm_obj[k]) for k in self.import_config["mapped_udm_properties"])
        return user

    def create_import_user(self, **kwargs):  # type: (**Any) -> ImportUser
        kls = random.choice((ImportStaff, ImportStudent, ImportTeacher, ImportTeachersAndStaff))  # nosec
        obj = kls(**kwargs)
        res = obj.create(self.lo)
        if not res:
            self.fail("Creating {!r} failed with kwargs {!r}".format(kls, kwargs))
        return obj


def retry_http_502(request_method, *args, **kwargs):
    # type: (Callable[..., requests.Response], *Any, **Any) -> requests.Response
    retries = 5
    while retries > 0:
        response = request_method(*args, **kwargs)
        if response.status_code == 502:
            caller = inspect.stack()[1][3]
            msg = "=> HTTP 502 #{} in {}() by request.{}({}, {})".format(
                len(HTTP_502_ERRORS) + 1,
                caller,
                request_method.__name__,
                ", ".join(repr(a) for a in args),
                ", ".join("{!r}={!r}".format(k, v) for k, v in kwargs.items()),
            )
            HTTP_502_ERRORS.append(msg)
            logger.info(msg)
            retries -= 1
            time.sleep(2)
            continue
        return response


def api_call(method, url, auth=None, headers=None, json_data=None):
    # type: (Text, Text, Optional[Any], Optional[Dict[Text, Any]], Optional[Dict[Text, Any]]) -> Dict[Text, Any]  # noqa: E501
    pid = os.getpid()
    req_id = uuid.uuid4()
    HttpApiUserTestBase.logger.debug(
        "*** [%r] method=%r url=%r json_data=%r (%s)", pid, method, url, json_data, req_id
    )
    meth = getattr(requests, method)
    response = retry_http_502(meth, url, auth=auth, headers=headers, json=json_data)
    if response.status_code >= 400:
        log = HttpApiUserTestBase.logger.error
    else:
        log = HttpApiUserTestBase.logger.debug
    log("*** [%r] status_code=%r reason=%r (%s)", pid, response.status_code, response.reason, req_id)
    if hasattr(response, "json"):
        try:
            res = response.json() if callable(response.json) else response.json
        except ValueError as exc:
            HttpApiUserTestBase.logger.exception(
                "*** [%r] (%s) ValueError (%s) decoding response.text=%r",
                pid,
                req_id,
                exc,
                response.text,
            )
            raise
    else:
        res = response.reason
    HttpApiUserTestBase.logger.debug("*** [%r] res=%r", pid, res)
    return res


def create_remote_static(attribs):
    # type: (Tuple[Dict[Text, Text], Dict[Text, Any]]) -> Dict[Text, Any]
    auth_headers, attrs = attribs
    return api_call("post", RESOURCE_URLS["users"], json_data=attrs, headers=auth_headers)


def partial_update_remote_static(old_username_and_new_attrs):
    # type: (Tuple[Dict[Text, Text], Text, Dict[Text, Any]]) -> Dict[Text, Any]
    auth_headers, old_username, new_attrs = old_username_and_new_attrs
    url = urljoin(RESOURCE_URLS["users"], old_username)
    return api_call("patch", url, json_data=new_attrs, headers=auth_headers)


def init_ucs_school_import_framework(**config_kwargs):
    global _ucs_school_import_framework_initialized, _ucs_school_import_framework_error

    if _ucs_school_import_framework_initialized:
        return Configuration()
    if _ucs_school_import_framework_error:
        # prevent "Changing the configuration is not allowed." error if we
        # return here after raising an InitialisationError
        raise _ucs_school_import_framework_error

    _config_args = {
        "dry_run": False,
        "logfile": "/var/log/univention/ucsschool-kelvin-rest-api/http.log",
        "skip_tests": ["uniqueness"],
    }
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


def empty_str2none(udm_props):  # type: (Dict[str, Any]) -> Dict[str, Any]
    res = {}
    for k, v in udm_props.items():
        if isinstance(v, dict):
            res[k] = empty_str2none(v)
        elif isinstance(v, list):
            res[k] = [None if vv == "" else vv for vv in v]
        else:
            if v == "":
                res[k] = None
    return res
