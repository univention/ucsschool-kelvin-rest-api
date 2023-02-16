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

from typing import List

import pytest
import requests
from faker import Faker

import ucsschool.kelvin.constants
from ucsschool.kelvin.routers.workgroup import WorkGroupModel
from ucsschool.lib.models.base import NoObject
from ucsschool.lib.models.group import WorkGroup
from ucsschool.lib.models.share import WorkGroupShare
from ucsschool.lib.models.user import Student, User
from udm_rest_client import UDM

fake = Faker()
pytestmark = pytest.mark.skipif(
    not ucsschool.kelvin.constants.CN_ADMIN_PASSWORD_FILE.exists(),
    reason="Must run inside Docker container started by appcenter.",
)


def dn2username(dn: str) -> str:
    return dn.split(",")[0].split("=")[1]


def url2username(url: str) -> str:
    return url.rsplit("/", 1)[-1]


async def compare_lib_api_obj(lib_obj: WorkGroup, api_obj: WorkGroupModel, url_fragment):
    for attr, lib_value in lib_obj.to_dict().items():
        if attr == "$dn$":
            assert lib_value == api_obj.dn
        elif attr == "objectType":
            assert lib_value == "groups/group"
        elif attr == "school":
            assert f"{url_fragment}/schools/{lib_value}" == api_obj.unscheme_and_unquote(api_obj.school)
        elif attr == "users":
            lib_users = {dn2username(lu) for lu in lib_value}
            api_users = {url2username(url) for url in api_obj.users}
            assert lib_users == api_users
        elif attr == "ucsschool_roles":
            if lib_value:
                assert lib_value == api_obj.ucsschool_roles
            else:
                assert api_obj.ucsschool_roles == [f"workgroup:school:{lib_obj.school}"]
        else:
            assert lib_value == getattr(api_obj, attr)


def compare_ldap_json_obj(dn, json_resp, url_fragment):
    import univention.admin.uldap

    lo, pos = univention.admin.uldap.getAdminConnection()
    ldap_obj = lo.get(dn)

    for attr, value in json_resp.items():
        if attr == "ucsschool_roles":
            assert set(value) == set(r.decode("utf-8") for r in ldap_obj["ucsschoolRole"])
        elif attr == "description" and "description" in ldap_obj:
            assert value == ldap_obj["description"][0].decode("utf-8")
        elif attr == "users":
            json_users = {url2username(url) for url in json_resp["users"]}
            if json_users:
                ldap_users = {name.decode("utf-8") for name in ldap_obj["memberUid"]}
                assert json_users == ldap_users
        elif attr == "dn":
            assert f"cn={ldap_obj['cn'][0].decode('utf-8')}" in value
        elif attr == "name":
            assert value in ldap_obj["cn"][0].decode("utf-8")
    if "univentionObjectType" in ldap_obj:
        assert ldap_obj["univentionObjectType"] == [b"groups/group"]


@pytest.mark.asyncio
async def test_search(
    auth_header,
    retry_http_502,
    url_fragment,
    udm_kwargs,
    new_workgroup_using_lib,
    create_ou_using_python,
):
    ou = await create_ou_using_python()
    sc1_dn, sc1_attr = await new_workgroup_using_lib(ou)
    sc2_dn, sc2_attr = await new_workgroup_using_lib(ou)
    async with UDM(**udm_kwargs) as udm:
        lib_workgroups: List[WorkGroup] = await WorkGroup.get_all(udm, ou)
    assert sc1_dn in [c.dn for c in lib_workgroups]
    assert sc2_dn in [c.dn for c in lib_workgroups]
    response = retry_http_502(
        requests.get,
        f"{url_fragment}/workgroups/",
        headers=auth_header,
        params={"school": ou},
    )
    json_resp = response.json()
    assert response.status_code == 200
    api_workgroups = {f"{ou}-{data['name']}": WorkGroupModel(**data) for data in json_resp}
    assert sc1_dn in [ac.dn for ac in api_workgroups.values()]
    assert sc2_dn in [ac.dn for ac in api_workgroups.values()]
    for lib_obj in lib_workgroups:
        api_obj = api_workgroups[lib_obj.name]
        await compare_lib_api_obj(lib_obj, api_obj, url_fragment)
        resp = [resp for resp in json_resp if resp["dn"] == api_obj.dn][0]
        compare_ldap_json_obj(api_obj.dn, resp, url_fragment)


@pytest.mark.asyncio
async def test_get(
    auth_header,
    retry_http_502,
    url_fragment,
    udm_kwargs,
    new_workgroup_using_lib,
    create_ou_using_python,
    mail_domain,
):
    ou = await create_ou_using_python()
    sc1_dn, sc1_attr = await new_workgroup_using_lib(ou)
    async with UDM(**udm_kwargs) as udm:
        lib_obj: WorkGroup = await WorkGroup.from_dn(sc1_dn, ou, udm)
        await lib_obj.modify(udm)
    assert sc1_dn == lib_obj.dn
    url = f"{url_fragment}/workgroups/{ou}/{sc1_attr['name']}"
    response = retry_http_502(requests.get, url, headers=auth_header)
    json_resp = response.json()
    assert response.status_code == 200
    assert all(
        attr in json_resp
        for attr in ("description", "dn", "name", "ucsschool_roles", "url", "users", "udm_properties")
    )
    api_obj = WorkGroupModel(**json_resp)
    await compare_lib_api_obj(lib_obj, api_obj, url_fragment)
    compare_ldap_json_obj(json_resp["dn"], json_resp, url_fragment)
    assert "gidNumber" in api_obj.udm_properties
    assert api_obj.udm_properties["gidNumber"]
    assert isinstance(api_obj.udm_properties["gidNumber"], int)


@pytest.mark.asyncio
async def test_create(
    auth_header,
    create_ou_using_python,
    retry_http_502,
    url_fragment,
    udm_kwargs,
    new_workgroup_using_lib_obj,
    mail_domain,
):
    school = await create_ou_using_python()
    lib_obj: WorkGroup = new_workgroup_using_lib_obj(school)
    name = lib_obj.name[len(lib_obj.school) + 1 :]  # noqa: E203
    attrs = {
        "name": name,
        "school": f"{url_fragment}/schools/{lib_obj.school}",
        "description": lib_obj.description,
        "users": lib_obj.users,
        "create_share": True,
    }
    async with UDM(**udm_kwargs) as udm:
        assert await lib_obj.exists(udm) is False
        response = retry_http_502(
            requests.post,
            f"{url_fragment}/workgroups/",
            headers={"Content-Type": "application/json", **auth_header},
            json=attrs,
        )
        json_resp = response.json()
        assert response.status_code == 201
        api_obj = WorkGroupModel(**json_resp)
        assert lib_obj.dn == api_obj.dn
        assert await WorkGroup(name=lib_obj.name, school=lib_obj.school).exists(udm) is True
        await compare_lib_api_obj(lib_obj, api_obj, url_fragment)
        compare_ldap_json_obj(json_resp["dn"], json_resp, url_fragment)
        assert await WorkGroupShare.from_school_group(lib_obj).exists(udm) is True
        await WorkGroup(name=lib_obj.name, school=lib_obj.school).remove(udm)
        assert await WorkGroup(name=lib_obj.name, school=lib_obj.school).exists(udm) is False


@pytest.mark.asyncio
async def test_create_unmapped_udm_prop(
    create_ou_using_python,
    new_workgroup_using_lib_obj,
    url_fragment,
    udm_kwargs,
    retry_http_502,
    auth_header,
):
    school = await create_ou_using_python()
    lib_obj: WorkGroup = new_workgroup_using_lib_obj(school)
    name = lib_obj.name[len(lib_obj.school) + 1 :]  # noqa: E203
    attrs = {
        "name": name,
        "school": f"{url_fragment}/schools/{lib_obj.school}",
        "description": lib_obj.description,
        "users": lib_obj.users,
        "udm_properties": {"unmapped_prop": "some value"},
    }
    async with UDM(**udm_kwargs) as udm:
        assert await lib_obj.exists(udm) is False
        response = retry_http_502(
            requests.post,
            f"{url_fragment}/workgroups/",
            headers={"Content-Type": "application/json", **auth_header},
            json=attrs,
        )
        assert response.status_code == 422, f"{response.__dict__!r}"


async def change_operation(
    auth_header,
    retry_http_502,
    url_fragment,
    udm_kwargs,
    new_workgroup_using_lib,
    new_school_users,
    mail_domain,
    operation: str,
    school: str,
):
    assert operation in ("patch", "put")
    users: List[User] = await new_school_users(
        school, {"student": 2, "teacher": 1, "teacher_and_staff": 1}
    )
    students = [user for user in users if isinstance(user, Student)]
    if not students:
        raise RuntimeError("No student in user data.")
    async with UDM(**udm_kwargs) as udm:
        first_student_dn = students[0].dn
        sc1_dn, sc1_attr = await new_workgroup_using_lib(school, users=[first_student_dn])
        # verify workgroup exists in LDAP
        lib_obj: WorkGroup = await WorkGroup.from_dn(sc1_dn, school, udm)
        assert lib_obj.description == sc1_attr["description"]
        assert lib_obj.users == [first_student_dn]
        # verify users exist in LDAP
        for user in users:
            assert await User(name=user.name, school=user.school).exists(udm) is True
        # execute PATCH/PUT
        change_data = {
            "description": fake.text(max_nb_chars=50),
            "users": [f"{url_fragment}/users/{user.name}" for user in users],
        }
        if operation == "put":
            change_data["name"] = sc1_attr["name"]
            change_data["school"] = f"{url_fragment}/schools/{school}"
        url = f"{url_fragment}/workgroups/{school}/{sc1_attr['name']}"
        requests_method = getattr(requests, operation)
        response = retry_http_502(
            requests_method,
            url,
            headers=auth_header,
            json=change_data,
        )
        json_resp = response.json()
        assert response.status_code == 200
        # check response
        api_obj = WorkGroupModel(**json_resp)
        assert api_obj.dn == sc1_dn
        assert api_obj.description == change_data["description"]
        assert {api_obj.unscheme_and_unquote(url) for url in api_obj.users} == set(change_data["users"])
        usernames_in_response = {url2username(url) for url in api_obj.users}
        # check LDAP content
        lib_obj: WorkGroup = await WorkGroup.from_dn(sc1_dn, school, udm)
        assert lib_obj.description == change_data["description"]
        usernames_in_ldap = {dn2username(dn) for dn in lib_obj.users}
        assert usernames_in_response == usernames_in_ldap


@pytest.mark.asyncio
async def test_put(
    auth_header,
    retry_http_502,
    url_fragment,
    udm_kwargs,
    new_workgroup_using_lib,
    create_ou_using_python,
    new_school_users,
    mail_domain,
):
    ou = await create_ou_using_python()
    await change_operation(
        auth_header,
        retry_http_502,
        url_fragment,
        udm_kwargs,
        new_workgroup_using_lib,
        new_school_users,
        mail_domain,
        operation="put",
        school=ou,
    )


@pytest.mark.parametrize("operation", ["put", "patch"])
@pytest.mark.asyncio
async def test_modify_unmapped_udm_prop(
    new_workgroup_using_lib,
    create_ou_using_python,
    url_fragment,
    retry_http_502,
    auth_header,
    operation,
):
    school = await create_ou_using_python()
    sc1_dn, sc1_attr = await new_workgroup_using_lib(school, users=[])
    change_data = {
        "description": fake.text(max_nb_chars=50),
        "users": [],
        "udm_properties": {"unmapped_prop": "some value"},
    }
    if operation == "put":
        change_data["name"] = sc1_attr["name"]
        change_data["school"] = f"{url_fragment}/schools/{school}"
    url = f"{url_fragment}/workgroups/{school}/{sc1_attr['name']}"
    requests_method = getattr(requests, operation)
    response = retry_http_502(
        requests_method,
        url,
        headers=auth_header,
        json=change_data,
    )
    assert response.status_code == 422, response.__dict__


@pytest.mark.asyncio
async def test_patch(
    auth_header,
    retry_http_502,
    url_fragment,
    udm_kwargs,
    new_workgroup_using_lib,
    create_ou_using_python,
    new_school_users,
    mail_domain,
):
    ou = await create_ou_using_python()
    await change_operation(
        auth_header,
        retry_http_502,
        url_fragment,
        udm_kwargs,
        new_workgroup_using_lib,
        new_school_users,
        mail_domain,
        operation="patch",
        school=ou,
    )


@pytest.mark.asyncio
async def test_delete(
    auth_header,
    create_ou_using_python,
    retry_http_502,
    url_fragment,
    udm_kwargs,
    new_workgroup_using_lib,
):
    ou = await create_ou_using_python()
    sc1_dn, sc1_attr = await new_workgroup_using_lib(ou)
    async with UDM(**udm_kwargs) as udm:
        lib_obj: WorkGroup = await WorkGroup.from_dn(sc1_dn, ou, udm)
        assert await lib_obj.exists(udm) is True
    assert sc1_dn == lib_obj.dn
    url = f"{url_fragment}/workgroups/{ou}/{sc1_attr['name']}"
    response = retry_http_502(
        requests.delete,
        url,
        headers=auth_header,
    )
    assert response.status_code == 204
    async with UDM(**udm_kwargs) as udm:
        with pytest.raises(NoObject):
            await WorkGroup.from_dn(sc1_dn, ou, udm)


@pytest.mark.asyncio
@pytest.mark.parametrize("operation", ["patch", "put"])
async def test_workgroup_name_can_change(
    auth_header, retry_http_502, url_fragment, new_workgroup_using_lib, create_ou_using_python, operation
):
    school = await create_ou_using_python()
    _, sc1_attr = await new_workgroup_using_lib(school, users=[])
    change_data = {
        "name": fake.unique.user_name(),
    }
    if operation == "put":
        change_data["school"] = f"{url_fragment}/schools/{school}"
    url = f"{url_fragment}/workgroups/{school}/{sc1_attr['name']}"
    requests_method = getattr(requests, operation)
    response = retry_http_502(
        requests_method,
        url,
        headers=auth_header,
        json=change_data,
    )
    assert response.status_code == 200, response.__dict__


@pytest.mark.asyncio
@pytest.mark.parametrize("operation", ["patch", "put"])
async def test_workgroup_school_cant_change(
    auth_header, retry_http_502, url_fragment, new_workgroup_using_lib, create_ou_using_python, operation
):
    school = await create_ou_using_python()
    school2 = await create_ou_using_python()
    _, sc1_attr = await new_workgroup_using_lib(school, users=[])
    change_data = {
        "school": f"{url_fragment}/schools/{school2}",
    }
    if operation == "put":
        change_data["name"] = sc1_attr["name"]
    url = f"{url_fragment}/workgroups/{school}/{sc1_attr['name']}"
    requests_method = getattr(requests, operation)
    response = retry_http_502(
        requests_method,
        url,
        headers=auth_header,
        json=change_data,
    )
    assert response.status_code == 422, response.__dict__


@pytest.mark.asyncio
async def test_workgroup_does_not_create_share_if_disabled(
    auth_header,
    create_ou_using_python,
    retry_http_502,
    url_fragment,
    udm_kwargs,
    new_workgroup_using_lib_obj,
):
    school = await create_ou_using_python()
    lib_obj: WorkGroup = new_workgroup_using_lib_obj(school)
    name = lib_obj.name[len(lib_obj.school) + 1 :]  # noqa: E203
    attrs = {
        "name": name,
        "school": f"{url_fragment}/schools/{lib_obj.school}",
        "description": lib_obj.description,
        "users": lib_obj.users,
        "create_share": False,
    }
    async with UDM(**udm_kwargs) as udm:
        assert await lib_obj.exists(udm) is False
        retry_http_502(
            requests.post,
            f"{url_fragment}/workgroups/",
            headers={"Content-Type": "application/json", **auth_header},
            json=attrs,
        )
        assert await WorkGroupShare.from_school_group(lib_obj).exists(udm) is False


@pytest.mark.parametrize("operation", ["put", "patch"])
@pytest.mark.asyncio
async def test_modify_udm_error_forwarding(
    new_workgroup_using_lib,
    create_ou_using_python,
    url_fragment,
    retry_http_502,
    auth_header,
    operation,
):
    school = await create_ou_using_python()
    sc1_dn, sc1_attr = await new_workgroup_using_lib(school, users=[])
    change_data = {
        "description": fake.text(max_nb_chars=50),
        "users": [],
        "udm_properties": {"gidNumber": "some value"},
    }
    if operation == "put":
        change_data["name"] = sc1_attr["name"]
        change_data["school"] = f"{url_fragment}/schools/{school}"
    url = f"{url_fragment}/workgroups/{school}/{sc1_attr['name']}"
    requests_method = getattr(requests, operation)
    response = retry_http_502(
        requests_method,
        url,
        headers=auth_header,
        json=change_data,
    )
    assert response.status_code == 422, response.__dict__
    assert response.json() == {
        "detail": [
            {
                "loc": ["gidNumber"],
                "msg": "The property gidNumber has an invalid value:"
                " Value must be of type integer not str.",
                "type": "UdmError:ModifyError",
            }
        ]
    }


@pytest.mark.asyncio
async def test_create_udm_error_forwarding(
    auth_header,
    create_ou_using_python,
    retry_http_502,
    url_fragment,
    udm_kwargs,
    new_workgroup_using_lib_obj,
    mail_domain,
):
    school = await create_ou_using_python()
    lib_obj: WorkGroup = new_workgroup_using_lib_obj(school)
    name = lib_obj.name[len(lib_obj.school) + 1 :]  # noqa: E203
    attrs = {
        "name": name,
        "school": f"{url_fragment}/schools/{lib_obj.school}",
        "description": lib_obj.description,
        "users": lib_obj.users,
        "create_share": True,
        "udm_properties": {"gidNumber": "some value"},
    }
    async with UDM(**udm_kwargs) as udm:
        assert await lib_obj.exists(udm) is False
        response = retry_http_502(
            requests.post,
            f"{url_fragment}/workgroups/",
            headers={"Content-Type": "application/json", **auth_header},
            json=attrs,
        )
        json_resp = response.json()
        assert response.status_code == 422
        assert json_resp == {
            "detail": [
                {
                    "loc": ["gidNumber"],
                    "msg": "The property gidNumber has an invalid value:"
                    " Value must be of type integer not str.",
                    "type": "UdmError:CreateError",
                }
            ]
        }
