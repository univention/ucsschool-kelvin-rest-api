# Copyright 2020-2021 Univention GmbH
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

import asyncio
import datetime
import itertools
import json
import logging
import random
from typing import Any, Dict, List, NamedTuple, Set, Tuple, Type, Union
from urllib.parse import SplitResult, urlsplit

import pytest
import requests
from conftest import MAPPED_UDM_PROPERTIES
from faker import Faker
from ldap.filter import filter_format
from pydantic import HttpUrl, error_wrappers
from uldap3 import BindError
from uldap3.exceptions import ModifyError as UModifyError, NoObject as UNoObject

import ucsschool.kelvin.constants
import univention.admin.uldap
from ucsschool.importer.models.import_user import ImportUser
from ucsschool.kelvin.ldap import get_dn_of_user
from ucsschool.kelvin.routers.role import SchoolUserRole
from ucsschool.kelvin.routers.user import (
    PasswordsHashes,
    UserCreateModel,
    UserModel,
    UserPatchModel,
    _validate_date_format,
    _validate_date_range,
    fix_case_of_ous,
    set_password_hashes,
    userexpiry_to_shadowExpire,
)
from ucsschool.lib.models.school import School
from ucsschool.lib.models.user import SchoolAdmin, Staff, Student, Teacher, TeachersAndStaff, User
from ucsschool.lib.roles import role_school_admin, role_student
from udm_rest_client import UDM

pytestmark = pytest.mark.skipif(
    not ucsschool.kelvin.constants.CN_ADMIN_PASSWORD_FILE.exists(),
    reason="Must run inside Docker container started by appcenter.",
)

fake = Faker()
random.shuffle(MAPPED_UDM_PROPERTIES)
UserType = Type[Union[Staff, Student, Teacher, TeachersAndStaff, User]]
Role = NamedTuple("Role", [("name", str), ("klass", UserType)])
USER_ROLES: List[Role] = [
    Role("staff", Staff),
    Role("student", Student),
    Role("teacher", Teacher),
    Role("teacher_and_staff", TeachersAndStaff),
    Role("school_admin", SchoolAdmin),
]  # User.role_string -> User
random.shuffle(USER_ROLES)
logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)


def role_id(value: Role) -> str:
    return value.name


def two_roles_id(value: List[Role]) -> str:
    return f"{value[0].name} -> {value[1].name}"


def scramble_case(s: str) -> str:
    """`"FooBar"` -> `"FoObAr"`"""
    res = s
    max_iterations = 100  # handle strings without letters
    while res == s and max_iterations > 0:
        res = "".join([random.choice((str.lower, str.upper))(c) for c in res])
        max_iterations -= 1
    return res


async def compare_lib_api_user(  # noqa: C901
    lib_user: ImportUser, api_user: UserModel, udm: UDM, url_fragment: str
) -> None:
    udm_obj = await lib_user.get_udm_object(udm)
    for key, value in api_user.dict().items():
        if key == "school":
            assert value.split("/")[-1] == getattr(lib_user, key)
        elif key == "schools":
            assert len(value) == len(getattr(lib_user, key))
            for entry in value:
                assert entry.split("/")[-1] in getattr(lib_user, key)
        elif key == "url":
            assert api_user.unscheme_and_unquote(value) == f"{url_fragment}/users/{lib_user.name}"
        elif key == "record_uid":
            assert value == udm_obj.props.ucsschoolRecordUID
        elif key == "source_uid":
            assert value == udm_obj.props.ucsschoolSourceUID
        elif key == "udm_properties":
            for prop, prop_val in value.items():
                assert prop_val == getattr(udm_obj.props, prop)
        elif key == "roles":
            api_roles = {role.split("/")[-1] for role in value}
            lib_roles = {SchoolUserRole.from_lib_role(role).value for role in lib_user.ucsschool_roles}
            assert api_roles == lib_roles
        elif key in ("birthday", "expiration_date"):
            if value:
                assert str(value) == getattr(lib_user, key)
            else:
                assert value == getattr(lib_user, key)
        elif key == "school_classes":
            if isinstance(lib_user, Staff):
                assert value == {}
            for school, classes in value.items():
                assert school in lib_user.school_classes
                assert set(classes) == {
                    kls.replace(f"{school}-", "") for kls in lib_user.school_classes[school]
                }
        elif key == "workgroups":
            for school, workgroups in value.items():
                assert school in lib_user.workgroups
                assert set(workgroups) == {
                    wg.replace(f"{school}-", "") for wg in lib_user.workgroups[school]
                }
        else:
            lib_user_value = getattr(lib_user, key)
            if isinstance(value, (list, set, tuple)) or isinstance(lib_user_value, (list, set, tuple)):
                assert set(value) == set(lib_user_value)
            else:
                assert value == lib_user_value


def compare_ldap_json_obj(dn, json_resp, url_fragment):  # noqa: C901
    lo, pos = univention.admin.uldap.getAdminConnection()
    ldap_obj = lo.get(dn)
    for attr, value in json_resp.items():
        if attr == "record_uid" and "ucsschoolRecordUID" in ldap_obj:
            assert value == ldap_obj["ucsschoolRecordUID"][0].decode("utf-8")
        elif attr == "ucsschool_roles" and "ucsschoolRole" in ldap_obj:
            assert set(value) == {r.decode("utf-8") for r in ldap_obj["ucsschoolRole"]}
        elif attr == "email" and "mailPrimaryAddress" in ldap_obj:
            assert value in [o.decode("utf-8") for o in ldap_obj["mail"]]
            assert value in [o.decode("utf-8") for o in ldap_obj["mailPrimaryAddress"]]
        elif attr == "source_uid" and "ucsschoolSourceUID" in ldap_obj:
            assert value == ldap_obj["ucsschoolSourceUID"][0].decode("utf-8")
        elif attr == "birthday" and "univentionBirthday" in ldap_obj:
            assert value == ldap_obj["univentionBirthday"][0].decode("utf-8")
        elif attr == "expiration_date" and "shadowExpire" in ldap_obj:
            if json_resp["disabled"]:
                check_value = "1"
            elif value:
                dt = datetime.datetime.strptime(value, "%Y-%m-%d").date()
                check_value = userexpiry_to_shadowExpire(dt)
            else:
                check_value = "0"
            assert check_value == ldap_obj["shadowExpire"][0].decode("utf-8")
        elif attr == "firstname" and "givenName" in ldap_obj:
            assert value == ldap_obj["givenName"][0].decode("utf-8")
        elif attr == "lastname" and "sn" in ldap_obj:
            assert value == ldap_obj["sn"][0].decode("utf-8")
        elif attr == "school" and "ucsschoolSchool" in ldap_obj:
            assert value.split("/")[-1] in [s.decode("utf-8") for s in ldap_obj["ucsschoolSchool"]]
        elif attr == "udm_properties":
            for k, v in json_resp["udm_properties"].items():
                if k == "organisation" and "o" in ldap_obj:
                    assert v == ldap_obj["o"][0].decode("utf-8")
                    continue
                if k == "phone" and "telephoneNumber" in ldap_obj:
                    for p1, p2 in zip(v, ldap_obj["telephoneNumber"]):
                        assert p1 == p2.decode("utf-8")
                    continue
                if type(v) is str:
                    assert ldap_obj[k][0].decode("utf-8") == v
                if type(v) is int:
                    assert int(ldap_obj[k][0].decode("utf-8")) == v


@pytest.fixture
def import_user_to_create_model_kwargs(url_fragment):
    def _func(user: ImportUser, exclude: List[str] = None) -> Dict[str, Any]:
        user_data = user.to_dict()
        user_data["birthday"] = datetime.date.fromisoformat(user_data["birthday"])
        user_data["expiration_date"] = datetime.date.fromisoformat(user_data["expiration_date"])
        user_data["roles"] = [
            f"{url_fragment}/roles/{SchoolUserRole.from_lib_role(lib_role).value}"
            for lib_role in user_data["ucsschool_roles"]
        ]
        user_data["school_classes"] = {
            k: [klass.split("-", 1)[1] for klass in v] for k, v in user_data["school_classes"].items()
        }
        user_data["workgroups"] = {
            k: [wg.split("-", 1)[1] for wg in v] for k, v in user_data["workgroups"].items()
        }
        user_data["school"] = f"{url_fragment}/schools/{user_data['school']}"
        user_data["schools"] = [f"{url_fragment}/schools/{school}" for school in user_data["schools"]]
        exclude = exclude or []
        for attr in [
            "$dn$",
            "action",
            "display_name",
            "entry_count",
            "in_hook",
            "input_data",
            "objectType",
            "old_user",
            "type",
            "type_name",
        ] + exclude:
            del user_data[attr]
        return user_data

    return _func


def test_validate_date_format():
    _validate_date_format("2000-01-01")

    with pytest.raises(ValueError):
        _validate_date_format("2000-01-01T00:00")

    with pytest.raises(ValueError):
        _validate_date_format("2000-13-01")


def test_validate_date_range():
    _validate_date_range("2000-01-01")

    with pytest.raises(ValueError):
        _validate_date_range("1900-01-01")

    with pytest.raises(ValueError):
        _validate_date_range("3000-01-01")


@pytest.mark.asyncio
async def test_search_no_filter(
    auth_header, retry_http_502, url_fragment, new_school_users, create_ou_using_python, udm_kwargs
):
    ou_name = await create_ou_using_python()
    users: List[User] = await new_school_users(
        ou_name,
        {"student": 2, "teacher": 2, "staff": 2, "teacher_and_staff": 2, "school_admin": 2},
        disabled=False,
    )
    async with UDM(**udm_kwargs) as udm:
        lib_users = await User.get_all(udm, ou_name)
    assert {u.name for u in users}.issubset({u.name for u in lib_users})
    response = retry_http_502(
        requests.get,
        f"{url_fragment}/users/",
        headers=auth_header,
        params={"school": ou_name},
    )
    assert response.status_code == 200, response.reason
    api_users = {data["name"]: UserModel(**data) for data in response.json()}
    assert len(api_users) == len(lib_users)
    assert {u.name for u in users}.issubset(set(api_users.keys()))
    json_resp = response.json()
    async with UDM(**udm_kwargs) as udm:
        for lib_user in lib_users:
            api_user = api_users[lib_user.name]
            await compare_lib_api_user(lib_user, api_user, udm, url_fragment)
            resp = [r for r in json_resp if r["dn"] == api_user.dn][0]
            compare_ldap_json_obj(api_user.dn, resp, url_fragment)


@pytest.mark.asyncio  # noqa: C901
@pytest.mark.parametrize(
    "filter_param",
    (
        "email",
        "record_uid",
        "source_uid",
        "birthday",
        "expiration_date",
        "disabled-true",
        "disabled-false",
        "firstname",
        "lastname",
        "roles_staff",
        "roles_student",
        "roles_teacher",
        "roles_teacher_and_staff",
        # "roles_school_admin",
        "school",
    ),
)
async def test_search_filter(  # noqa: C901
    auth_header,
    retry_http_502,
    url_fragment,
    new_import_user,
    udm_kwargs,
    random_name,
    create_ou_using_python,
    import_config,
    filter_param: str,
):
    ou1_name = await create_ou_using_python()
    ou_name = ou1_name
    if filter_param.startswith("roles_"):
        filter_param, role = filter_param.split("_", 1)
    else:
        role = random.choice(("staff", "student", "teacher", "teacher_and_staff", "school_admin"))
    if filter_param == "source_uid":
        create_kwargs = {"source_uid": random_name()}
    elif filter_param == "disabled-true":
        filter_param = "disabled"
        create_kwargs = {"disabled": True}
    elif filter_param == "disabled-false":
        filter_param = "disabled"
        create_kwargs = {"disabled": False}
    elif filter_param == "school":
        # use 2nd OU from cache, create_ou_using_python() returns a random OU from the cache
        while True:
            ou2_name = await create_ou_using_python()
            if ou1_name != ou2_name:
                break
        ou_name = ou2_name
        create_kwargs = {"schools": [ou1_name, ou2_name]}
    else:
        create_kwargs = {}

    if filter_param == "disabled" and create_kwargs["disabled"]:
        # search does not work for disabled users with an expiry date, bug 55633
        create_kwargs["expiration_date"] = None
    user: ImportUser = await new_import_user(ou_name, role, **create_kwargs)
    assert ou_name == user.school
    assert user.role_string == role
    if filter_param == "school":
        assert ou_name == ou2_name
        assert {school.rsplit("/", 1)[-1] for school in user.schools} == {ou1_name, ou2_name}

    param_value = getattr(user, filter_param)
    if filter_param in ("source_uid", "disabled"):
        assert param_value == create_kwargs[filter_param]
        if filter_param == "disabled":
            param_value = str(param_value).lower()  # True/False -> "true"/"false"
    elif filter_param == "roles":
        param_value = ["student" if p == "pupil" else p for p in param_value]
    elif filter_param == "school":
        param_value = ou2_name

    if filter_param == "roles":
        # list instead of dict for using same key ("roles") twice
        params = [(filter_param, pv) for pv in param_value]
    else:
        params = {filter_param: param_value}
    response = retry_http_502(
        requests.get,
        f"{url_fragment}/users/",
        headers=auth_header,
        params=params,
    )
    assert response.status_code == 200, response.reason
    json_resp = response.json()
    api_users = {
        data["name"]: UserModel(**data) for data in json_resp if data["school"].split("/")[-1] == ou_name
    }
    if filter_param not in ("disabled", "roles", "school"):
        assert len(api_users) == 1
    assert user.name in api_users
    api_user = api_users[user.name]
    async with UDM(**udm_kwargs) as udm:
        await compare_lib_api_user(user, api_user, udm, url_fragment)
    resp = [r for r in json_resp if r["dn"] == api_user.dn][0]
    compare_ldap_json_obj(api_user.dn, resp, url_fragment)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "filter_param",
    MAPPED_UDM_PROPERTIES,
)
async def test_search_filter_udm_properties(
    auth_header,
    create_ou_using_python,
    retry_http_502,
    url_fragment,
    new_import_user,
    mail_domain,
    import_config,
    udm_kwargs,
    random_name,
    filter_param: str,
):
    if filter_param in {"description", "displayName", "employeeType", "organisation", "title"}:
        filter_value = random_name()
        create_kwargs = {"udm_properties": {filter_param: filter_value}}
    elif filter_param == "e-mail":
        email1 = f"{random_name()}mail{fake.pyint()}@{mail_domain}".lower()
        filter_value = f"{random_name()}mail{fake.pyint()}@{mail_domain}".lower()
        email3 = f"{random_name()}mail{fake.pyint()}@{mail_domain}".lower()
        create_kwargs = {
            "email": filter_value,
            "udm_properties": {filter_param: [email1, filter_value, email3]},
        }
    elif filter_param == "phone":
        filter_value = random_name()
        create_kwargs = {"udm_properties": {filter_param: [random_name(), filter_value, random_name()]}}
    else:
        create_kwargs = {}
    role = random.choice(("student", "teacher", "staff", "teacher_and_staff", "school_admin"))
    school = await create_ou_using_python()
    user: ImportUser = await new_import_user(school, role, **create_kwargs)
    assert user.role_string == role
    async with UDM(**udm_kwargs) as udm:
        udm_user = await user.get_udm_object(udm)
    if filter_param in {"uidNumber", "gidNumber"}:
        filter_value = udm_user.props[filter_param]
    elif filter_param in {"e-mail", "phone"}:
        assert set(udm_user.props[filter_param]) == set(create_kwargs["udm_properties"][filter_param])
    else:
        assert udm_user.props[filter_param] == create_kwargs["udm_properties"][filter_param]
    params = {filter_param: filter_value}
    response = retry_http_502(
        requests.get,
        f"{url_fragment}/users/",
        headers=auth_header,
        params=params,
    )
    assert response.status_code == 200, response.reason
    api_users = {data["name"]: UserModel(**data) for data in response.json()}
    if filter_param != "gidNumber":
        assert len(api_users) == 1
    assert user.name in api_users
    api_user = api_users[user.name]
    created_value = api_user.udm_properties[filter_param]
    if filter_param in {"e-mail", "phone"}:
        assert set(created_value) == set(create_kwargs["udm_properties"][filter_param])
    else:
        assert created_value == filter_value
    await compare_lib_api_user(user, api_user, udm, url_fragment)
    json_resp = response.json()
    resp = [r for r in json_resp if r["dn"] == api_user.dn][0]
    compare_ldap_json_obj(api_user.dn, resp, url_fragment)


@pytest.mark.asyncio
async def test_search_user_without_firstname(
    auth_header, create_ou_using_python, retry_http_502, url_fragment, new_school_user, udm_kwargs
):
    role = random.choice(("student", "teacher", "staff", "teacher_and_staff", "school_admin"))
    school = await create_ou_using_python()
    lib_user: User = await new_school_user(school, role)
    assert lib_user.firstname
    response = retry_http_502(
        requests.get,
        f"{url_fragment}/users/",
        headers=auth_header,
        params={"school": school},
    )
    assert response.status_code == 200, (response.reason, response.content)
    json_resp = response.json()
    assert any(u["firstname"] == lib_user.firstname for u in json_resp)
    # reading the user is OK at this point
    async with UDM(**udm_kwargs) as udm:
        udm_user = await udm.get("users/user").get(lib_user.dn)
        udm_user.props.firstname = ""
        await udm_user.save()
    # should fail now:
    response = retry_http_502(
        requests.get,
        f"{url_fragment}/users/",
        headers=auth_header,
        params={"school": school},
    )
    assert response.status_code == 500, (response.reason, response.content)
    json_resp = response.json()
    assert lib_user.dn in json_resp["detail"]
    assert "firstname" in json_resp["detail"]
    assert "none is not an allowed value" in json_resp["detail"]


@pytest.mark.asyncio
async def test_search_returns_no_exam_user(
    auth_header, create_ou_using_python, retry_http_502, url_fragment, create_exam_user, udm_kwargs
):
    school = await create_ou_using_python()
    dn, exam_user = await create_exam_user(school)
    async with UDM(**udm_kwargs) as udm:
        lib_user: User = (await User.get_all(udm, school, filter_str=f"uid={exam_user['username']}"))[0]
    assert lib_user.name == exam_user["username"]
    assert lib_user.school == school
    assert lib_user.ucsschool_roles == exam_user["ucsschoolRole"]
    assert f"cn=examusers,ou={school}" in lib_user.dn

    response = retry_http_502(
        requests.get,
        f"{url_fragment}/users/",
        headers=auth_header,
        params={"school": school},
    )
    assert response.status_code == 200, (response.reason, response.content)
    json_resp = response.json()
    assert all(u["name"] != exam_user["username"] for u in json_resp)
    assert not any(role.startswith("exam") for user in json_resp for role in user["ucsschool_roles"])


@pytest.mark.asyncio
@pytest.mark.parametrize("role", USER_ROLES, ids=role_id)
async def test_get(
    auth_header,
    retry_http_502,
    url_fragment,
    create_ou_using_python,
    new_import_user,
    random_name,
    import_config,
    udm_kwargs,
    role: Role,
):
    udm_properties = {
        "title": random_name(),
        "description": random_name(),
        "employeeType": random_name(),
        "organisation": random_name(),
        "phone": [random_name(), random_name()],
    }
    school = await create_ou_using_python()
    user: ImportUser = await new_import_user(school, role.name, udm_properties)
    assert isinstance(user, role.klass)
    response = retry_http_502(requests.get, f"{url_fragment}/users/{user.name}", headers=auth_header)
    assert response.status_code == 200, response.reason
    json_resp = response.json()
    assert all(
        attr in json_resp
        for attr in (
            "birthday",
            "disabled",
            "dn",
            "email",
            "expiration_date",
            "firstname",
            "lastname",
            "name",
            "record_uid",
            "roles",
            "schools",
            "school_classes",
            "source_uid",
            "ucsschool_roles",
            "udm_properties",
            "url",
            "workgroups",
        )
    )
    api_user = UserModel(**json_resp)
    for k, v in udm_properties.items():
        if isinstance(v, (tuple, list)):
            assert set(api_user.udm_properties.get(k, [])) == set(v)
        else:
            assert api_user.udm_properties.get(k) == v
    async with UDM(**udm_kwargs) as udm:
        await compare_lib_api_user(user, api_user, udm, url_fragment)
    json_resp = response.json()
    if type(json_resp) is list:
        json_resp = [resp for resp in json_resp if resp["dn"] == api_user.dn][0]
    compare_ldap_json_obj(api_user.dn, json_resp, url_fragment)


@pytest.mark.asyncio
async def test_get_empty_udm_properties_are_returned(
    auth_header,
    retry_http_502,
    url_fragment,
    create_ou_using_python,
    new_import_user,
    import_config,
    udm_kwargs,
):
    role: Role = random.choice(USER_ROLES)
    school = await create_ou_using_python()
    user: ImportUser = await new_import_user(school, role.name)
    response = retry_http_502(requests.get, f"{url_fragment}/users/{user.name}", headers=auth_header)
    assert response.status_code == 200, response.reason
    api_user = UserModel(**response.json())
    for prop in import_config["mapped_udm_properties"]:
        assert prop in api_user.udm_properties


@pytest.mark.asyncio
async def test_get_returns_exam_user(
    auth_header, create_ou_using_python, retry_http_502, url_fragment, create_exam_user, udm_kwargs
):
    school = await create_ou_using_python()
    dn, exam_user = await create_exam_user(school)
    async with UDM(**udm_kwargs) as udm:
        lib_user: User = (await User.get_all(udm, school, filter_str=f"uid={exam_user['username']}"))[0]
        assert lib_user.name == exam_user["username"]
        assert lib_user.school == school
        assert lib_user.ucsschool_roles == exam_user["ucsschoolRole"]
        assert f"cn=examusers,ou={school}" in lib_user.dn

        response = retry_http_502(
            requests.get,
            f"{url_fragment}/users/{exam_user['username']}",
            headers=auth_header,
            params={"school": school},
        )
        assert response.status_code == 200, response.reason
        json_resp = response.json()
        assert json_resp["name"] == exam_user["username"]
        assert json_resp["ucsschool_roles"] == exam_user["ucsschoolRole"]
        assert f"cn=examusers,ou={school}" in json_resp["dn"]


@pytest.mark.asyncio
@pytest.mark.parametrize("role", USER_ROLES, ids=role_id)
async def test_create(
    auth_header,
    check_password,
    retry_http_502,
    url_fragment,
    create_ou_using_python,
    random_user_create_model,
    random_name,
    import_config,
    udm_kwargs,
    schedule_delete_user_name_using_udm,
    new_workgroup_using_lib,
    role: Role,
):
    if role.name == "teacher_and_staff":
        roles = ["staff", "teacher"]
    else:
        roles = [role.name]
    school = await create_ou_using_python()
    school_scrambled = scramble_case(school)
    wg_dn, wg_attr = await new_workgroup_using_lib(school)
    workgroups = {school_scrambled: [wg_attr["name"]]}
    r_user = await random_user_create_model(
        school_scrambled,
        roles=[f"{url_fragment}/roles/{role_}" for role_ in roles],
        workgroups=workgroups,
    )
    r_user.school_classes = {scramble_case(ou): kls for ou, kls in r_user.school_classes.items()}
    title = random_name()
    r_user.udm_properties["title"] = title
    phone = [random_name(), random_name()]
    r_user.udm_properties["phone"] = phone
    data = r_user.json()
    logger.debug("POST data=%r", data)
    async with UDM(**udm_kwargs) as udm:
        lib_users = await User.get_all(udm, school, f"username={r_user.name}")
    assert len(lib_users) == 0
    schedule_delete_user_name_using_udm(r_user.name)
    response = retry_http_502(
        requests.post,
        f"{url_fragment}/users/",
        headers={"Content-Type": "application/json", **auth_header},
        data=data,
    )
    assert response.status_code == 201, f"{response.__dict__!r}"
    response_json = response.json()
    api_user = UserModel(**response_json)
    async with UDM(**udm_kwargs) as udm:
        lib_users = await User.get_all(udm, school, f"username={r_user.name}")
        assert len(lib_users) == 1
        assert isinstance(lib_users[0], role.klass)
        udm_props = (await lib_users[0].get_udm_object(udm)).props
    assert api_user.udm_properties["title"] == title
    assert api_user.school.split("/")[-1] == school
    assert set(api_user.udm_properties["phone"]) == set(phone)
    assert udm_props.title == title
    assert set(udm_props.phone) == set(phone)
    await compare_lib_api_user(lib_users[0], api_user, udm, url_fragment)
    await asyncio.sleep(5)
    compare_ldap_json_obj(api_user.dn, response_json, url_fragment)
    if r_user.disabled:
        with pytest.raises(BindError):
            await check_password(response_json["dn"], r_user.password)
    else:
        await check_password(response_json["dn"], r_user.password)
    # Bug #52668: check sambahome and profilepath
    async with UDM(**udm_kwargs) as udm:
        user_udm = await udm.get("users/user").get(response_json["dn"])
        if role.name == "staff":
            assert user_udm.props.profilepath is None
            assert user_udm.props.sambahome is None
        else:
            assert user_udm.props.profilepath == r"%LOGONSERVER%\%USERNAME%\windows-profiles\default"
            school = await School.from_dn(School.cache(lib_users[0].school).dn, None, udm)
            home_share_file_server = school.home_share_file_server
            assert (
                home_share_file_server
            ), f"No 'home_share_file_server' set for OU {lib_users[0].school!r}."
            samba_home_path = rf"\\{school.get_name_from_dn(home_share_file_server)}\{lib_users[0].name}"
            assert user_udm.props.sambahome == samba_home_path


@pytest.mark.asyncio
@pytest.mark.parametrize("role", USER_ROLES, ids=role_id)
async def test_create_username_checks(
    auth_header,
    check_password,
    retry_http_502,
    url_fragment,
    create_ou_using_python,
    random_user_create_model,
    random_name,
    import_config,
    udm_kwargs,
    schedule_delete_user_name_using_udm,
    new_workgroup_using_lib,
    role: Role,
):
    if role.name == "teacher_and_staff":
        roles = ["staff", "teacher"]
    else:
        roles = [role.name]
    school = await create_ou_using_python()
    school_scrambled = scramble_case(school)
    wg_dn, wg_attr = await new_workgroup_using_lib(school)
    workgroups = {school_scrambled: [wg_attr["name"]]}
    r_user = await random_user_create_model(
        school_scrambled,
        roles=[f"{url_fragment}/roles/{role_}" for role_ in roles],
        workgroups=workgroups,
    )
    while len(r_user.name) < 50:
        r_user.name += random_name()
    r_user.school_classes = {scramble_case(ou): kls for ou, kls in r_user.school_classes.items()}
    title = random_name()
    r_user.udm_properties["title"] = title
    phone = [random_name(), random_name()]
    r_user.udm_properties["phone"] = phone
    data = r_user.json()
    logger.debug("POST data=%r", data)
    async with UDM(**udm_kwargs) as udm:
        lib_users = await User.get_all(udm, school, f"username={r_user.name}")
    assert len(lib_users) == 0
    schedule_delete_user_name_using_udm(r_user.name)
    response = retry_http_502(
        requests.post,
        f"{url_fragment}/users/",
        headers={"Content-Type": "application/json", **auth_header},
        data=data,
    )
    assert response.status_code == 400, f"{response.__dict__!r}"
    async with UDM(**udm_kwargs) as udm:
        lib_users = await User.get_all(udm, school, f"username={r_user.name}")
        assert len(lib_users) == 0


@pytest.mark.asyncio
@pytest.mark.parametrize("role", USER_ROLES, ids=role_id)
@pytest.mark.parametrize("evaluate_password_policies", [True, False])
async def test_user_create_password_policies(
    auth_header,
    retry_http_502,
    url_fragment,
    create_ou_using_python,
    random_user_create_model,
    schedule_delete_user_name_using_udm,
    role: Role,
    add_to_kelvin_config,
    evaluate_password_policies,
):
    """
    creating users with activated password policy evaluation
    should fail (for the default password policy) if the length of the
    password is higher than the value of password_length but
    lower than 8 (value in the default password policy).
    """
    password_length = 3
    add_to_kelvin_config(
        evaluate_password_policies=evaluate_password_policies, password_length=password_length
    )
    if role.name == "teacher_and_staff":
        roles = ["staff", "teacher"]
    else:
        roles = [role.name]
    school = await create_ou_using_python()
    r_user = await random_user_create_model(
        school,
        roles=[f"{url_fragment}/roles/{role_}" for role_ in roles],
    )
    r_user.password = fake.password(length=password_length + 1)
    data = r_user.json()
    logger.debug("POST data=%r", data)
    schedule_delete_user_name_using_udm(r_user.name)
    response = retry_http_502(
        requests.post,
        f"{url_fragment}/users/",
        headers={"Content-Type": "application/json", **auth_header},
        data=data,
    )

    response_json = response.json()

    if evaluate_password_policies:
        assert response.status_code == 422, f"{response.__dict__!r}"

        assert "detail" in response_json
        assert len(response_json["detail"]) > 0
        assert "msg" in response_json["detail"][0]
        response_msg: str = response.json()["detail"][0]["msg"]
        assert "Password policy error" in response_msg, response_msg
    else:
        assert response.status_code == 201, f"{response.__dict__!r}"
        assert "detail" not in response_json


@pytest.mark.asyncio
@pytest.mark.parametrize("evaluate_password_policies", [True, False])
@pytest.mark.parametrize("method", ("patch", "put"))
async def test_user_modify_password_policies(
    evaluate_password_policies,
    add_to_kelvin_config,
    auth_header,
    retry_http_502,
    import_user_to_create_model_kwargs,
    url_fragment,
    create_ou_using_python,
    new_import_user,
    random_user_create_model,
    import_config,
    method,
):
    """
    modifying users with activated password policy evaluation
    should always fail (for the default password policy)
    if the length of the password is higher than the value of password_length but
    lower than 8 (value in the default password policy).
    """
    password_length = 3
    add_to_kelvin_config(
        evaluate_password_policies=evaluate_password_policies, password_length=password_length
    )
    role: Role = Role("student", Student)
    school = await create_ou_using_python()
    user: ImportUser = await new_import_user(school, role.name, disabled=False)
    old_user_data = import_user_to_create_model_kwargs(user)
    user_create_model = await random_user_create_model(
        school,
        roles=old_user_data["roles"],
        disabled=False,
        school=old_user_data["school"],
        schools=old_user_data["schools"],
    )
    user_create_model.password = fake.password(length=password_length + 1)
    new_user_data = user_create_model.dict(exclude={"name", "record_uid", "source_uid"})
    modified_user = UserCreateModel(**{**old_user_data, **new_user_data})
    modified_user.password = modified_user.password.get_secret_value()
    logger.debug(f"{method.upper()} modified_user=%r.", modified_user.dict())
    response = None
    if method == "patch":
        response = retry_http_502(
            requests.patch,
            f"{url_fragment}/users/{user.name}",
            headers=auth_header,
            data=json.dumps({"password": modified_user.password}),
        )
    elif method == "put":
        response = retry_http_502(
            requests.put,
            f"{url_fragment}/users/{user.name}",
            headers=auth_header,
            data=modified_user.json(),
        )

    response_json = response.json()

    assert "detail" in response_json
    assert len(response_json["detail"]) > 0
    assert "msg" in response_json["detail"][0]
    response_msg: str = response.json()["detail"][0]["msg"]

    assert response.status_code == 422, f"{response.__dict__!r}"
    assert "Password policy error" in response_msg, response_msg


@pytest.mark.asyncio
async def test_create_unmapped_udm_prop(
    create_ou_using_python,
    random_user_create_model,
    url_fragment,
    udm_kwargs,
    schedule_delete_user_name_using_udm,
    retry_http_502,
    auth_header,
):
    school = await create_ou_using_python()
    r_user = await random_user_create_model(school, roles=[f"{url_fragment}/roles/teacher"])
    r_user.udm_properties["unmapped_prop"] = "some value"
    data = r_user.json()
    logger.debug("POST data=%r", data)
    async with UDM(**udm_kwargs) as udm:
        lib_users = await User.get_all(udm, school, f"username={r_user.name}")
    assert len(lib_users) == 0
    schedule_delete_user_name_using_udm(r_user.name)
    response = retry_http_502(
        requests.post,
        f"{url_fragment}/users/",
        headers={"Content-Type": "application/json", **auth_header},
        data=data,
    )
    response_json = response.json()
    assert response.status_code == 422, response.__dict__
    assert response_json == {
        "detail": [
            {
                "loc": ["body", "udm_properties"],
                "msg": "UDM properties that were not configured for resource 'user' and are "
                "thus not allowed: {'unmapped_prop'}",
                "type": "value_error.unknownudmproperty",
            }
        ]
    }


@pytest.mark.asyncio
@pytest.mark.parametrize("role", USER_ROLES, ids=role_id)
async def test_create_without_username(
    auth_header,
    check_password,
    retry_http_502,
    url_fragment,
    create_ou_using_python,
    random_user_create_model,
    import_config,
    reset_import_config,
    udm_kwargs,
    add_to_import_config,
    schedule_delete_user_name_using_udm,
    role: Role,
):
    if role.name == "teacher_and_staff":
        roles = ["staff", "teacher"]
    else:
        roles = [role.name]
    school = await create_ou_using_python()
    r_user = await random_user_create_model(
        school, roles=[f"{url_fragment}/roles/{role_}" for role_ in roles]
    )
    data = r_user.json(exclude={"name"})
    assert "'name'" not in data
    expected_name = f"test.{r_user.firstname[:2]}.{r_user.lastname[:3]}".lower()
    async with UDM(**udm_kwargs) as udm:
        lib_users = await User.get_all(udm, school, f"username={expected_name}")
    assert len(lib_users) == 0
    schedule_delete_user_name_using_udm(expected_name)
    logger.debug("POST data=%r", data)
    response = retry_http_502(
        requests.post,
        f"{url_fragment}/users/",
        headers={"Content-Type": "application/json", **auth_header},
        data=data,
    )
    assert response.status_code == 201, f"{response.__dict__!r}"
    response_json = response.json()
    api_user = UserModel(**response_json)
    assert api_user.name == expected_name
    async with UDM(**udm_kwargs) as udm:
        lib_users = await User.get_all(udm, school, f"username={expected_name}")
    assert len(lib_users) == 1
    assert isinstance(lib_users[0], role.klass)
    if r_user.disabled:
        with pytest.raises(BindError):
            await check_password(response_json["dn"], r_user.password)
    else:
        await check_password(response_json["dn"], r_user.password)


@pytest.mark.asyncio
@pytest.mark.parametrize("role", USER_ROLES, ids=role_id)
@pytest.mark.parametrize("no_school_s", ("school", "schools"))
async def test_create_minimal_attrs(
    auth_header,
    check_password,
    retry_http_502,
    url_fragment,
    create_ou_using_python,
    random_user_create_model,
    import_config,
    reset_import_config,
    udm_kwargs,
    add_to_import_config,
    schedule_delete_user_name_using_udm,
    role: Role,
    no_school_s: str,
):
    if role.name == "teacher_and_staff":
        roles = ["staff", "teacher"]
    else:
        roles = [role.name]
    school = await create_ou_using_python()
    r_user = await random_user_create_model(
        school, roles=[f"{url_fragment}/roles/{role_}" for role_ in roles], disabled=False
    )
    data = r_user.dict(
        exclude={
            "birthday",
            "disabled",
            no_school_s,
            "email",
            "expiration_date",
            "name",
            "source_uid",
            "ucsschool_roles",
            "udm_properties",
        }
    )
    expected_name = f"test.{r_user.firstname[:2]}.{r_user.lastname[:3]}".lower()
    async with UDM(**udm_kwargs) as udm:
        lib_users = await User.get_all(udm, school, f"username={expected_name}")
    assert len(lib_users) == 0
    schedule_delete_user_name_using_udm(expected_name)
    logger.debug("POST data=%r", data)
    response = retry_http_502(
        requests.post,
        f"{url_fragment}/users/",
        headers={"Content-Type": "application/json", **auth_header},
        json=data,
    )
    assert response.status_code == 201, f"{response.__dict__!r}"
    response_json = response.json()
    api_user = UserModel(**response_json)
    assert api_user.name == expected_name
    async with UDM(**udm_kwargs) as udm:
        lib_users = await User.get_all(udm, school, f"username={expected_name}")
    assert len(lib_users) == 1
    assert isinstance(lib_users[0], role.klass)
    await check_password(response_json["dn"], r_user.password)


@pytest.mark.asyncio
@pytest.mark.parametrize("role", [random.choice(USER_ROLES)], ids=role_id)
@pytest.mark.parametrize("no_school_s", ("school", "schools"))
async def test_create_requires_school_or_schools(
    auth_header,
    url_fragment,
    create_ou_using_python,
    retry_http_502,
    random_user_create_model,
    import_config,
    reset_import_config,
    udm_kwargs,
    add_to_import_config,
    schedule_delete_user_name_using_udm,
    role: Role,
    no_school_s: str,
):
    if role.name == "teacher_and_staff":
        roles = ["staff", "teacher"]
    else:
        roles = [role.name]
    school = await create_ou_using_python()
    r_user = await random_user_create_model(
        school, roles=[f"{url_fragment}/roles/{role_}" for role_ in roles], disabled=False
    )
    data = r_user.dict(exclude={"school", "schools"})
    data["birthday"] = data["birthday"].isoformat()
    data["expiration_date"] = data["expiration_date"].isoformat()
    expected_name = f"test.{r_user.firstname[:2]}.{r_user.lastname[:3]}".lower()
    async with UDM(**udm_kwargs) as udm:
        lib_users = await User.get_all(udm, school, f"username={expected_name}")
    assert len(lib_users) == 0
    schedule_delete_user_name_using_udm(expected_name)
    logger.debug("POST data=%r", data)
    response = retry_http_502(
        requests.post,
        f"{url_fragment}/users/",
        headers={"Content-Type": "application/json", **auth_header},
        json=data,
    )
    assert response.status_code == 422, f"{response.__dict__!r}"
    logger.debug("response.content=%r", response.content)
    response_json = response.json()
    logger.debug("response_json=%r", response_json)
    assert "At least one of" in response_json["detail"][0]["msg"]


@pytest.mark.asyncio
async def test_create_with_password_hashes(
    auth_header,
    check_password,
    retry_http_502,
    url_fragment,
    create_ou_using_python,
    random_user_create_model,
    import_config,
    udm_kwargs,
    schedule_delete_user_name_using_udm,
    password_hash,
):
    role = random.choice(USER_ROLES)
    if role.name == "teacher_and_staff":
        roles = ["staff", "teacher"]
    else:
        roles = [role.name]
    school = await create_ou_using_python()
    r_user = await random_user_create_model(
        school,
        roles=[f"{url_fragment}/roles/{role_}" for role_ in roles],
        disabled=False,
        school_classes={},
        workgroups={},
    )
    school = r_user.school.split("/")[-1]
    r_user.password = None
    password_new, password_new_hashes = await password_hash()
    r_user.kelvin_password_hashes = password_new_hashes.dict()
    data = r_user.json()
    logger.debug("POST data=%r", data)
    async with UDM(**udm_kwargs) as udm:
        lib_users = await User.get_all(udm, school, f"username={r_user.name}")
    assert len(lib_users) == 0
    schedule_delete_user_name_using_udm(r_user.name)
    response = retry_http_502(
        requests.post,
        f"{url_fragment}/users/",
        headers={"Content-Type": "application/json", **auth_header},
        data=data,
    )
    assert response.status_code == 201, f"{response.__dict__!r}"
    response_json = response.json()
    api_user = UserModel(**response_json)
    async with UDM(**udm_kwargs) as udm:
        lib_users = await User.get_all(udm, school, f"username={r_user.name}")
        assert len(lib_users) == 1
        assert isinstance(lib_users[0], role.klass)
    await compare_lib_api_user(lib_users[0], api_user, udm, url_fragment)
    compare_ldap_json_obj(api_user.dn, response_json, url_fragment)
    await check_password(response_json["dn"], password_new)
    logger.debug("OK: can login as user with new password.")


@pytest.mark.asyncio
@pytest.mark.parametrize("role", USER_ROLES, ids=role_id)
async def test_put(
    auth_header,
    check_password,
    retry_http_502,
    import_user_to_create_model_kwargs,
    url_fragment,
    create_ou_using_python,
    new_import_user,
    random_user_create_model,
    random_name,
    import_config,
    udm_kwargs,
    role: Role,
):
    school = await create_ou_using_python()
    user: ImportUser = await new_import_user(school, role.name, disabled=False)
    await check_password(user.dn, user.password)
    logger.debug("OK: can login with old password")
    old_user_data = import_user_to_create_model_kwargs(user)
    user_create_model = await random_user_create_model(
        school,
        roles=old_user_data["roles"],
        disabled=False,
        school=old_user_data["school"],
        schools=old_user_data["schools"],
    )
    new_user_data = user_create_model.dict(exclude={"name", "record_uid", "source_uid"})
    title = random_name()
    phone = [random_name(), random_name()]
    new_user_data["udm_properties"] = {"title": title, "phone": phone}
    modified_user = UserCreateModel(**{**old_user_data, **new_user_data})
    modified_user.password = modified_user.password.get_secret_value()
    logger.debug("PUT modified_user=%r.", modified_user.dict())
    response = retry_http_502(
        requests.put,
        f"{url_fragment}/users/{user.name}",
        headers=auth_header,
        data=modified_user.json(),
    )
    assert response.status_code == 200, response.reason
    api_user = UserModel(**response.json())
    async with UDM(**udm_kwargs) as udm:
        lib_users = await User.get_all(udm, school, f"username={user.name}")
        assert len(lib_users) == 1
        assert isinstance(lib_users[0], role.klass)
        assert api_user.udm_properties["title"] == title
        assert set(api_user.udm_properties["phone"]) == set(phone)
        udm_props = (await lib_users[0].get_udm_object(udm)).props
        assert udm_props.title == title
        assert set(udm_props.phone) == set(phone)
        await compare_lib_api_user(lib_users[0], api_user, udm, url_fragment)
    json_resp = response.json()
    compare_ldap_json_obj(api_user.dn, json_resp, url_fragment)
    await check_password(lib_users[0].dn, modified_user.password)


@pytest.mark.asyncio
async def test_put_with_password_hashes(
    auth_header,
    check_password,
    retry_http_502,
    import_user_to_create_model_kwargs,
    url_fragment,
    create_ou_using_python,
    new_import_user,
    random_user_create_model,
    password_hash,
    import_config,
    udm_kwargs,
):
    role = random.choice(USER_ROLES)
    school = await create_ou_using_python()
    user: ImportUser = await new_import_user(
        school, role.name, disabled=False, school_classes={}, workgroups={}
    )
    await check_password(user.dn, user.password)
    logger.debug("OK: can login with old password")
    old_user_data = import_user_to_create_model_kwargs(user)
    new_user_create_model = await random_user_create_model(
        school,
        roles=old_user_data["roles"],
        disabled=False,
        school=old_user_data["school"],
        schools=old_user_data["schools"],
    )
    new_user_data = new_user_create_model.dict(exclude={"name", "password", "record_uid", "source_uid"})
    for key in ("name", "password", "record_uid", "source_uid"):
        assert key not in new_user_data
    modified_user = UserCreateModel(**{**old_user_data, **new_user_data})
    modified_user.password = None
    password_new, password_new_hashes = await password_hash()
    modified_user.kelvin_password_hashes = password_new_hashes.dict()
    logger.debug("PUT modified_user=%r.", modified_user.dict())
    response = retry_http_502(
        requests.put,
        f"{url_fragment}/users/{user.name}",
        headers=auth_header,
        data=modified_user.json(),
    )
    assert response.status_code == 200, response.reason
    api_user = UserModel(**response.json())
    async with UDM(**udm_kwargs) as udm:
        lib_users = await User.get_all(udm, school, f"username={user.name}")
        assert len(lib_users) == 1
        assert isinstance(lib_users[0], role.klass)
        await compare_lib_api_user(lib_users[0], api_user, udm, url_fragment)
    json_resp = response.json()
    compare_ldap_json_obj(api_user.dn, json_resp, url_fragment)
    await check_password(lib_users[0].dn, password_new)
    logger.debug("OK: can login as user with new password.")
    with pytest.raises(BindError):
        await check_password(lib_users[0].dn, user.password)
    logger.debug("OK: cannot login as user with old password.")


@pytest.mark.asyncio
@pytest.mark.parametrize("role", USER_ROLES, ids=role_id)
@pytest.mark.parametrize("null_value", ("birthday", "email", "expiration_date"))
async def test_patch(
    auth_header,
    check_password,
    retry_http_502,
    import_user_to_create_model_kwargs,
    url_fragment,
    create_ou_using_python,
    new_import_user,
    random_user_create_model,
    random_name,
    mail_domain,
    import_config,
    udm_kwargs,
    role: Role,
    null_value: str,
):
    school = await create_ou_using_python()
    user: ImportUser = await new_import_user(school, role.name, disabled=False)
    await check_password(user.dn, user.password)
    logger.debug("OK: can login with old password")
    old_user_data = import_user_to_create_model_kwargs(user)
    user_create_model = await random_user_create_model(
        school,
        roles=old_user_data["roles"],
        disabled=False,
        email=f"{random_name()}mail{fake.pyint()}@{mail_domain}".lower(),
        school=old_user_data["school"],
        schools=old_user_data["schools"],
    )
    new_user_data = user_create_model.dict(
        exclude={"name", "record_uid", "source_uid", "kelvin_password_hashes"}
    )
    new_user_data["birthday"] = str(new_user_data["birthday"])
    new_user_data["expiration_date"] = str(new_user_data["expiration_date"])
    for key in random.sample(list(new_user_data.keys()), random.randint(1, len(new_user_data.keys()))):
        del new_user_data[key]
    title = random_name()
    phone = [random_name(), random_name()]
    new_user_data["udm_properties"] = {"title": title, "phone": phone}
    new_user_data[null_value] = None
    new_user_data["password"] = fake.password(length=20)
    logger.debug("PATCH new_user_data=%r.", new_user_data)
    response = retry_http_502(
        requests.patch,
        f"{url_fragment}/users/{user.name}",
        headers=auth_header,
        json=new_user_data,
    )
    assert response.status_code == 200, f"{response.__dict__!r}"
    api_user = UserModel(**response.json())
    async with UDM(**udm_kwargs) as udm:
        lib_users = await User.get_all(udm, school, f"username={user.name}")
        assert len(lib_users) == 1
        assert isinstance(lib_users[0], role.klass)
        assert api_user.udm_properties["title"] == title
        assert getattr(lib_users[0], null_value) is None
        assert set(api_user.udm_properties["phone"]) == set(phone)
        udm_props = (await lib_users[0].get_udm_object(udm)).props
        assert udm_props.title == title
        assert set(udm_props.phone) == set(phone)
        await compare_lib_api_user(lib_users[0], api_user, udm, url_fragment)
    json_resp = response.json()
    compare_ldap_json_obj(api_user.dn, json_resp, url_fragment)
    await check_password(lib_users[0].dn, new_user_data["password"])


@pytest.mark.asyncio
async def test_patch_with_password_hashes(
    auth_header,
    check_password,
    retry_http_502,
    import_user_to_create_model_kwargs,
    url_fragment,
    create_ou_using_python,
    new_import_user,
    random_user_create_model,
    import_config,
    password_hash,
    udm_kwargs,
):
    role = random.choice(USER_ROLES)
    school = await create_ou_using_python()
    user: ImportUser = await new_import_user(
        school, role.name, disabled=False, school_classes={}, workgroups={}
    )
    await check_password(user.dn, user.password)
    logger.debug("OK: can login with old password")
    old_user_data = import_user_to_create_model_kwargs(user)
    user_create_model = await random_user_create_model(
        school,
        roles=old_user_data["roles"],
        disabled=False,
        school=old_user_data["school"],
        schools=old_user_data["schools"],
    )
    new_user_data = user_create_model.dict(
        exclude={"birthday", "expiration_date", "name", "password", "record_uid", "source_uid"}
    )
    password_new, password_new_hashes = await password_hash()
    new_user_data["kelvin_password_hashes"] = password_new_hashes.dict()
    logger.debug("PATCH new_user_data=%r.", new_user_data)
    response = retry_http_502(
        requests.patch,
        f"{url_fragment}/users/{user.name}",
        headers=auth_header,
        json=new_user_data,
    )
    assert response.status_code == 200, response.reason
    json_resp = response.json()
    api_user = UserModel(**json_resp)
    async with UDM(**udm_kwargs) as udm:
        lib_users = await User.get_all(udm, school, f"username={user.name}")
        assert len(lib_users) == 1
        assert isinstance(lib_users[0], role.klass)
        await compare_lib_api_user(lib_users[0], api_user, udm, url_fragment)
    compare_ldap_json_obj(api_user.dn, json_resp, url_fragment)
    await check_password(user.dn, password_new)
    logger.debug("OK: can login as user with new password.")
    with pytest.raises(BindError):
        await check_password(user.dn, user.password)
    logger.debug("OK: cannot login as user with old password.")


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "roles",
    set(itertools.product(USER_ROLES, USER_ROLES))
    - {(Role(role_school_admin, SchoolAdmin), Role(role_student, Student))},
    ids=two_roles_id,
)
@pytest.mark.parametrize("method", ("patch", "put"))
async def test_role_change(
    auth_header,
    retry_http_502,
    import_user_to_create_model_kwargs,
    url_fragment,
    new_import_user,
    import_config,
    udm_kwargs,
    schedule_delete_user_name_using_udm,
    new_school_class_using_lib,
    new_workgroup_using_lib,
    random_name,
    roles: Tuple[Role, Role],
    method: str,
    create_multiple_ous,
):
    role_from, role_to = roles

    ou1, ou2 = await create_multiple_ous(2)
    user: ImportUser = await new_import_user(ou1, role_from.name, schools=[ou1, ou2])
    if role_to.name == "teacher_and_staff":
        roles_urls = [
            f"{url_fragment}/roles/staff",
            f"{url_fragment}/roles/teacher",
        ]
    else:
        roles_urls = [f"{url_fragment}/roles/{role_to.name}"]
    user_url = f"{url_fragment}/users/{user.name}"
    schedule_delete_user_name_using_udm(user.name)
    wg_dn2, wg_attr2 = await new_workgroup_using_lib(ou2)
    workgroups = {ou2: [wg_attr2["name"]]}
    sc_dn2, sc_attr2 = await new_school_class_using_lib(ou2)
    school_classes = {ou2: [sc_attr2["name"]]}
    if role_to.name == "student":
        # For conversion to Student one class per school is required, but user has only the one for ou1.
        sc_dn2, sc_attr2 = await new_school_class_using_lib(ou2)
        school_classes = {ou2: [sc_attr2["name"]]}
        if role_from.name == "staff":
            # Staff user will have no school_class, so it is missing even the one for ou1.
            sc_dn, sc_attr = await new_school_class_using_lib(ou1)
            school_classes[ou1] = [sc_attr["name"]]
    else:
        school_classes = {}
    if method == "patch":
        patch_data = {"roles": roles_urls}
        if school_classes:
            patch_data["school_classes"] = school_classes
        if workgroups:
            patch_data["workgroups"] = workgroups
        response = retry_http_502(
            requests.patch,
            user_url,
            headers=auth_header,
            json=patch_data,
        )
    elif method == "put":
        old_data = import_user_to_create_model_kwargs(user, ["roles"])
        if school_classes:
            old_data["school_classes"] = school_classes
        if workgroups:
            old_data["workgroups"] = workgroups
        modified_user = UserCreateModel(roles=roles_urls, **old_data)
        response = retry_http_502(
            requests.put,
            user_url,
            headers=auth_header,
            data=modified_user.json(),
        )
    else:
        raise RuntimeError(f"Unknown method: {method}")
    assert response.status_code == 200, response.reason
    json_resp = response.json()
    assert set(UserCreateModel.unscheme_and_unquote(role_url) for role_url in json_resp["roles"]) == set(
        roles_urls
    )
    async with UDM(**udm_kwargs) as udm:
        lib_users = await User.get_all(udm, ou1, f"username={user.name}")
        assert len(lib_users) == 1
        assert isinstance(lib_users[0], role_to.klass)


@pytest.mark.asyncio
@pytest.mark.parametrize("method", ("patch", "put"))
async def test_failing_role_change_school_admin_to_student(
    auth_header,
    retry_http_502,
    import_user_to_create_model_kwargs,
    url_fragment,
    new_import_user,
    import_config,
    udm_kwargs,
    schedule_delete_user_name_using_udm,
    new_school_class_using_lib,
    new_workgroup_using_lib,
    random_name,
    method: str,
    create_multiple_ous,
):
    role_from, role_to = Role(role_school_admin, SchoolAdmin), Role(role_student, Student)

    ou1, ou2 = await create_multiple_ous(2)
    user: ImportUser = await new_import_user(ou1, role_from.name, schools=[ou1, ou2])
    roles_urls = [f"{url_fragment}/roles/{role_to.name}"]
    user_url = f"{url_fragment}/users/{user.name}"
    schedule_delete_user_name_using_udm(user.name)
    wg_dn2, wg_attr2 = await new_workgroup_using_lib(ou2)
    workgroups = {ou2: [wg_attr2["name"]]}
    sc_dn2, sc_attr2 = await new_school_class_using_lib(ou2)
    school_classes = {ou2: [sc_attr2["name"]]}
    school_classes = {}
    if method == "patch":
        patch_data = {"roles": roles_urls}
        if school_classes:
            patch_data["school_classes"] = school_classes
        if workgroups:
            patch_data["workgroups"] = workgroups
        response = retry_http_502(
            requests.patch,
            user_url,
            headers=auth_header,
            json=patch_data,
        )
    elif method == "put":
        old_data = import_user_to_create_model_kwargs(user, ["roles"])
        if school_classes:
            old_data["school_classes"] = school_classes
        if workgroups:
            old_data["workgroups"] = workgroups
        modified_user = UserCreateModel(roles=roles_urls, **old_data)
        response = retry_http_502(
            requests.put,
            user_url,
            headers=auth_header,
            data=modified_user.json(),
        )
    else:
        raise RuntimeError(f"Unknown method: {method}")
    assert response.status_code == 400


@pytest.mark.asyncio
@pytest.mark.parametrize("method", ("patch", "put"))
async def test_role_change_fails_for_student_without_school_class(
    auth_header,
    retry_http_502,
    import_user_to_create_model_kwargs,
    url_fragment,
    create_ou_using_python,
    new_import_user,
    import_config,
    udm_kwargs,
    schedule_delete_user_name_using_udm,
    method: str,
):
    school = await create_ou_using_python()
    user: ImportUser = await new_import_user(school, "staff")  # staff has no school classes
    roles_urls = [f"{url_fragment}/roles/student"]
    user_url = f"{url_fragment}/users/{user.name}"
    schedule_delete_user_name_using_udm(user.name)
    if method == "patch":
        patch_data = {"roles": roles_urls}
        response = retry_http_502(
            requests.patch,
            user_url,
            headers=auth_header,
            json=patch_data,
        )
    elif method == "put":
        old_data = import_user_to_create_model_kwargs(user, ["roles"])
        modified_user = UserCreateModel(roles=roles_urls, **old_data)
        response = retry_http_502(
            requests.put,
            user_url,
            headers=auth_header,
            data=modified_user.json(),
        )
    else:
        raise RuntimeError("method must be patch or put")
    assert response.status_code == 400, response.reason
    json_resp = response.json()
    assert "requires at least one school class per school" in json_resp["detail"]
    async with UDM(**udm_kwargs) as udm:
        lib_users = await User.get_all(udm, school, f"username={user.name}")
        assert len(lib_users) == 1
        assert isinstance(lib_users[0], Staff)  # unchanged


@pytest.mark.asyncio
@pytest.mark.parametrize("method", ("patch", "put"))
async def test_role_change_fails_for_student_missing_school_class_for_second_school(
    auth_header,
    retry_http_502,
    import_user_to_create_model_kwargs,
    url_fragment,
    new_import_user,
    import_config,
    udm_kwargs,
    schedule_delete_user_name_using_udm,
    method: str,
    create_multiple_ous,
):
    ou1, ou2 = await create_multiple_ous(2)
    user: ImportUser = await new_import_user(ou1, "teacher", schools=[ou1, ou2])
    # staff has no school classes
    async with UDM(**udm_kwargs) as udm:
        lib_users = await Teacher.get_all(udm, ou1, f"username={user.name}")
        assert len(lib_users) == 1
        assert lib_users[0].school_classes[ou1]
        assert not lib_users[0].school_classes.get(ou2)
    roles_urls = [f"{url_fragment}/roles/student"]
    user_url = f"{url_fragment}/users/{user.name}"
    schedule_delete_user_name_using_udm(user.name)
    if method == "patch":
        patch_data = {"roles": roles_urls}
        response = retry_http_502(
            requests.patch,
            user_url,
            headers=auth_header,
            json=patch_data,
        )
    elif method == "put":
        old_data = import_user_to_create_model_kwargs(user, ["roles"])
        modified_user = UserCreateModel(roles=roles_urls, **old_data)
        response = retry_http_502(
            requests.put,
            user_url,
            headers=auth_header,
            data=modified_user.json(),
        )
    else:
        raise RuntimeError("method must be patch or put")
    assert response.status_code == 400, response.reason
    json_resp = response.json()
    assert "requires at least one school class per school" in json_resp["detail"]
    async with UDM(**udm_kwargs) as udm:
        lib_users = await User.get_all(udm, ou1, f"username={user.name}")
        assert len(lib_users) == 1
        assert isinstance(lib_users[0], Teacher)  # unchanged


@pytest.mark.asyncio
@pytest.mark.parametrize("method", ("patch", "put"))
async def test_modify_username_checks(
    auth_header,
    check_password,
    retry_http_502,
    url_fragment,
    new_import_user,
    create_ou_using_python,
    random_user_create_model,
    random_name,
    import_config,
    udm_kwargs,
    schedule_delete_user_name_using_udm,
    import_user_to_create_model_kwargs,
    new_workgroup_using_lib,
    method: str,
):
    school = await create_ou_using_python()
    user: ImportUser = await new_import_user(school, "teacher", schools=[school])
    schedule_delete_user_name_using_udm(user.name)

    new_username: str = ""
    while len(new_username) < 50:
        new_username += random_name()

    user_url = f"{url_fragment}/users/{user.name}"
    if method == "patch":
        patch_data = {"name": new_username}
        response = retry_http_502(
            requests.patch,
            user_url,
            headers=auth_header,
            json=patch_data,
        )
    elif method == "put":
        old_data = import_user_to_create_model_kwargs(user, ["name"])
        modified_user = UserCreateModel(name=new_username, **old_data)
        response = retry_http_502(
            requests.put,
            user_url,
            headers=auth_header,
            data=modified_user.json(),
        )
    else:
        raise RuntimeError("Method not supported")
    assert response.status_code == 400, response.reason
    json_resp = response.json()
    assert "is longer than allowed" in json_resp["detail"]
    async with UDM(**udm_kwargs) as udm:
        lib_users = await User.get_all(udm, school, f"username={user.name}")
        assert len(lib_users) == 1
        assert lib_users[0].name == user.name  # unchanged


@pytest.mark.asyncio
@pytest.mark.parametrize("role", USER_ROLES, ids=role_id)
async def test_delete(
    auth_header,
    retry_http_502,
    url_fragment,
    create_ou_using_python,
    new_school_user,
    udm_kwargs,
    role: Role,
):
    school = await create_ou_using_python()
    user: User = await new_school_user(school, role.name)
    assert isinstance(user, role.klass)
    response = retry_http_502(
        requests.delete,
        f"{url_fragment}/users/{user.name}",
        headers=auth_header,
    )
    assert response.status_code == 204, response.reason
    async with UDM(**udm_kwargs) as udm:
        lib_users = await User.get_all(udm, school, f"username={user.name}")
    assert len(lib_users) == 0


def test_delete_non_existent(auth_header, retry_http_502, url_fragment, random_name):
    response = retry_http_502(
        requests.delete,
        f"{url_fragment}/users/{random_name()}",
        headers=auth_header,
    )
    assert response.status_code == 404, response.reason


@pytest.mark.asyncio
@pytest.mark.parametrize("role", USER_ROLES, ids=role_id)
@pytest.mark.parametrize("method", ("patch", "put"))
async def test_rename(
    auth_header,
    retry_http_502,
    import_user_to_create_model_kwargs,
    url_fragment,
    create_ou_using_python,
    new_import_user,
    create_random_users,
    random_user_create_model,
    random_name,
    import_config,
    udm_kwargs,
    role: Role,
    method: str,
    schedule_delete_user_name_using_udm,
):
    school = await create_ou_using_python()
    if method == "patch":
        user: ImportUser = await new_import_user(school, role.name)
        new_name = f"t.new.{random_name()}.{random_name()}"[:15]
        # dot at the end not allowed
        if new_name[-1] == ".":
            new_name = new_name[:-1]
        schedule_delete_user_name_using_udm(new_name)
        response = retry_http_502(
            requests.patch,
            f"{url_fragment}/users/{user.name}",
            headers=auth_header,
            json={"name": new_name},
        )
    elif method == "put":
        user_data = (await random_user_create_model(school, roles=[url_fragment, url_fragment])).dict(
            exclude={"roles"}
        )
        user = (await create_random_users(school, {role.name: 1}, **user_data))[0]
        new_name = f"t.new.{random_name()}.{random_name()}"[:15]
        # dot at the end not allowed
        if new_name[-1] == ".":
            new_name = new_name[:-1]
        old_data = user.dict(exclude={"name"})
        modified_user = UserCreateModel(name=new_name, **old_data)
        response = retry_http_502(
            requests.put,
            f"{url_fragment}/users/{user.name}",
            headers=auth_header,
            data=modified_user.json(),
        )
    else:
        raise RuntimeError("method not supported")
    assert response.status_code == 200, f"{response.reason} -- {response.content[:4096]}"
    api_user = UserModel(**response.json())
    assert api_user.name == new_name
    async with UDM(**udm_kwargs) as udm:
        lib_users = await User.get_all(udm, school, f"username={user.name}")
        assert len(lib_users) == 0
        lib_users = await User.get_all(udm, school, f"username={new_name}")
        assert len(lib_users) == 1
        assert isinstance(lib_users[0], role.klass)


@pytest.mark.asyncio
@pytest.mark.parametrize("role", USER_ROLES, ids=role_id)
@pytest.mark.parametrize("method", ("patch", "put"))
async def test_school_change(
    auth_header,
    retry_http_502,
    url_fragment,
    create_random_users,
    create_multiple_ous,
    udm_kwargs,
    role: Role,
    method: str,
):
    ou1_name, ou2_name = await create_multiple_ous(2)
    user = (
        await create_random_users(ou1_name, {role.name: 1}, school=f"{url_fragment}/schools/{ou1_name}")
    )[0]
    async with UDM(**udm_kwargs) as udm:
        lib_users = await User.get_all(udm, ou1_name, f"username={user.name}")
    assert len(lib_users) == 1
    assert isinstance(lib_users[0], role.klass)
    assert lib_users[0].school == ou1_name
    assert lib_users[0].schools == [ou1_name]
    if role.name == "teacher_and_staff":
        roles = {
            f"staff:school:{ou1_name}",
            f"teacher:school:{ou1_name}",
        }
    else:
        roles = {f"{role.name}:school:{ou1_name}"}
    assert set(lib_users[0].ucsschool_roles) == roles
    url = f"{url_fragment}/schools/{ou2_name}"
    _url: SplitResult = urlsplit(url)
    new_school_url = HttpUrl(url, path=_url.path, scheme=_url.scheme, host=_url.netloc)
    if method == "patch":
        patch_data = dict(school=new_school_url, schools=[new_school_url])
        response = retry_http_502(
            requests.patch,
            f"{url_fragment}/users/{user.name}",
            headers=auth_header,
            json=patch_data,
        )
    elif method == "put":
        old_data = user.dict(exclude={"school", "schools", "school_classes", "workgroups"})
        modified_user = UserCreateModel(school=new_school_url, schools=[new_school_url], **old_data)
        response = retry_http_502(
            requests.put,
            f"{url_fragment}/users/{user.name}",
            headers=auth_header,
            data=modified_user.json(),
        )
    json_response = response.json()
    assert response.status_code == 200, response.reason
    async with UDM(**udm_kwargs) as udm:
        async for udm_user in udm.get("users/user").search(filter_format("uid=%s", (user.name,))):
            udm_user_schools = udm_user.props.school
            assert udm_user_schools == [ou2_name]
        api_user = UserModel(**json_response)
        assert (
            api_user.unscheme_and_unquote(str(api_user.school)) == f"{url_fragment}/schools/{ou2_name}"
        )
        lib_users = await User.get_all(udm, ou2_name, f"username={user.name}")
    assert len(lib_users) == 1
    assert isinstance(lib_users[0], role.klass)
    assert lib_users[0].school == ou2_name
    assert lib_users[0].schools == [ou2_name]
    if role.name == "teacher_and_staff":
        roles = {
            f"staff:school:{ou2_name}",
            f"teacher:school:{ou2_name}",
        }
    else:
        roles = {f"{role.name}:school:{ou2_name}"}
    assert set(lib_users[0].ucsschool_roles) == roles


@pytest.mark.asyncio
@pytest.mark.parametrize("method", ("patch", "put"))
async def test_school_change_verify_groups(
    auth_header,
    retry_http_502,
    url_fragment,
    create_random_users,
    create_multiple_ous,
    udm_kwargs,
    ldap_base,
    new_school_class_using_lib,
    new_workgroup_using_lib,
    method: str,
):
    role: Role = Role("teacher", Teacher)
    ou1_name, ou2_name, ou3_name = await create_multiple_ous(3)
    sc_dn1, sc_attr1 = await new_school_class_using_lib(ou1_name)
    sc_dn2, sc_attr2 = await new_school_class_using_lib(ou2_name)
    sc_dn3, sc_attr3 = await new_school_class_using_lib(ou3_name)
    wg_dn1, wg_attr1 = await new_workgroup_using_lib(ou1_name)
    wg_dn2, wg_attr2 = await new_workgroup_using_lib(ou2_name)
    wg_dn3, wg_attr3 = await new_workgroup_using_lib(ou3_name)
    user = (
        await create_random_users(
            ou1_name,
            {role.name: 1},
            school=f"{url_fragment}/schools/{ou1_name}",
            schools=[f"{url_fragment}/schools/{ou1_name}", f"{url_fragment}/schools/{ou2_name}"],
            school_classes={ou1_name: [sc_attr1["name"]], ou2_name: [sc_attr2["name"]]},
            workgroups={ou1_name: [wg_attr1["name"]], ou2_name: [wg_attr2["name"]]},
        )
    )[0]
    async with UDM(**udm_kwargs) as udm:
        lib_user = (await User.get_all(udm, ou1_name, f"username={user.name}"))[0]
        udm_user = await udm.get("users/user").get(lib_user.dn)
        udm_user.options["ucsschoolAdministrator"] = True
        udm_user.props.groups.extend(
            [
                f"cn=admins-{ou1_name},cn=ouadmins,cn=groups,{ldap_base}",
                f"cn=admins-{ou2_name},cn=ouadmins,cn=groups,{ldap_base}",
            ]
        )
        await udm_user.save()
    assert isinstance(lib_user, role.klass)
    assert lib_user.school == ou1_name
    assert set(lib_user.schools) == {ou1_name, ou2_name}
    assert set(lib_user.ucsschool_roles) == {
        f"{role.name}:school:{ou1_name}",
        f"{role.name}:school:{ou2_name}",
    }

    if method == "patch":
        patch_data = dict(
            schools=[user.school, f"{url_fragment}/schools/{ou3_name}"],
            school_classes={ou1_name: user.school_classes[ou1_name], ou3_name: [sc_attr3["name"]]},
            workgroups={ou1_name: user.workgroups[ou1_name], ou3_name: [wg_attr3["name"]]},
        )
        response = retry_http_502(
            requests.patch,
            f"{url_fragment}/users/{user.name}",
            headers=auth_header,
            json=patch_data,
        )
    elif method == "put":
        old_data = user.dict(exclude={"school", "schools", "school_classes", "workgroups"})
        modified_user = UserCreateModel(
            school=user.school,
            schools=[user.school, f"{url_fragment}/schools/{ou3_name}"],
            school_classes={ou1_name: user.school_classes[ou1_name], ou3_name: [sc_attr3["name"]]},
            workgroups={ou1_name: user.workgroups[ou1_name], ou3_name: [wg_attr3["name"]]},
            **old_data,
        )
        response = retry_http_502(
            requests.put,
            f"{url_fragment}/users/{user.name}",
            headers=auth_header,
            data=modified_user.json(),
        )
    else:
        raise RuntimeError(f"Unknown method: {method}")
    json_response = response.json()
    assert response.status_code == 200, response.reason
    async with UDM(**udm_kwargs) as udm:
        async for udm_user in udm.get("users/user").search(filter_format("uid=%s", (user.name,))):
            udm_user_schools = udm_user.props.school
            assert udm_user_schools == [ou1_name, ou3_name]
        api_user = UserModel(**json_response)
        assert (
            api_user.unscheme_and_unquote(str(api_user.school)) == f"{url_fragment}/schools/{ou1_name}"
        )
        lib_user = (await User.get_all(udm, ou1_name, f"username={user.name}"))[0]
        udm_user = await udm.get("users/user").get(lib_user.dn)
        groups = udm_user.props.groups
    expected_groups: Set[str] = {
        f"cn=Domain Users {ou1_name},cn=groups,ou={ou1_name},{ldap_base}",
        f"cn=lehrer-{ou1_name},cn=groups,ou={ou1_name},{ldap_base}",
        f"cn=admins-{ou1_name},cn=ouadmins,cn=groups,{ldap_base}",
        f"cn=Domain Users {ou3_name},cn=groups,ou={ou3_name},{ldap_base}",
        f"cn=lehrer-{ou3_name},cn=groups,ou={ou3_name},{ldap_base}",
    }
    for ou in (ou1_name, ou3_name):
        for class_name in lib_user.school_classes[ou]:
            expected_groups.add(
                f"cn={class_name},cn=klassen,cn=schueler,cn=groups,ou={ou},{ldap_base}",
            )
        for wg_name in lib_user.workgroups[ou]:
            expected_groups.add(
                f"cn={wg_name},cn=schueler,cn=groups,ou={ou},{ldap_base}",
            )

    assert set(groups) == expected_groups
    assert isinstance(lib_user, role.klass)
    assert lib_user.school == ou1_name
    assert lib_user.schools == [ou1_name, ou3_name]
    assert set(lib_user.ucsschool_roles) == {
        f"{role.name}:school:{ou1_name}",
        f"{role.name}:school:{ou3_name}",
    }


@pytest.mark.asyncio
@pytest.mark.parametrize("role", USER_ROLES, ids=role_id)
@pytest.mark.parametrize("http_method", ("patch", "put"))
async def test_change_disable(
    auth_header,
    check_password,
    retry_http_502,
    url_fragment,
    create_ou_using_python,
    create_random_users,
    import_config,
    udm_kwargs,
    role: Role,
    http_method: str,
):
    school = await create_ou_using_python()
    user = (await create_random_users(school, {role.name: 1}, disabled=False))[0]
    assert user.disabled is False
    async with UDM(**udm_kwargs) as udm:
        lib_users = await User.get_all(udm, school, f"username={user.name}")
        assert len(lib_users) == 1
    # delete password, so PUT with complete user data will not produce
    # 'Password has been used before. Please choose a different one.'
    password = user.password
    user.password = None
    await check_password(lib_users[0].dn, password)

    user.disabled = True
    if http_method == "patch":
        response = retry_http_502(
            requests.patch,
            f"{url_fragment}/users/{user.name}",
            headers=auth_header,
            json={"disabled": user.disabled},
        )
    else:
        response = retry_http_502(
            requests.put,
            f"{url_fragment}/users/{user.name}",
            headers=auth_header,
            data=user.json(),
        )
    assert response.status_code == 200, response.reason
    response = retry_http_502(requests.get, f"{url_fragment}/users/{user.name}", headers=auth_header)
    assert response.status_code == 200, response.reason
    await asyncio.sleep(5)
    api_user = UserModel(**response.json())
    assert api_user.disabled == user.disabled
    with pytest.raises(BindError):
        await check_password(lib_users[0].dn, password)

    user.disabled = False
    if http_method == "patch":
        response = retry_http_502(
            requests.patch,
            f"{url_fragment}/users/{user.name}",
            headers=auth_header,
            json={"disabled": user.disabled},
        )
    else:
        response = retry_http_502(
            requests.put,
            f"{url_fragment}/users/{user.name}",
            headers=auth_header,
            data=user.json(),
        )
    assert response.status_code == 200, response.reason
    await asyncio.sleep(5)
    response = retry_http_502(requests.get, f"{url_fragment}/users/{user.name}", headers=auth_header)
    api_user = UserModel(**response.json())
    assert api_user.disabled == user.disabled
    await check_password(lib_users[0].dn, password)


@pytest.mark.asyncio
@pytest.mark.parametrize("role", USER_ROLES, ids=role_id)
@pytest.mark.parametrize("http_method", ("patch", "put"))
async def test_change_password(
    auth_header,
    check_password,
    retry_http_502,
    import_user_to_create_model_kwargs,
    url_fragment,
    create_ou_using_python,
    new_import_user,
    import_config,
    role: Role,
    http_method: str,
):
    school = await create_ou_using_python()
    user: ImportUser = await new_import_user(school, role.name, disabled=False)
    assert user.disabled is False
    old_password = user.password
    await check_password(user.dn, old_password)
    logger.debug("OK: can login with old password")
    new_password = fake.password(length=20)
    user.password = new_password
    assert user.password != old_password
    if http_method == "patch":
        response = retry_http_502(
            requests.patch,
            f"{url_fragment}/users/{user.name}",
            headers=auth_header,
            json={"password": new_password},
        )
    else:
        create_model_kwargs = import_user_to_create_model_kwargs(user)
        create_model = UserCreateModel(**create_model_kwargs)
        create_model.password = create_model.password.get_secret_value()
        response = retry_http_502(
            requests.put,
            f"{url_fragment}/users/{user.name}",
            headers=auth_header,
            data=create_model.json(),
        )
    assert response.status_code == 200, response.reason
    await check_password(user.dn, new_password)


@pytest.mark.asyncio
async def test_set_password_hashes_uldap3_error(create_ou_using_python, new_school_user, password_hash):
    role = random.choice(USER_ROLES)
    school = await create_ou_using_python()
    user: User = await new_school_user(school, role.name, disabled=False, school_classes={})
    assert user.disabled is False
    user_dn = get_dn_of_user(user.name)
    password_new, password_new_hashes = await password_hash()
    # replace uid
    uid = user_dn[user_dn.find("=") + 1 : user_dn.find(",")]
    new_user_dn = user_dn.replace(uid, "does.not.exist", 1)
    try:
        await set_password_hashes(new_user_dn, password_new_hashes)
    except (UModifyError, UNoObject) as exc:
        logger.debug("OK: Expected exception and error got thrown: %s", exc)


@pytest.mark.asyncio
async def test_set_password_hashes(
    check_password, create_ou_using_python, new_school_user, password_hash
):
    role = random.choice(USER_ROLES)
    school = await create_ou_using_python()
    user: User = await new_school_user(school, role.name, disabled=False, school_classes={})
    assert user.disabled is False
    password_old = user.password
    user_dn = get_dn_of_user(user.name)
    await check_password(user_dn, password_old)
    logger.debug("OK: can login as user with its old password.")
    password_new, password_new_hashes = await password_hash()
    assert password_old != password_new
    await set_password_hashes(user_dn, password_new_hashes)
    await check_password(user_dn, password_new)
    logger.debug("OK: can login as user with new password.")
    with pytest.raises(BindError):
        await check_password(user_dn, password_old)
    logger.debug("OK: cannot login as user with old password.")


@pytest.mark.asyncio
@pytest.mark.parametrize("role", USER_ROLES, ids=role_id)
@pytest.mark.parametrize("model", (UserCreateModel, UserPatchModel))
async def test_not_password_and_password_hashes(
    role: Role,
    model: Union[Type[UserCreateModel], Type[UserPatchModel]],
    create_ou_using_python,
    random_user_create_model,
    password_hash,
    url_fragment,
):
    if role.name == "teacher_and_staff":
        roles = ["staff", "teacher"]
    else:
        roles = [role.name]
    school = await create_ou_using_python()
    user_data = await random_user_create_model(
        school,
        roles=[f"{url_fragment}/roles/{role_}" for role_ in roles],
        disabled=False,
        school_classes={},
    )
    password_new, password_new_hashes = await password_hash()

    user_data.password = fake.password()
    user_data.kelvin_password_hashes = None
    if issubclass(model, UserPatchModel):
        model(password=user_data.password)
    else:
        model(**user_data.dict())

    user_data.password = None
    user_data.kelvin_password_hashes = password_new_hashes
    if issubclass(model, UserPatchModel):
        model(kelvin_password_hashes=user_data.kelvin_password_hashes)
    else:
        model(**user_data.dict())

    user_data.password = fake.password()
    user_data.kelvin_password_hashes = password_new_hashes
    with pytest.raises(ValueError):
        if issubclass(model, UserPatchModel):
            model(password=user_data.password, kelvin_password_hashes=user_data.kelvin_password_hashes)
        else:
            model(**user_data.dict())


@pytest.mark.asyncio
async def test_krb_5_keys_are_base64_binaries(password_hash):
    password_new, password_new_hashes = await password_hash()
    assert PasswordsHashes(**password_new_hashes.dict())

    password_new_hashes.krb_5_key.append("bar")
    with pytest.raises(ValueError) as exc_info:
        _ = PasswordsHashes(**password_new_hashes.dict())
    assert "krb_5_key" in str(exc_info.value)
    assert "must be base64 encoded" in str(exc_info.value)


# tests for multiple schools
@pytest.mark.asyncio
@pytest.mark.parametrize("role", USER_ROLES, ids=role_id)
@pytest.mark.parametrize("dont_set_school_directly", (True, False))
async def test_create_with_multiple_schools(
    auth_header,
    retry_http_502,
    url_fragment,
    create_multiple_ous,
    random_user_create_model,
    udm_kwargs,
    schedule_delete_user_name_using_udm,
    role: Role,
    dont_set_school_directly: bool,
):
    """
    Create user with 3 schools.
    The primary OU (`school` parameter) will be sent in the POST request only if
    `dont_set_school_directly` == False.
    Only `school` and `schools` are validated.
    """
    if role.name == "teacher_and_staff":
        roles = ["staff", "teacher"]
    else:
        roles = [role.name]
    school1, school2, school3 = await create_multiple_ous(3)

    r_user = await random_user_create_model(
        school1,
        schools=[
            f"{url_fragment}/schools/{school1}",
            f"{url_fragment}/schools/{school2}",
            f"{url_fragment}/schools/{school3}",
        ],
        roles=[f"{url_fragment}/roles/{role_}" for role_ in roles],
        disabled=False,
    )
    async with UDM(**udm_kwargs) as udm:
        lib_users = await User.get_all(udm, school1, f"username={r_user.name}")
    assert len(lib_users) == 0

    data = r_user.dict(
        exclude={
            "birthday",
            "disabled",
            "email",
            "expiration_date",
            "source_uid",
            "ucsschool_roles",
            "udm_properties",
        }
    )
    if dont_set_school_directly:
        del data["school"]

    schedule_delete_user_name_using_udm(r_user.name)
    response = retry_http_502(
        requests.post,
        f"{url_fragment}/users/",
        headers={"Content-Type": "application/json", **auth_header},
        json=data,
    )
    assert response.status_code == 201, f"{response.__dict__!r}"
    async with UDM(**udm_kwargs) as udm:
        lib_users = await User.get_all(udm, school1, f"username={r_user.name}")
    assert len(lib_users) == 1
    lib_user = lib_users[0]
    assert isinstance(lib_user, role.klass)
    expected_school = sorted([school1, school2, school3])[0] if dont_set_school_directly else school1
    assert lib_user.school == expected_school
    assert set(lib_user.schools) == {school1, school2, school3}


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "role",
    [role for role in USER_ROLES if role.name != "staff"],
    ids=role_id,
)
@pytest.mark.parametrize("method", ("patch", "put", "putwithschool"))
async def test_add_additional_schools(
    auth_header,
    retry_http_502,
    url_fragment,
    create_random_users,
    create_multiple_ous,
    random_name,
    udm_kwargs,
    role: Role,
    method: str,
):
    """
    Create user with 1 school and 1 school class.
    Then add 2nd school and school class. Verify school, schools, school_classes, ucsschool_roles.
    Then add 3rd school and school class. Verify school, schools, school_classes, ucsschool_roles.
    """
    school1, school2, school3 = await create_multiple_ous(3)
    school_class_names = {
        school1: random_name(),
        school2: random_name(),
        school3: random_name(),
    }
    school_classes = {school1: [school_class_names[school1]]}
    user = (
        await create_random_users(
            school1,
            {role.name: 1},
            school=f"{url_fragment}/schools/{school1}",
            school_classes=school_classes,
        )
    )[0]
    async with UDM(**udm_kwargs) as udm:
        lib_users = await User.get_all(udm, school1, f"username={user.name}")
    assert len(lib_users) == 1
    lib_user = lib_users[0]
    assert isinstance(lib_user, role.klass)
    assert lib_user.school == school1
    assert lib_user.schools == [school1]
    assert lib_user.school_classes[school1]
    assert not lib_user.school_classes.get(school2)
    assert not lib_user.school_classes.get(school3)

    new_schools = [school1]
    new_school_classes = school_classes.copy()
    for new_school in [school2, school3]:
        new_schools.append(new_school)
        new_school_classes[new_school] = [school_class_names[new_school]]

        if method == "patch":
            patch_data = dict(
                schools=[f"{url_fragment}/schools/{school}" for school in new_schools],
                school_classes=new_school_classes,
            )
            response = retry_http_502(
                requests.patch,
                f"{url_fragment}/users/{user.name}",
                headers=auth_header,
                json=patch_data,
            )
        elif method in {"put", "putwithschool"}:
            exclude = {"school", "schools", "school_classes", "password"}
            if method == "putwithschool":
                exclude.remove("school")
            old_data = user.dict(exclude=exclude)
            modified_user = UserCreateModel(
                schools=[f"{url_fragment}/schools/{school}" for school in new_schools],
                school_classes=new_school_classes,
                **old_data,
            )
            response = retry_http_502(
                requests.put,
                f"{url_fragment}/users/{user.name}",
                headers=auth_header,
                data=modified_user.json(exclude={"school"}),
            )
        json_response = response.json()
        logger.debug("RESPONSE")
        logger.debug(json_response)
        assert response.status_code == 200, response.reason
        async with UDM(**udm_kwargs) as udm:
            async for udm_user in udm.get("users/user").search(filter_format("uid=%s", (user.name,))):
                assert set(udm_user.props.school) == set(new_schools)
            api_user = UserModel(**json_response)
            lib_users = await User.get_all(udm, school1, f"username={user.name}")
        assert len(lib_users) == 1
        assert isinstance(lib_user, role.klass)
        lib_user = lib_users[0]

        # check main school
        assert lib_user.school == school1
        assert api_user.unscheme_and_unquote(str(api_user.school)) == f"{url_fragment}/schools/{school1}"

        # check schools
        assert set(lib_user.schools) == set(new_schools)
        assert {api_user.unscheme_and_unquote(str(school)) for school in api_user.schools} == {
            f"{url_fragment}/schools/{school}" for school in new_schools
        }

        # check roles
        if role.name == "teacher_and_staff":
            roles = []
            for school in new_schools:
                roles.extend([f"staff:school:{school}", f"teacher:school:{school}"])
        else:
            roles = [f"{role.name}:school:{school}" for school in new_schools]
        assert set(lib_user.ucsschool_roles) == set(roles)

        # check school_classes
        for school in new_schools:
            class_name = school_class_names[school]
            assert api_user.school_classes[school] == [class_name]
            assert lib_user.school_classes[school] == [f"{school}-{class_name}"]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "role",
    [role for role in USER_ROLES if role.name != "staff"],
    ids=role_id,
)
@pytest.mark.parametrize("method", ("patch", "put"))
async def test_set_school_with_multiple_schools(
    auth_header,
    retry_http_502,
    url_fragment,
    create_random_users,
    create_multiple_ous,
    random_name,
    udm_kwargs,
    role: Role,
    method: str,
):
    """
    Test that setting `school` without `schools` sets `schools` to `[school]`.

    Create user with 3 schools and 3 school classes.
    Then send 1 school and 1 school class.
    Verify school, schools, school_classes, ucsschool_roles.
    """
    school1, school2, school3 = await create_multiple_ous(3)
    school1_class = random_name()
    school2_class = random_name()
    school3_class = random_name()
    school_classes = {
        school1: [school1_class],
        school2: [school2_class],
        school3: [school3_class],
    }
    user = (
        await create_random_users(
            school1,
            {role.name: 1},
            school=f"{url_fragment}/schools/{school1}",
            schools=[
                f"{url_fragment}/schools/{school1}",
                f"{url_fragment}/schools/{school2}",
                f"{url_fragment}/schools/{school3}",
            ],
            school_classes=school_classes,
        )
    )[0]
    async with UDM(**udm_kwargs) as udm:
        lib_users = await User.get_all(udm, school1, f"username={user.name}")
    assert len(lib_users) == 1
    lib_user = lib_users[0]
    assert isinstance(lib_user, role.klass)
    assert lib_user.school == school1
    assert set(lib_user.schools) == {school1, school2, school3}
    assert lib_user.school_classes[school1] == [f"{school1}-{school1_class}"]
    assert lib_user.school_classes[school2] == [f"{school2}-{school2_class}"]
    assert lib_user.school_classes[school3] == [f"{school3}-{school3_class}"]

    new_school_classes = {
        school2: [school2_class],
    }
    new_school_classes[school2] = [school2_class]
    if method == "patch":
        patch_data = dict(school=f"{url_fragment}/schools/{school2}", school_classes=new_school_classes)
        response = retry_http_502(
            requests.patch,
            f"{url_fragment}/users/{user.name}",
            headers=auth_header,
            json=patch_data,
        )
    elif method == "put":
        old_data = user.dict(exclude={"school", "schools", "school_classes", "workgroups"})
        modified_user = UserCreateModel(
            school=f"{url_fragment}/schools/{school2}", school_classes=new_school_classes, **old_data
        )
        response = retry_http_502(
            requests.put,
            f"{url_fragment}/users/{user.name}",
            headers=auth_header,
            data=modified_user.json(),
        )
    json_response = response.json()
    assert response.status_code == 200, response.reason
    async with UDM(**udm_kwargs) as udm:
        async for udm_user in udm.get("users/user").search(filter_format("uid=%s", (user.name,))):
            assert set(udm_user.props.school) == {school2}
        api_user = UserModel(**json_response)
        lib_users = await User.get_all(udm, school2, f"username={user.name}")
    assert len(lib_users) == 1
    assert isinstance(lib_user, role.klass)
    lib_user = lib_users[0]

    # check main school
    assert lib_user.school == school2
    assert api_user.unscheme_and_unquote(str(api_user.school)) == f"{url_fragment}/schools/{school2}"

    # check schools
    assert set(lib_user.schools) == {school2}
    assert {api_user.unscheme_and_unquote(str(school)) for school in api_user.schools} == {
        f"{url_fragment}/schools/{school2}"
    }

    # check roles
    if role.name == "teacher_and_staff":
        roles = {
            f"staff:school:{school2}",
            f"teacher:school:{school2}",
        }
    else:
        roles = {f"{role.name}:school:{school2}"}
    assert set(lib_user.ucsschool_roles) == roles

    # check school_classes
    assert not api_user.school_classes.get(school1)
    assert api_user.school_classes[school2] == [school2_class]
    assert not lib_user.school_classes.get(school1)
    assert lib_user.school_classes[school2] == [f"{school2}-{school2_class}"]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "role",
    [role for role in USER_ROLES if role.name != "staff"],
    ids=role_id,
)
@pytest.mark.parametrize("method", ("patch", "put"))
async def test_change_school_with_multiple_schools(
    auth_header,
    retry_http_502,
    url_fragment,
    create_random_users,
    create_multiple_ous,
    random_name,
    udm_kwargs,
    role: Role,
    method: str,
):
    """
    Test that it's possible to change `school` to one of the other OUs on `schools`.

    Create user with 3 schools and 3 school classes.
    Then change `school` to another OU from the ones in `schools`.
    Verify school, schools, school_classes, ucsschool_roles.
    """
    school1, school2, school3 = await create_multiple_ous(3)
    school1_class = random_name()
    school2_class = random_name()
    school3_class = random_name()
    school_classes = {
        school1: [school1_class],
        school2: [school2_class],
        school3: [school3_class],
    }
    user = (
        await create_random_users(
            school1,
            {role.name: 1},
            school=f"{url_fragment}/schools/{school1}",
            schools=[
                f"{url_fragment}/schools/{school1}",
                f"{url_fragment}/schools/{school2}",
                f"{url_fragment}/schools/{school3}",
            ],
            school_classes=school_classes,
        )
    )[0]
    async with UDM(**udm_kwargs) as udm:
        lib_users = await User.get_all(udm, school1, f"username={user.name}")
    assert len(lib_users) == 1
    lib_user = lib_users[0]
    assert isinstance(lib_user, role.klass)
    assert lib_user.school == school1
    assert set(lib_user.schools) == {school1, school2, school3}
    assert lib_user.school_classes[school1] == [f"{school1}-{school1_class}"]
    assert lib_user.school_classes[school2] == [f"{school2}-{school2_class}"]
    assert lib_user.school_classes[school3] == [f"{school3}-{school3_class}"]

    if method == "patch":
        patch_data = dict(
            school=f"{url_fragment}/schools/{school2}",
            schools=[
                f"{url_fragment}/schools/{school1}",
                f"{url_fragment}/schools/{school2}",
                f"{url_fragment}/schools/{school3}",
            ],
            school_classes=school_classes,
        )
        response = retry_http_502(
            requests.patch,
            f"{url_fragment}/users/{user.name}",
            headers=auth_header,
            json=patch_data,
        )
    elif method == "put":
        old_data = user.dict(exclude={"school"})
        modified_user = UserCreateModel(school=f"{url_fragment}/schools/{school2}", **old_data)
        response = retry_http_502(
            requests.put,
            f"{url_fragment}/users/{user.name}",
            headers=auth_header,
            data=modified_user.json(),
        )
    else:
        raise RuntimeError(f"method {method} not supported")
    json_response = response.json()
    logger.debug("RESPONSE")
    logger.debug(json_response)
    assert response.status_code == 200, response.reason
    async with UDM(**udm_kwargs) as udm:
        async for udm_user in udm.get("users/user").search(filter_format("uid=%s", (user.name,))):
            assert set(udm_user.props.school) == {school1, school2, school3}
        api_user = UserModel(**json_response)
        lib_users = await User.get_all(udm, school2, f"username={user.name}")
    assert len(lib_users) == 1
    assert isinstance(lib_user, role.klass)
    lib_user = lib_users[0]

    # check main school
    assert lib_user.school == school2
    assert api_user.unscheme_and_unquote(str(api_user.school)) == f"{url_fragment}/schools/{school2}"

    # check schools
    assert set(lib_user.schools) == {school1, school2, school3}
    assert {api_user.unscheme_and_unquote(str(school)) for school in api_user.schools} == {
        f"{url_fragment}/schools/{school1}",
        f"{url_fragment}/schools/{school2}",
        f"{url_fragment}/schools/{school3}",
    }

    # check roles
    if role.name == "teacher_and_staff":
        roles = {
            f"staff:school:{school1}",
            f"teacher:school:{school1}",
            f"staff:school:{school2}",
            f"teacher:school:{school2}",
            f"staff:school:{school3}",
            f"teacher:school:{school3}",
        }
    else:
        roles = {
            f"{role.name}:school:{school1}",
            f"{role.name}:school:{school2}",
            f"{role.name}:school:{school3}",
        }
    assert set(lib_user.ucsschool_roles) == roles

    # check school_classes
    assert api_user.school_classes[school1] == [school1_class]
    assert api_user.school_classes[school2] == [school2_class]
    assert api_user.school_classes[school3] == [school3_class]
    assert lib_user.school_classes[school1] == [f"{school1}-{school1_class}"]
    assert lib_user.school_classes[school2] == [f"{school2}-{school2_class}"]
    assert lib_user.school_classes[school3] == [f"{school3}-{school3_class}"]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "role",
    [role for role in USER_ROLES if role.name != "staff"],
    ids=role_id,
)
@pytest.mark.parametrize("method", ("patch", "put"))
async def test_change_school_and_schools(
    auth_header,
    retry_http_502,
    url_fragment,
    create_random_users,
    create_multiple_ous,
    random_name,
    udm_kwargs,
    role: Role,
    method: str,
):
    """
    Test that it's possible to add and remove schools in the same request.

    Create user with 2 schools and 2 school classes.
    Then remove the primary OU from `schools` and add a 3rd school to it. Do not send the primary OU.
    Verify school, schools, school_classes, ucsschool_roles.
    """
    school1, school2, school3 = await create_multiple_ous(3)
    school1_class = random_name()
    school2_class = random_name()
    school3_class = random_name()
    school_classes = {
        school1: [school1_class],
        school2: [school2_class],
    }
    user = (
        await create_random_users(
            school1,
            {role.name: 1},
            school=f"{url_fragment}/schools/{school1}",
            schools=[f"{url_fragment}/schools/{school1}", f"{url_fragment}/schools/{school2}"],
            school_classes=school_classes,
        )
    )[0]
    async with UDM(**udm_kwargs) as udm:
        lib_users = await User.get_all(udm, school1, f"username={user.name}")
    assert len(lib_users) == 1
    lib_user = lib_users[0]
    assert isinstance(lib_user, role.klass)
    assert lib_user.school == school1
    assert set(lib_user.schools) == {school1, school2}
    assert lib_user.school_classes[school1] == [f"{school1}-{school1_class}"]
    assert lib_user.school_classes[school2] == [f"{school2}-{school2_class}"]

    new_school_classes = {
        school2: [school2_class],
        school3: [school3_class],
    }
    if method == "patch":
        patch_data = dict(
            schools=[f"{url_fragment}/schools/{school2}", f"{url_fragment}/schools/{school3}"],
            school_classes=new_school_classes,
        )
        response = retry_http_502(
            requests.patch,
            f"{url_fragment}/users/{user.name}",
            headers=auth_header,
            json=patch_data,
        )
    elif method == "put":
        old_data = user.dict(exclude={"school", "schools", "school_classes", "workgroups"})
        modified_user = UserCreateModel(
            schools=[f"{url_fragment}/schools/{school2}", f"{url_fragment}/schools/{school3}"],
            school_classes=new_school_classes,
            **old_data,
        )
        response = retry_http_502(
            requests.put,
            f"{url_fragment}/users/{user.name}",
            headers=auth_header,
            data=modified_user.json(exclude={"school"}),
        )
    else:
        raise RuntimeError(f"method {method} not supported")
    json_response = response.json()
    expected_school = sorted([school2, school3])[0]
    assert response.status_code == 200, response.reason
    async with UDM(**udm_kwargs) as udm:
        async for udm_user in udm.get("users/user").search(filter_format("uid=%s", (user.name,))):
            assert set(udm_user.props.school) == {school2, school3}
        api_user = UserModel(**json_response)
        lib_users = await User.get_all(udm, expected_school, f"username={user.name}")
    assert len(lib_users) == 1
    assert isinstance(lib_user, role.klass)
    lib_user = lib_users[0]

    # check main school
    assert lib_user.school == expected_school, "expected_school failed"
    assert (
        api_user.unscheme_and_unquote(str(api_user.school))
        == f"{url_fragment}/schools/{expected_school}"
    )

    # check schools
    assert set(lib_user.schools) == {school2, school3}
    assert {api_user.unscheme_and_unquote(str(school)) for school in api_user.schools} == {
        f"{url_fragment}/schools/{school2}",
        f"{url_fragment}/schools/{school3}",
    }

    # check roles
    if role.name == "teacher_and_staff":
        roles = {
            f"staff:school:{school2}",
            f"teacher:school:{school2}",
            f"staff:school:{school3}",
            f"teacher:school:{school3}",
        }
    else:
        roles = {f"{role.name}:school:{school2}", f"{role.name}:school:{school3}"}
    assert set(lib_user.ucsschool_roles) == roles

    # check school_classes
    assert not api_user.school_classes.get(school1)
    assert api_user.school_classes[school2] == [school2_class]
    assert api_user.school_classes[school3] == [school3_class]
    assert not lib_user.school_classes.get(school1)
    assert lib_user.school_classes[school2] == [f"{school2}-{school2_class}"]
    assert lib_user.school_classes[school3] == [f"{school3}-{school3_class}"]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "role",
    [role for role in USER_ROLES if role.name != "staff"],
    ids=role_id,
)
@pytest.mark.parametrize("method", ("patch", "put"))
async def test_change_schools_and_classes(
    auth_header,
    retry_http_502,
    url_fragment,
    create_random_users,
    create_multiple_ous,
    random_name,
    udm_kwargs,
    role: Role,
    method: str,
):
    """
    Test that it's possible to add and remove schools in the same request.

    Create user with 2 schools and 2 school classes.
    Then remove the NON-primary OU from `schools` and add a 3rd school to it. Do not send the primary OU.
    Verify school, schools, school_classes, ucsschool_roles.
    """
    school1, school2, school3 = await create_multiple_ous(3)
    school1_class = random_name()
    school2_class = random_name()
    school3_class = random_name()
    school_classes = {
        school1: [school1_class],
        school2: [school2_class],
    }
    user = (
        await create_random_users(
            school1,
            {role.name: 1},
            school=f"{url_fragment}/schools/{school1}",
            schools=[f"{url_fragment}/schools/{school1}", f"{url_fragment}/schools/{school2}"],
            school_classes=school_classes,
        )
    )[0]
    async with UDM(**udm_kwargs) as udm:
        lib_users = await User.get_all(udm, school1, f"username={user.name}")
    assert len(lib_users) == 1
    lib_user = lib_users[0]
    assert isinstance(lib_user, role.klass)
    assert lib_user.school == school1
    assert set(lib_user.schools) == {school1, school2}
    assert lib_user.school_classes[school1] == [f"{school1}-{school1_class}"]
    assert lib_user.school_classes[school2] == [f"{school2}-{school2_class}"]

    new_school_classes = {
        school1: [school1_class],
        school3: [school3_class],
    }
    if method == "patch":
        patch_data = dict(
            schools=[f"{url_fragment}/schools/{school1}", f"{url_fragment}/schools/{school3}"],
            school_classes=new_school_classes,
        )
        response = retry_http_502(
            requests.patch,
            f"{url_fragment}/users/{user.name}",
            headers=auth_header,
            json=patch_data,
        )
    elif method == "put":
        old_data = user.dict(exclude={"school", "schools", "school_classes", "workgroups"})
        modified_user = UserCreateModel(
            schools=[f"{url_fragment}/schools/{school1}", f"{url_fragment}/schools/{school3}"],
            school_classes=new_school_classes,
            **old_data,
        )
        response = retry_http_502(
            requests.put,
            f"{url_fragment}/users/{user.name}",
            headers=auth_header,
            data=modified_user.json(exclude={"school"}),
        )
    json_response = response.json()
    expected_school = school1
    assert response.status_code == 200, response.reason
    async with UDM(**udm_kwargs) as udm:
        async for udm_user in udm.get("users/user").search(filter_format("uid=%s", (user.name,))):
            assert set(udm_user.props.school) == {school1, school3}
        api_user = UserModel(**json_response)
        lib_users = await User.get_all(udm, expected_school, f"username={user.name}")
    assert len(lib_users) == 1
    assert isinstance(lib_user, role.klass)
    lib_user = lib_users[0]

    # check main school
    assert lib_user.school == expected_school, "expected_school failed"
    assert (
        api_user.unscheme_and_unquote(str(api_user.school))
        == f"{url_fragment}/schools/{expected_school}"
    )

    # check schools
    assert set(lib_user.schools) == {school1, school3}
    assert {api_user.unscheme_and_unquote(str(school)) for school in api_user.schools} == {
        f"{url_fragment}/schools/{school1}",
        f"{url_fragment}/schools/{school3}",
    }

    # check roles
    if role.name == "teacher_and_staff":
        roles = {
            f"staff:school:{school1}",
            f"teacher:school:{school1}",
            f"staff:school:{school3}",
            f"teacher:school:{school3}",
        }
    else:
        roles = {f"{role.name}:school:{school1}", f"{role.name}:school:{school3}"}
    assert set(lib_user.ucsschool_roles) == roles

    # check school_classes
    assert not api_user.school_classes.get(school2)
    assert api_user.school_classes[school1] == [school1_class]
    assert api_user.school_classes[school3] == [school3_class]
    assert not lib_user.school_classes.get(school2)
    assert lib_user.school_classes[school1] == [f"{school1}-{school1_class}"]
    assert lib_user.school_classes[school3] == [f"{school3}-{school3_class}"]


@pytest.mark.asyncio
async def test_create_with_non_existing_workgroup_raises(
    auth_header,
    check_password,
    retry_http_502,
    url_fragment,
    create_ou_using_python,
    random_user_create_model,
    random_name,
    import_config,
    udm_kwargs,
    schedule_delete_user_name_using_udm,
):
    school = await create_ou_using_python()
    r_user = await random_user_create_model(school, roles=[f"{url_fragment}/roles/student"])
    title = random_name()
    r_user.udm_properties["title"] = title
    phone = [random_name(), random_name()]
    r_user.udm_properties["phone"] = phone
    r_user.workgroups = {school: ["thiswgdoesnotexist"]}
    data = r_user.json()
    logger.debug("POST data=%r", data)
    async with UDM(**udm_kwargs) as udm:
        lib_users = await User.get_all(udm, school, f"username={r_user.name}")
    assert len(lib_users) == 0
    schedule_delete_user_name_using_udm(r_user.name)  # just in case
    response = retry_http_502(
        requests.post,
        f"{url_fragment}/users/",
        headers={"Content-Type": "application/json", **auth_header},
        data=data,
    )
    assert response.status_code == 400, f"{response.__dict__!r}"
    assert (
        f"Work group '{school}-thiswgdoesnotexist' of school '{school}' does not exist"
        in response.json()["detail"]
    )
    async with UDM(**udm_kwargs) as udm:
        lib_users = await User.get_all(udm, school, f"username={r_user.name}")
    assert len(lib_users) == 0


@pytest.mark.asyncio
@pytest.mark.parametrize("method", ("patch", "put"))
async def test_modify_with_non_existing_workgroup(
    auth_header,
    check_password,
    retry_http_502,
    import_user_to_create_model_kwargs,
    url_fragment,
    create_ou_using_python,
    new_import_user,
    random_user_create_model,
    random_name,
    import_config,
    udm_kwargs,
    method: str,
):
    role: Role = Role("student", Student)
    school = await create_ou_using_python()
    user: ImportUser = await new_import_user(school, role.name, disabled=False)
    await check_password(user.dn, user.password)
    logger.debug("OK: can login with old password")
    old_user_data = import_user_to_create_model_kwargs(user)
    user_create_model = await random_user_create_model(
        school,
        roles=old_user_data["roles"],
        disabled=False,
        school=old_user_data["school"],
        schools=old_user_data["schools"],
    )
    new_user_data = user_create_model.dict(exclude={"name", "record_uid", "source_uid"})
    title = random_name()
    new_user_data["udm_properties"] = {"title": title}
    modified_user = UserCreateModel(**{**old_user_data, **new_user_data})
    modified_user.workgroups = {school: ["thiswgdoesnotexist"]}
    logger.debug(f"{method.upper()} modified_user=%r.", modified_user.dict())
    if method == "patch":
        response = retry_http_502(
            requests.patch,
            f"{url_fragment}/users/{user.name}",
            headers=auth_header,
            data=json.dumps({"workgroups": modified_user.workgroups}),
        )
    elif method == "put":
        response = retry_http_502(
            requests.put,
            f"{url_fragment}/users/{user.name}",
            headers=auth_header,
            data=modified_user.json(),
        )
    assert response.status_code == 400, response.reason
    # check that the user's work groups did not change
    async with UDM(**udm_kwargs) as udm:
        lib_users = await User.get_all(udm, school, f"username={user.name}")
    assert len(lib_users) == 1
    assert lib_users[0].workgroups == {
        k: [f"{school}-{wg}" for wg in v] for k, v in old_user_data["workgroups"].items()
    }


@pytest.mark.asyncio
async def test_create_with_non_existing_school_in_workgroup_raises(
    auth_header,
    check_password,
    retry_http_502,
    url_fragment,
    create_ou_using_python,
    random_user_create_model,
    random_name,
    import_config,
    udm_kwargs,
    schedule_delete_user_name_using_udm,
    new_workgroup_using_lib,
):
    school = await create_ou_using_python()
    wg_dn, wg_attr = await new_workgroup_using_lib(school)
    r_user = await random_user_create_model(school, roles=[f"{url_fragment}/roles/student"])
    title = random_name()
    r_user.udm_properties["title"] = title
    phone = [random_name(), random_name()]
    r_user.udm_properties["phone"] = phone
    r_user.workgroups = {school: [wg_attr["name"]], "thisschooldoesnotexist": []}
    data = r_user.json()
    logger.debug("POST data=%r", data)
    async with UDM(**udm_kwargs) as udm:
        lib_users = await User.get_all(udm, school, f"username={r_user.name}")
    assert len(lib_users) == 0
    schedule_delete_user_name_using_udm(r_user.name)  # just in case
    response = retry_http_502(
        requests.post,
        f"{url_fragment}/users/",
        headers={"Content-Type": "application/json", **auth_header},
        data=data,
    )
    assert response.status_code == 400, f"{response.__dict__!r}"
    assert "School 'thisschooldoesnotexist' in 'workgroups' is missing" in response.json()["detail"]
    async with UDM(**udm_kwargs) as udm:
        lib_users = await User.get_all(udm, school, f"username={r_user.name}")
    assert len(lib_users) == 0


@pytest.mark.asyncio
@pytest.mark.parametrize("windows_check", ("false", "true"))
async def test_create_with_windows_reserved_name_raises(
    auth_header,
    check_password,
    retry_http_502,
    url_fragment,
    create_ou_using_python,
    random_user_create_model,
    random_name,
    import_config,
    udm_kwargs,
    schedule_delete_user_name_using_udm,
    new_workgroup_using_lib,
    set_ucr,
    windows_check,
):
    set_ucr("ucsschool/validation/username/windows-check", windows_check)
    school = await create_ou_using_python()
    wg_dn, wg_attr = await new_workgroup_using_lib(school)
    r_user = await random_user_create_model(school, roles=[f"{url_fragment}/roles/student"])
    r_user.name = "com1"
    data = r_user.json()
    logger.debug("POST data=%r", data)
    async with UDM(**udm_kwargs) as udm:
        lib_users = await User.get_all(udm, school, f"username={r_user.name}")
    assert len(lib_users) == 0
    schedule_delete_user_name_using_udm(r_user.name)  # just in case
    response = retry_http_502(
        requests.post,
        f"{url_fragment}/users/",
        headers={"Content-Type": "application/json", **auth_header},
        data=data,
    )

    if windows_check == "true":
        assert response.status_code == 422, f"{response.__dict__!r}"
        assert (
            response.json()["detail"][0]["msg"] == "May not be a Windows reserved name"
        ), response.json()["detail"]
        async with UDM(**udm_kwargs) as udm:
            lib_users = await User.get_all(udm, school, f"username={r_user.name}")
        assert len(lib_users) == 0
    else:
        assert response.status_code == 201, f"{response.__dict__!r}"
        async with UDM(**udm_kwargs) as udm:
            lib_users = await User.get_all(udm, school, f"username={r_user.name}")
        assert len(lib_users) == 1


@pytest.mark.asyncio
async def test_complete_update_does_not_change_workgroups_if_not_passed(
    auth_header,
    check_password,
    retry_http_502,
    import_user_to_create_model_kwargs,
    url_fragment,
    create_ou_using_python,
    new_import_user,
    random_user_create_model,
    random_name,
    import_config,
    udm_kwargs,
):
    role: Role = Role("student", Student)
    school = await create_ou_using_python()
    user: ImportUser = await new_import_user(school, role.name, disabled=False)
    old_user_data = import_user_to_create_model_kwargs(user)
    user_create_model = await random_user_create_model(
        school,
        roles=old_user_data["roles"],
        disabled=False,
        school=old_user_data["school"],
        schools=old_user_data["schools"],
    )
    new_user_data = user_create_model.dict(exclude={"name", "record_uid", "source_uid"})
    modified_user = UserCreateModel(**{**old_user_data, **new_user_data})
    del modified_user.workgroups
    logger.debug("PUT modified_user=%r.", modified_user.dict())
    response = retry_http_502(
        requests.put,
        f"{url_fragment}/users/{user.name}",
        headers=auth_header,
        data=modified_user.json(),
    )
    assert response.status_code == 200, response.reason
    # check that the user's work groups did not change
    async with UDM(**udm_kwargs) as udm:
        lib_users = await User.get_all(udm, school, f"username={user.name}")
    assert len(lib_users) == 1
    assert lib_users[0].workgroups == {
        k: [f"{school}-{wg}" for wg in v] for k, v in old_user_data["workgroups"].items()
    }


@pytest.mark.asyncio
@pytest.mark.parametrize("role", USER_ROLES, ids=role_id)
@pytest.mark.parametrize("with_schools", [True, False], ids=["with_schools", "schools=[]"])
async def test_create_custom_ucsschool_roles(
    create_ou_using_python,
    random_user_create_model,
    url_fragment,
    retry_http_502,
    auth_header,
    schedule_delete_user_name_using_udm,
    role,
    with_schools,
):
    school = await create_ou_using_python()
    # we also add "student:school:school1", but this should be ignored by KELVIN
    # all ucsschool role strings with context == school are ignored in post
    ucsschool_roles = [
        "student:school:school1",
        "foo:school:school1",
        "test_1:mycon:where",
        "test_2:foo:bar",
    ]
    expected_ucsschool_roles = [f"{role.name}:school:{school}", "test_1:mycon:where", "test_2:foo:bar"]
    roles = [f"{url_fragment}/roles/{role.name}"]
    if role.name == "teacher_and_staff":
        roles = [f"{url_fragment}/roles/staff", f"{url_fragment}/roles/teacher"]
        expected_ucsschool_roles = [
            f"staff:school:{school}",
            f"teacher:school:{school}",
            "test_1:mycon:where",
            "test_2:foo:bar",
        ]
    r_user = await random_user_create_model(school, roles=roles, ucsschool_roles=ucsschool_roles)
    if not with_schools:
        r_user.schools = []
    data = r_user.json()
    logger.debug("POST data=%r", data)
    schedule_delete_user_name_using_udm(r_user.name)
    response = retry_http_502(
        requests.post,
        f"{url_fragment}/users/",
        headers={"Content-Type": "application/json", **auth_header},
        data=data,
    )
    assert response.status_code == 201, f"{response.__dict__!r}"
    response_json = response.json()
    assert set(response_json["ucsschool_roles"]) == set(expected_ucsschool_roles)


@pytest.mark.asyncio
async def test_create_invalid_custom_ucsschool_roles(
    create_ou_using_python,
    random_user_create_model,
    url_fragment,
    retry_http_502,
    auth_header,
    schedule_delete_user_name_using_udm,
):
    school = await create_ou_using_python()
    roles = [f"{url_fragment}/roles/student"]

    for ucsschool_role in ["test_1mycon:where", "test_2:foobar", "foo", ""]:
        with pytest.raises(error_wrappers.ValidationError):
            await random_user_create_model(school, roles=roles, ucsschool_roles=[ucsschool_role])


@pytest.mark.asyncio
@pytest.mark.parametrize("role", USER_ROLES, ids=role_id)
@pytest.mark.parametrize("method", ("patch", "put"))
async def test_modify_custom_ucsschool_roles(
    create_multiple_ous,
    new_import_user,
    url_fragment_https,
    retry_http_502,
    auth_header,
    schedule_delete_user_name_using_udm,
    import_config,
    import_user_to_create_model_kwargs,
    method,
    role,
):
    roles = [role.name]
    if role.name == "teacher_and_staff":
        roles = ["staff", "teacher"]
    school, school2 = await create_multiple_ous(2)
    create_kwargs = {}
    user: ImportUser = await new_import_user(school, role.name, **create_kwargs)
    schedule_delete_user_name_using_udm(user.name)
    user_data = import_user_to_create_model_kwargs(user)
    modified_user = UserCreateModel(**user_data)
    # we also add "teacher:school:{school}", but this should be ignored by KELVIN
    # all ucsschool role strings with context == school are ignored in patch/put
    ucsschool_roles_to_set = [
        "test_1:mycon:where",
        f"foo:bar:{school}",
        f"teacher:school:{school}",
        f"foo:school:{school}",
    ]
    ucsschool_roles_expected = ["test_1:mycon:where", f"foo:bar:{school}"] + [
        f"{role_}:school:{school}" for role_ in roles
    ]
    modified_user.ucsschool_roles = ucsschool_roles_to_set
    logger.debug(f"{method.upper()} data=%r", modified_user)
    if method == "put":
        response = retry_http_502(
            requests.put,
            f"{url_fragment_https}/users/{user.name}",
            headers=auth_header,
            data=modified_user.json(),
        )
    else:
        patch_data = {"ucsschool_roles": [f"foo:bar:{school}", "test_1:mycon:where"]}
        response = retry_http_502(
            requests.patch,
            f"{url_fragment_https}/users/{user.name}",
            headers=auth_header,
            json=patch_data,
        )
    assert response.status_code == 200, f"{response.__dict__!r}"
    response_json = response.json()
    assert set(response_json["ucsschool_roles"]) == set(ucsschool_roles_expected)
    assert set(response_json["roles"]) == set([f"{url_fragment_https}/roles/{role_}" for role_ in roles])
    # one more with school change
    ucsschool_roles_to_set = ["test_1:nextcon:where", f"student:school:{school}", f"foo:bar:{school}"]
    ucsschool_roles_expected = ["test_1:nextcon:where", f"foo:bar:{school}"] + [
        f"{role_}:school:{school2}" for role_ in roles
    ]
    response_json["ucsschool_roles"] = ucsschool_roles_to_set
    response_json["school"] = f"{url_fragment_https}/schools/{school2}"
    response_json["schools"] = [f"{url_fragment_https}/schools/{school2}"]
    response_json["school_classes"] = {school2: ["1a"]}
    response_json["workgroups"] = {}
    response_json["udm_properties"] = {}
    logger.debug(f"{method.upper()} data=%r", response_json)
    if method == "put":
        response = retry_http_502(
            requests.put,
            f"{url_fragment_https}/users/{user.name}",
            headers=auth_header,
            data=json.dumps(response_json),
        )
    else:
        patch_data = {
            "ucsschool_roles": [f"foo:bar:{school}", "test_1:nextcon:where"],
            "school": f"{url_fragment_https}/schools/{school2}",
        }
        response = retry_http_502(
            requests.patch,
            f"{url_fragment_https}/users/{user.name}",
            headers=auth_header,
            json=patch_data,
        )
    assert response.status_code == 200, f"{response.__dict__!r}"
    response_json = response.json()
    assert set(response_json["ucsschool_roles"]) == set(ucsschool_roles_expected)
    assert set(response_json["roles"]) == set([f"{url_fragment_https}/roles/{role_}" for role_ in roles])
    assert response_json["school"] == f"{url_fragment_https}/schools/{school2}"


@pytest.mark.asyncio
@pytest.mark.parametrize("method", ("patch", "put"))
async def test_modify_custom_ucsschool_roles_with_role_change(
    create_ou_using_python,
    new_import_user,
    url_fragment_https,
    retry_http_502,
    auth_header,
    schedule_delete_user_name_using_udm,
    import_config,
    import_user_to_create_model_kwargs,
    method,
):
    school = await create_ou_using_python()
    role_create = "student"
    role_change = "teacher"
    # we also add "staff:school:{school}", but this should be ignored by KELVIN
    # all ucsschool role strings with context == school are ignored in patch/put
    ucsschool_roles_to_set = [
        "test_1:mycon:where",
        f"foo:bar:{school}",
        f"staff:school:{school}",
    ]
    ucsschool_roles_expected = [
        "test_1:mycon:where",
        f"foo:bar:{school}",
        f"{role_change}:school:{school}",
    ]
    create_kwargs = {}
    user: ImportUser = await new_import_user(school, role_create, **create_kwargs)
    schedule_delete_user_name_using_udm(user.name)
    user_data = import_user_to_create_model_kwargs(user)
    modified_user = UserCreateModel(**user_data)
    modified_user.ucsschool_roles = ucsschool_roles_to_set
    modified_user.roles = [f"{url_fragment_https}/roles/{role_change}"]
    logger.debug(f"{method.upper()} data=%r", modified_user)
    if method == "put":
        response = retry_http_502(
            requests.put,
            f"{url_fragment_https}/users/{user.name}",
            headers=auth_header,
            data=modified_user.json(),
        )
    else:
        patch_data = {
            "ucsschool_roles": [f"foo:bar:{school}", "test_1:mycon:where"],
            "roles": [f"{url_fragment_https}/roles/{role_change}"],
        }
        response = retry_http_502(
            requests.patch,
            f"{url_fragment_https}/users/{user.name}",
            headers=auth_header,
            json=patch_data,
        )
    assert response.status_code == 200, f"{response.__dict__!r}"
    response_json = response.json()
    assert set(response_json["ucsschool_roles"]) == set(ucsschool_roles_expected)
    assert response_json["roles"] == [f"{url_fragment_https}/roles/{role_change}"]


@pytest.mark.asyncio
@pytest.mark.parametrize("http_method", ("patch", "put"))
async def test_udm_error_forwarding_on_modify(
    auth_header,
    check_password,
    retry_http_502,
    import_user_to_create_model_kwargs,
    url_fragment,
    create_ou_using_python,
    new_import_user,
    import_config,
    http_method,
):
    school = await create_ou_using_python()
    user: ImportUser = await new_import_user(school, "student", disabled=False)
    assert user.disabled is False
    old_password = user.password
    await check_password(user.dn, old_password)
    logger.debug("OK: can login with old password")
    new_password = "__"
    user.password = new_password
    assert user.password != old_password
    if http_method == "patch":
        response = retry_http_502(
            requests.patch,
            f"{url_fragment}/users/{user.name}",
            headers=auth_header,
            json={"password": new_password},
        )
    else:
        create_model_kwargs = import_user_to_create_model_kwargs(user)
        create_model = UserCreateModel.parse_obj(create_model_kwargs)
        create_model.password = create_model.password.get_secret_value()
        response = retry_http_502(
            requests.put,
            f"{url_fragment}/users/{user.name}",
            headers=auth_header,
            data=create_model.json(),
        )

    expected_return_value = {
        "detail": [
            {
                "loc": ["password"],
                "msg": "Password policy error:"
                " The password is too short, at least 8 characters needed!",
                "type": "UdmError:ModifyError",
            }
        ]
    }

    assert response.json() == expected_return_value


@pytest.mark.asyncio
async def test_udm_error_forwarding_on_create(
    auth_header,
    check_password,
    retry_http_502,
    url_fragment,
    create_ou_using_python,
    random_user_create_model,
    import_config,
    reset_import_config,
    udm_kwargs,
    add_to_import_config,
    schedule_delete_user_name_using_udm,
):
    school = await create_ou_using_python()
    r_user = await random_user_create_model(
        school, roles=[f"{url_fragment}/roles/student"], disabled=False
    )
    r_user.email = "abc@abc.de"
    expected_name = f"test.{r_user.firstname[:2]}.{r_user.lastname[:3]}".lower()

    schedule_delete_user_name_using_udm(expected_name)

    response = retry_http_502(
        requests.post,
        f"{url_fragment}/users/",
        headers={"Content-Type": "application/json", **auth_header},
        json=json.loads(r_user.json()),
    )

    assert response.json() == {
        "detail": [
            {
                "loc": ["mailPrimaryAddress"],
                "msg": "The domain part of the primary mail address is not"
                f" in list of configured mail domains: {r_user.email}.",
                "type": "UdmError:CreateError",
            }
        ]
    }


@pytest.mark.asyncio
async def test_fix_case_of_ous(create_multiple_ous, school_user):
    school1_ori, school2_ori = await create_multiple_ous(2)
    school1_scrambled = scramble_case(school1_ori)
    school2_scrambled = scramble_case(school2_ori)

    user = school_user(
        school=school1_scrambled,
        schools=[school1_scrambled, school2_scrambled],
        school_classes={
            school1_scrambled: [fake.unique.user_name(), fake.unique.user_name()],
            school2_scrambled: [fake.unique.user_name(), fake.unique.user_name()],
        },
        workgroups={
            school1_scrambled: [fake.unique.user_name(), fake.unique.user_name()],
            school2_scrambled: [fake.unique.user_name(), fake.unique.user_name()],
        },
    )
    await fix_case_of_ous(user)
    assert user.school == school1_ori
    assert set(user.schools) == {school1_ori, school2_ori}
    assert set(user.school_classes) == {school1_ori, school2_ori}
    assert set(user.workgroups) == {school1_ori, school2_ori}


@pytest.mark.asyncio
async def test_fqdn_is_case_insensitive(
    url_fragment_scrambled_hostname,
    retry_http_502,
    auth_header,
    create_ou_using_python,
    random_user_create_model,
):
    """The FQDN should not be case-sensitive

    Bug #54305
    """
    school = await create_ou_using_python()

    roles = ["student"]

    r_user = await random_user_create_model(
        school,
        roles=[f"{url_fragment_scrambled_hostname}/roles/{role_}" for role_ in roles],
    )
    response = retry_http_502(
        requests.post,
        f"{url_fragment_scrambled_hostname}/users/",
        headers={"Content-Type": "application/json", **auth_header},
        data=r_user.json(),
    )
    assert response.status_code == 201, response.reason
