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

import datetime
import inspect
import logging
import random
from pathlib import Path
from typing import Any, Dict, List, NamedTuple, Type, Union

import pytest
import requests
from faker import Faker

import ucsschool.kelvin.constants
import univention.admin.uldap_docker
from ucsschool.importer.models.import_user import ImportUser
from ucsschool.importer.utils.format_pyhook import FormatPyHook
from ucsschool.importer.utils.user_pyhook import KelvinUserHook, UserPyHook
from ucsschool.kelvin.routers.user import LegalGuardianModel, StudentModel, UserModel, UserModelsUnion
from ucsschool.lib.models.hook import Hook
from ucsschool.lib.models.user import (
    LegalGuardian,
    SchoolAdmin,
    Staff,
    Student,
    Teacher,
    TeachersAndStaff,
    User,
)
from ucsschool.lib.models.utils import env_or_ucr
from udm_rest_client import UDM

pytestmark = pytest.mark.skipif(
    not ucsschool.kelvin.constants.CN_ADMIN_PASSWORD_FILE.exists(),
    reason="Must run inside Docker container started by appcenter.",
)

UserType = Type[Union[Staff, Student, Teacher, TeachersAndStaff, User]]
Role = NamedTuple("Role", [("name", str), ("klass", UserType)])
USER_ROLES: List[Role] = [
    Role("staff", Staff),
    Role("student", Student),
    Role("teacher", Teacher),
    Role("legalGuardian", LegalGuardian),
    Role("teacher_and_staff", TeachersAndStaff),
    Role("school_admin", SchoolAdmin),
]  # User.role_string -> User
random.shuffle(USER_ROLES)
fake = Faker()
logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)


def get_user_model(response_json: Dict[str, Any]) -> UserModelsUnion:
    if response_json["user_type"] == "legal_guardian":
        return LegalGuardianModel(**response_json)
    if response_json["user_type"] == "student":
        return StudentModel(**response_json)
    return UserModel(**response_json)


"""
Hook classes used in tests
"""


class CamelCaseLastnameFormatPyHook(FormatPyHook):
    priority = {
        "patch_fields_student": 10,
        "patch_fields_teacher_and_staff": 10,
    }
    properties = ("record_uid",)

    def crazy_camel(self, property_name: str, fields: Dict[str, Any]) -> Dict[str, Any]:
        import random

        fields["lastname"] = "".join(
            [getattr(char, random.choice(("upper", "lower")))() for char in fields["lastname"]]  # nosec
        )
        return fields

    patch_fields_student = crazy_camel
    patch_fields_teacher_and_staff = crazy_camel


class UserBirthdayImportPyHook(UserPyHook):
    priority = {
        "pre_create": 10,
        "post_create": 10,
        "pre_modify": 10,
        "post_modify": 10,
        "pre_remove": 10,
        "post_remove": 10,
    }

    def __init__(
        self,
        lo: univention.admin.uldap_docker.access = None,
        dry_run: bool = None,
        udm: UDM = None,
        *args,
        **kwargs,
    ) -> None:
        assert isinstance(self, KelvinUserHook)
        super(UserBirthdayImportPyHook, self).__init__(lo=lo, dry_run=dry_run, udm=udm, *args, **kwargs)
        self.logger.info("   -> THIS IS A KelvinUserHook")

    async def test_lo(self) -> None:
        assert isinstance(self.lo, univention.admin.uldap_docker.access), type(self.lo)
        admin = self.lo.get(f"uid=Administrator,cn=users,{env_or_ucr('ldap/base')}")
        samba_sid = admin["sambaSID"][0]
        if isinstance(samba_sid, bytes):
            samba_sid: str = samba_sid.decode("utf-8")
        assert samba_sid.endswith("-500")

    async def test_udm(self) -> None:
        assert isinstance(self.udm, UDM), type(self.udm)
        assert self.udm.session._session
        assert not self.udm.session._session.closed
        assert await self.udm.session.base_dn == env_or_ucr("ldap/base")

    async def _hook_func(self, user: ImportUser, hook_phase: str) -> None:
        await self.test_lo()
        await self.test_udm()
        self.logger.info(f"{self.__class__.__name__}  -> {hook_phase}")
        Path("/tmp", f"{hook_phase}-{user.name}").touch()

    async def pre_create(self, user: ImportUser) -> None:
        user.record_uid = user.lastname
        await self._hook_func(user, "pre_create")

    async def post_create(self, user: ImportUser) -> None:
        await self._hook_func(user, "post_create")
        user.birthday = datetime.date.today().isoformat()
        await user.modify(self.udm)

    async def pre_modify(self, user: ImportUser) -> None:
        user.record_uid = user.lastname
        await self._hook_func(user, "pre_modify")

    async def post_modify(self, user: ImportUser) -> None:
        user.record_uid = user.lastname
        await self._hook_func(user, "post_modify")

    async def pre_remove(self, user: ImportUser) -> None:
        await self._hook_func(user, "pre_remove")

    async def post_remove(self, user: ImportUser) -> None:
        await self._hook_func(user, "post_remove")


class ExpirationDateUCSSchoolLibPyHook(Hook):
    priority = {
        "pre_create": 10,
        "post_create": 10,
        "pre_modify": 10,
        "post_modify": 10,
        "pre_remove": 10,
        "post_remove": 10,
    }
    # MODEL_NAME # will be replaced in fixture to write hook with Student, Teacher, Staff or SchoolAdmin

    def __init__(
        self,
        lo: univention.admin.uldap_docker.access = None,
        udm: UDM = None,
        *args,
        **kwargs,
    ) -> None:
        self.lo = lo  # we need this to make the test pass: why?
        super(ExpirationDateUCSSchoolLibPyHook, self).__init__(lo=lo, udm=udm, *args, **kwargs)

    async def test_lo(self) -> None:
        assert isinstance(self.lo, univention.admin.uldap_docker.access), type(self.lo)
        admin = self.lo.get(f"uid=Administrator,cn=users,{env_or_ucr('ldap/base')}")
        samba_sid = admin["sambaSID"][0]
        if isinstance(samba_sid, bytes):
            samba_sid: str = samba_sid.decode("utf-8")
        assert samba_sid.endswith("-500")

    async def test_udm(self) -> None:
        assert isinstance(self.udm, UDM), type(self.udm)
        assert self.udm.session._session
        assert not self.udm.session._session.closed
        assert await self.udm.session.base_dn == env_or_ucr("ldap/base")

    async def _hook_func(self, user: User, hook_phase: str) -> None:
        await self.test_lo()
        await self.test_udm()
        self.logger.info(f"{self.__class__.__name__}  -> {hook_phase}")
        Path("/tmp", f"{hook_phase}-{user.name}").touch()

    async def pre_create(self, user: User) -> None:
        await self._hook_func(user, "pre_create")

    async def post_create(self, user: User) -> None:
        await self._hook_func(user, "post_create")
        user.expiration_date = (datetime.date.today() + datetime.timedelta(days=1)).isoformat()
        await user.modify(self.udm)

    async def pre_modify(self, user: User) -> None:
        user.disabled = True
        await self._hook_func(user, "pre_modify")

    async def post_modify(self, user: User) -> None:
        await self._hook_func(user, "post_modify")

    async def pre_remove(self, user: User) -> None:
        await self._hook_func(user, "pre_remove")

    async def post_remove(self, user: User) -> None:
        await self._hook_func(user, "post_remove")


@pytest.fixture(scope="module")
def _create_pyhook_file(restart_kelvin_api_server_module):
    """
    creates a hook file the specified path and cleans up
    after running the tests.
    """
    _hook_path = ""
    cache_path = ""
    module_names = []

    def _func(name: str, text: str, hook_path: Path):
        nonlocal _hook_path
        nonlocal cache_path
        _hook_path = hook_path
        cache_path = hook_path / "__pycache__"
        module_names.append(name)
        with open(_hook_path / f"{name}.py", "w") as fp:
            fp.write(text)
        logger.debug(f"****** {hook_path} ******")
        logger.debug(text)
        logger.debug("***********************************************")
        restart_kelvin_api_server_module()

    yield _func

    for name in module_names:
        hook_path = _hook_path / f"{name}.py"
        try:
            hook_path.unlink()
        except FileNotFoundError:
            pass
        for cache_file in cache_path.glob(f"{name}.*"):
            cache_file.unlink()
    restart_kelvin_api_server_module()


@pytest.fixture(scope="module")
def create_ucsschool_lib_pyhook(_create_pyhook_file):
    def func(role: Role) -> str:
        text = f"""
import datetime
import inspect
import univention.admin.uldap_docker
from pathlib import Path
from udm_rest_client import UDM
from ucsschool.lib.models.hook import Hook
from ucsschool.lib.models.user import Student, Teacher, Staff, SchoolAdmin, User
from ucsschool.lib.models.utils import env_or_ucr

{inspect.getsource(ExpirationDateUCSSchoolLibPyHook)}
            """
        module_name = "Teacher" if role.klass.__name__ == "TeachersAndStaff" else role.klass.__name__
        text = text.replace("# MODEL_NAME", f"model = {module_name}")
        _create_pyhook_file(
            name="ucsschool-lib-testhook",
            text=text,
            hook_path=Path(ucsschool.lib.models.base.PYHOOKS_PATH),
        )

    yield func


@pytest.fixture(scope="module")
def create_format_pyhook(_create_pyhook_file):
    text = f"""from typing import Any, Dict
from ucsschool.importer.utils.format_pyhook import FormatPyHook

{inspect.getsource(CamelCaseLastnameFormatPyHook)}
"""
    _create_pyhook_file(
        name="formattesthook",
        text=text,
        hook_path=ucsschool.kelvin.constants.KELVIN_IMPORTUSER_HOOKS_PATH,
    )


@pytest.fixture(scope="module")
def create_user_import_pyhook(_create_pyhook_file):
    text = f"""
import inspect
import datetime
from pathlib import Path

from udm_rest_client import UDM
import univention.admin.uldap_docker
from ucsschool.importer.models.import_user import ImportUser
from ucsschool.importer.utils.user_pyhook import UserPyHook, KelvinUserHook
from ucsschool.lib.models.utils import env_or_ucr

{inspect.getsource(UserBirthdayImportPyHook)}
"""
    _create_pyhook_file(
        name="importusertesthook",
        text=text,
        hook_path=ucsschool.kelvin.constants.KELVIN_IMPORTUSER_HOOKS_PATH,
    )


def role_id(value: Role) -> str:
    return value.name


def check_all_hooks_called_and_clean_up(user: User | ImportUser) -> None:
    hook_phases = [
        "pre_create",
        "post_create",
        "pre_modify",
        "post_modify",
        "pre_remove",
        "post_remove",
    ]
    hook_file_paths = [Path("/tmp", f"{hook_phase}-{user.name}") for hook_phase in hook_phases]
    hooks_called = [hook_file.exists() for hook_file in hook_file_paths]
    for _path in hook_file_paths:
        try:
            Path("/tmp", _path).unlink()
        except FileNotFoundError:
            pass
    assert all(hooks_called), f"Not all hooks were called: {dict(zip(hook_phases, hooks_called))}"


@pytest.mark.asyncio
@pytest.mark.parametrize("role", USER_ROLES, ids=role_id)
async def test_format_pyhook(
    auth_header,
    retry_http_502,
    url_fragment,
    udm_kwargs,
    create_ou_using_python,
    random_user_create_model,
    schedule_delete_user_name_using_udm,
    create_format_pyhook,
    role: Role,
):
    roles = ["staff", "teacher"] if role.name == "teacher_and_staff" else [role.name]
    ou = await create_ou_using_python()
    lastname = (
        f"{fake.unique.last_name()}-{fake.unique.last_name()}"  # extra long name for reduced flakiness
    )
    r_user = await random_user_create_model(
        ou,
        roles=[f"{url_fragment}/roles/{role_}" for role_ in roles],
        lastname=lastname,
    )
    data = r_user.json(exclude={"record_uid"})
    logger.debug("POST data=%r", data)
    async with UDM(**udm_kwargs) as udm:
        lib_users = await User.get_all(udm, ou, f"username={r_user.name}")
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
    api_user = get_user_model(response_json)
    if role.name in ("school_admin", "legal_guardian", "staff", "teacher"):
        assert api_user.record_uid == api_user.lastname
    else:
        assert api_user.record_uid != api_user.lastname
        assert api_user.record_uid.lower() == api_user.lastname.lower()


@pytest.mark.asyncio
@pytest.mark.parametrize("role", USER_ROLES, ids=role_id)
async def test_user_import_pyhook(
    auth_header,
    retry_http_502,
    url_fragment,
    udm_kwargs,
    create_ou_using_python,
    random_user_create_model,
    schedule_delete_user_name_using_udm,
    create_user_import_pyhook,
    schedule_delete_file,
    role: Role,
):
    roles = ["staff", "teacher"] if role.name == "teacher_and_staff" else [role.name]
    ou = await create_ou_using_python()
    r_user = await random_user_create_model(
        ou, roles=[f"{url_fragment}/roles/{role_}" for role_ in roles]
    )
    schedule_delete_file(Path("/tmp", r_user.name))
    data = r_user.json()
    logger.debug("POST data=%r", data)
    async with UDM(**udm_kwargs) as udm:
        lib_users = await User.get_all(udm, ou, f"username={r_user.name}")
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
    api_user = get_user_model(response_json)
    assert api_user.birthday == datetime.date.today()

    response = retry_http_502(
        requests.patch,
        f"{url_fragment}/users/{r_user.name}",
        headers=auth_header,
        json={"birthday": "2013-12-11"},
    )
    assert response.status_code == 200, response.reason
    api_user = get_user_model(response.json())
    assert api_user.record_uid == api_user.lastname

    response = retry_http_502(
        requests.delete,
        f"{url_fragment}/users/{r_user.name}",
        headers=auth_header,
    )
    assert response.status_code == 204, response.reason
    async with UDM(**udm_kwargs) as udm:
        lib_users = await User.get_all(udm, ou, f"username={r_user.name}")
    assert len(lib_users) == 0
    check_all_hooks_called_and_clean_up(r_user)


@pytest.mark.asyncio
@pytest.mark.parametrize("role", USER_ROLES, ids=role_id)
async def test_user_ucsschool_lib_pyhook(
    auth_header,
    retry_http_502,
    url_fragment,
    create_ou_using_python,
    random_user_create_model,
    schedule_delete_user_name_using_udm,
    create_ucsschool_lib_pyhook,
    schedule_delete_file,
    role: Role,
):
    create_ucsschool_lib_pyhook(role)
    roles = ["staff", "teacher"] if role.name == "teacher_and_staff" else [role.name]
    ou = await create_ou_using_python()
    r_user = await random_user_create_model(
        ou, roles=[f"{url_fragment}/roles/{role_}" for role_ in roles]
    )
    schedule_delete_file(Path("/tmp", r_user.name))
    data = r_user.json()
    logger.debug("POST data=%r", data)
    schedule_delete_user_name_using_udm(r_user.name)
    response = retry_http_502(
        requests.post,
        f"{url_fragment}/users/",
        headers={"Content-Type": "application/json", **auth_header},
        data=data,
    )
    assert response.status_code == 201, f"{response.reason}: {response.__dict__!r}"
    response_json = response.json()
    api_user = User(**response_json)
    assert api_user.expiration_date == (datetime.date.today() + datetime.timedelta(days=1)).isoformat()
    response = retry_http_502(
        requests.patch,
        f"{url_fragment}/users/{r_user.name}",
        headers=auth_header,
        json={"birthday": "2013-12-11"},
    )
    assert response.status_code == 200, response.reason
    api_user = User(**response.json())
    assert api_user.disabled is True
    response = retry_http_502(
        requests.delete,
        f"{url_fragment}/users/{r_user.name}",
        headers=auth_header,
    )
    assert response.status_code == 204, response.reason
    check_all_hooks_called_and_clean_up(r_user)
