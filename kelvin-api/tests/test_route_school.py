# Copyright 2021 Univention GmbH
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

from typing import Dict, Iterable, Set, Tuple

import pytest
from fastapi.testclient import TestClient
from ldap.dn import explode_dn

import ucsschool.kelvin.constants
from ucsschool.kelvin.ldap import uldap_machine_read
from ucsschool.kelvin.main import app
from ucsschool.kelvin.routers.school import SchoolCreateModel, SchoolModel
from ucsschool.lib.models.school import School
from udm_rest_client import UDM

pytestmark = pytest.mark.skipif(
    not ucsschool.kelvin.constants.CN_ADMIN_PASSWORD_FILE.exists(),
    reason="Must run inside Docker container started by appcenter.",
)


async def compare_lib_api_obj(lib_obj: School, api_obj: SchoolModel):
    for attr, lib_value in lib_obj.to_dict().items():
        if attr == "$dn$":
            assert lib_value == api_obj.dn
        elif attr == "objectType":
            assert lib_value == "container/ou"
        elif attr in ("class_share_file_server", "home_share_file_server"):
            if lib_value:
                hostname = explode_dn(lib_value, True)[0]
                assert hostname == getattr(api_obj, attr)
            else:
                assert getattr(api_obj, attr) is None
        elif attr in ("administrative_servers", "educational_servers"):
            assert {explode_dn(lv, True)[0] for lv in lib_value} == set(getattr(api_obj, attr))
        elif attr in ("dc_name", "dc_name_administrative"):
            continue
        elif attr == "ucsschool_roles":
            assert lib_value == api_obj.ucsschool_roles
            assert api_obj.ucsschool_roles == [f"school:school:{lib_obj.name}"]
        else:
            assert lib_value == getattr(api_obj, attr)


@pytest.mark.asyncio
async def test_search_no_filter(auth_header, udm_kwargs):
    uldap = uldap_machine_read()
    ldap_ous: Set[Tuple[str, str]] = {
        (ldap_result["ou"].value, ldap_result.entry_dn)
        for ldap_result in uldap.search("(objectClass=ucsschoolOrganizationalUnit)", attributes=["ou"])
    }
    async with UDM(**udm_kwargs) as udm:
        lib_schools: Iterable[School] = await School.get_all(udm)
    assert {s.name for s in lib_schools} == {ou[0] for ou in ldap_ous}

    client = TestClient(app, base_url="http://test.server")
    response = client.get(app.url_path_for("school_search"), headers=auth_header)
    json_resp = response.json()
    assert response.status_code == 200
    api_schools: Dict[str, SchoolModel] = {data["name"]: SchoolModel(**data) for data in json_resp}
    assert {ou[1] for ou in ldap_ous} == {aps.dn for aps in api_schools.values()}
    for lib_obj in lib_schools:
        api_obj = api_schools[lib_obj.name]
        await compare_lib_api_obj(lib_obj, api_obj)
        assert (
            api_obj.unscheme_and_unquote(api_obj.url)
            == f"{client.base_url}{app.url_path_for('school_get', school_name=lib_obj.name)}"
        )


@pytest.mark.asyncio
async def test_search_with_filter(auth_header, create_ou_using_python, random_ou_name, udm_kwargs):
    common_name = random_ou_name()[:8]
    await create_ou_using_python(ou_name=f"{common_name}abc12")
    await create_ou_using_python(ou_name=f"{common_name}34xyz")
    uldap = uldap_machine_read()
    ldap_ous: Set[Tuple[str, str]] = {
        (ldap_result["ou"].value, ldap_result.entry_dn)
        for ldap_result in uldap.search(
            f"(&(objectClass=ucsschoolOrganizationalUnit)(ou={common_name}*))", attributes=["ou"]
        )
    }
    async with UDM(**udm_kwargs) as udm:
        lib_schools: Iterable[School] = await School.get_all(udm, filter_str=f"ou={common_name}*")
    assert {s.name for s in lib_schools} == {ou[0] for ou in ldap_ous}

    client = TestClient(app, base_url="http://test.server")
    response = client.get(
        app.url_path_for("school_search"),
        headers=auth_header,
        params={"name": f"{common_name}*"},
        timeout=120,
    )
    json_resp = response.json()
    assert response.status_code == 200
    api_schools: Dict[str, SchoolModel] = {data["name"]: SchoolModel(**data) for data in json_resp}
    assert {ou[1] for ou in ldap_ous} == {aps.dn for aps in api_schools.values()}
    for lib_obj in lib_schools:
        api_obj = api_schools[lib_obj.name]
        await compare_lib_api_obj(lib_obj, api_obj)
        assert (
            api_obj.unscheme_and_unquote(api_obj.url)
            == f"{client.base_url}{app.url_path_for('school_get', school_name=lib_obj.name)}"
        )


@pytest.mark.asyncio
async def test_get(auth_header, create_ou_using_python, ldap_base, udm_kwargs):
    ou_name = await create_ou_using_python()
    async with UDM(**udm_kwargs) as udm:
        lib_obj = await School.from_dn(f"ou={ou_name},{ldap_base}", ou_name, udm)
        lib_obj.udm_properties["description"] = f"{ou_name}-description"
        await lib_obj.modify(udm)
    client = TestClient(app, base_url="http://test.server")
    response = client.get(app.url_path_for("school_get", school_name=ou_name), headers=auth_header)
    json_resp = response.json()
    assert response.status_code == 200
    api_obj = SchoolModel(**json_resp)
    assert api_obj.udm_properties["description"] == f"{ou_name}-description"
    await compare_lib_api_obj(lib_obj, api_obj)
    assert (
        api_obj.unscheme_and_unquote(api_obj.url)
        == f"{client.base_url}{app.url_path_for('school_get', school_name=lib_obj.name)}"
    )


@pytest.mark.parametrize("exists", [True, False])
@pytest.mark.asyncio
async def test_head(auth_header, create_ou_using_python, ldap_base, udm_kwargs, exists, random_ou_name):
    ou_name = random_ou_name()
    if exists:
        await create_ou_using_python(ou_name=ou_name, cache=False)
    client = TestClient(app, base_url="http://test.server")
    response = client.head(app.url_path_for("school_exists", school_name=ou_name), headers=auth_header)
    if exists:
        assert response.status_code == 200
        assert not response.text
    else:
        assert response.status_code == 404


@pytest.mark.asyncio
async def test_create(
    auth_header,
    udm_kwargs,
    docker_host_name,
    ldap_base,
    random_school_create_model,
    schedule_delete_ou_using_ssh,
):
    school_create_model: SchoolCreateModel = random_school_create_model()
    attrs = school_create_model.dict()
    attrs["udm_properties"] = {"description": "DESCRIPTION"}
    schedule_delete_ou_using_ssh(school_create_model.name, docker_host_name)
    client = TestClient(app, base_url="http://test.server")
    response = client.post(
        app.url_path_for("school_create"),
        headers={"Content-Type": "application/json", **auth_header},
        json=attrs,
    )
    json_resp = response.json()
    assert response.status_code == 201
    api_obj = SchoolModel(**json_resp)
    async with UDM(**udm_kwargs) as udm:
        lib_obj = await School.from_dn(
            f"ou={school_create_model.name},{ldap_base}", school_create_model.name, udm
        )
        udm_obj = await udm.obj_by_dn(lib_obj.dn)
    assert api_obj.udm_properties["description"] == "DESCRIPTION"
    assert udm_obj.props["description"] == "DESCRIPTION"
    assert lib_obj.dn == api_obj.dn
    await compare_lib_api_obj(lib_obj, api_obj)
    assert (
        api_obj.unscheme_and_unquote(api_obj.url)
        == f"{client.base_url}{app.url_path_for('school_get', school_name=lib_obj.name)}"
    )


@pytest.mark.asyncio
async def test_create_unmapped_udm_prop(
    random_school_create_model,
    schedule_delete_ou_using_ssh,
    docker_host_name,
    auth_header,
):
    school_create_model: SchoolCreateModel = random_school_create_model()
    attrs = school_create_model.dict()
    attrs["udm_properties"] = {"unmapped_prop": "some value"}
    schedule_delete_ou_using_ssh(school_create_model.name, docker_host_name)
    client = TestClient(app, base_url="http://test.server")
    response = client.post(
        app.url_path_for("school_create"),
        headers={"Content-Type": "application/json", **auth_header},
        json=attrs,
    )
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_create_udm_error_forwarding(
    auth_header,
    docker_host_name,
    random_school_create_model,
    schedule_delete_ou_using_ssh,
):
    school_create_model: SchoolCreateModel = random_school_create_model()
    attrs = school_create_model.dict()
    attrs["udm_properties"] = {"description": "DESCRIPTION", "userPath": "_xxx"}
    schedule_delete_ou_using_ssh(school_create_model.name, docker_host_name)
    client = TestClient(app, base_url="http://test.server")
    response = client.post(
        app.url_path_for("school_create"),
        headers={"Content-Type": "application/json", **auth_header},
        json=attrs,
    )
    assert response.status_code == 422, response.json()
    assert response.json() == {
        "detail": [
            {
                "loc": ["userPath"],
                "msg": "The property userPath has an invalid value:"
                " Value must be of type boolean not str.",
                # raises a ModifyError as school_create creates the school ou and modifies it afterwards
                "type": "UdmError:ModifyError",
            }
        ]
    }


@pytest.mark.asyncio
@pytest.mark.parametrize("language", [None, "de", "en", "de-DE", "en-US;q=0.95"])
async def test_get_school_language(auth_header, monkeypatch, language):
    async def from_lib_model_mock(obj, request, udm) -> SchoolModel:
        kwargs = await SchoolModel._from_lib_model_kwargs(obj, request, udm)
        kwargs["display_name"] = udm.session.language
        return SchoolModel(**kwargs)

    monkeypatch.setattr(
        ucsschool.kelvin.routers.school.SchoolModel, "from_lib_model", from_lib_model_mock
    )

    client = TestClient(app, base_url="http://test.server")
    if language is not None:
        headers = {"Accept-Language": language, **auth_header}
    else:
        headers = {**auth_header}
    response = client.get(
        app.url_path_for("school_get", school_name="DEMOSCHOOL"),
        headers=headers,
    ).json()

    assert response["display_name"] == language
