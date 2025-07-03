import asyncio
import datetime
import logging
import random
import tempfile
import time
from pathlib import Path
from typing import Any, Dict, List, Set, Tuple

import factory
import pytest
import pytest_asyncio
from faker import Faker

import ucsschool.lib.models.user
from ucsschool.lib.create_ou import create_ou
from ucsschool.lib.models.school import School
from ucsschool.lib.models.user import User
from ucsschool.lib.models.utils import (
    env_or_ucr,
    exec_cmd,
    get_file_handler,
    ucr,
    uldap_admin_read_local,
    uldap_admin_read_primary,
    uldap_conf,
)
from ucsschool.lib.roles import (
    create_ucsschool_role_string,
    role_school_admin,
    role_school_class,
    role_school_class_share,
    role_staff,
    role_teacher,
    role_workgroup,
    role_workgroup_share,
)
from ucsschool.lib.schoolldap import SchoolSearchBase
from udm_rest_client import UDM, NoObject as UdmNoObject

APP_ID = "ucsschool-kelvin-rest-api"
APP_BASE_PATH = Path("/var/lib/univention-appcenter/apps", APP_ID)
APP_CONFIG_BASE_PATH = APP_BASE_PATH / "conf"
CN_ADMIN_PASSWORD_FILE = APP_CONFIG_BASE_PATH / "cn_admin.secret"

_cached_ous: Set[Tuple[str, str]] = set()
fake = Faker()
logger = logging.getLogger("ucsschool")
logger.setLevel(logging.DEBUG)
logger = logging.getLogger("udm_rest_client")
logger.setLevel(logging.DEBUG)
logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)


@pytest.fixture(scope="session")
def event_loop(request):
    """Create an instance of the default event loop for each test case."""
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()


@pytest.fixture(scope="session")
def docker_host_name():
    return env_or_ucr("docker_host_name")


@pytest.fixture(scope="session")
def ldap_base():
    return env_or_ucr("ldap/base")


@pytest.fixture
def random_ou_name():
    def _func() -> str:
        return f"testou{fake.unique.pyint(1000, 9999)}"

    return _func


@pytest.fixture(scope="session")
def random_user_name():
    return fake.unique.user_name


@pytest.fixture(scope="session")
def random_first_name():
    return fake.unique.first_name


@pytest.fixture(scope="session")
def random_last_name():
    return fake.unique.last_name


@pytest.fixture(scope="session")
def udm_kwargs() -> Dict[str, Any]:
    with open(CN_ADMIN_PASSWORD_FILE, "r") as fp:
        cn_admin_password = fp.read().strip()
    host = env_or_ucr("ldap/server/name")
    return {
        "username": "cn=admin",
        "password": cn_admin_password,
        "url": f"https://{host}/univention/udm/",
    }


@pytest.fixture
def school_class_attrs(ldap_base):
    def _func(school: str, **kwargs) -> Dict[str, Any]:
        return {
            "name": kwargs.get("name", f"test.{fake.unique.user_name()}"),
            "school": school,
            "description": kwargs.get("description", fake.text(max_nb_chars=50)),
            "users": kwargs.get(
                "users",
                [
                    f"uid={fake.unique.user_name()},cn=users,{ldap_base}",
                    f"uid={fake.unique.user_name()},cn=users,{ldap_base}",
                ],
            ),
            "ucsschool_roles": kwargs.get(
                "ucsschool_roles",
                [create_ucsschool_role_string(role_school_class, school)],
            ),
            "create_share": True,
        }

    return _func


@pytest.fixture
def workgroup_attrs(ldap_base, school_class_attrs):
    def _func(school: str, **kwargs) -> Dict[str, Any]:
        ucsschool_roles = kwargs.get(
            "ucsschool_roles",
            [create_ucsschool_role_string(role_workgroup, school)],
        )
        res = school_class_attrs(school, ucsschool_roles=ucsschool_roles, **kwargs)
        res.update(
            {
                "email": None,
                "allowed_email_senders_users": [],
                "allowed_email_senders_groups": [],
            }
        )
        return res

    return _func


class UserFactory(factory.Factory):
    """
    Not yet created lib User object (missing specific roles), you probably want to use
    new_school_user() or new_udm_user().
    """

    class Meta:
        model = ucsschool.lib.models.user.User

    firstname = factory.Faker("first_name")
    lastname = factory.Faker("last_name")
    name = factory.LazyAttribute(
        lambda o: f"test.{o.firstname[:8]}{fake.pyint(10, 99)}.{o.lastname}"[:15].rstrip(".")
    )
    school = factory.LazyFunction(lambda: fake.unique.user_name()[:10])
    schools = factory.LazyAttribute(lambda o: [o.school])
    birthday = factory.LazyFunction(
        lambda: fake.unique.date_of_birth(minimum_age=6, maximum_age=18).strftime("%Y-%m-%d")
    )
    expiration_date = factory.LazyFunction(
        lambda: fake.unique.date_between(start_date="+1y", end_date="+10y").strftime("%Y-%m-%d")
    )
    email = None
    password = factory.Faker("password", length=20)
    disabled = False
    school_classes = factory.Dict({})
    workgroups = factory.Dict({})


@pytest_asyncio.fixture(scope="session")
async def mail_domain(udm_kwargs, wait_for_replication) -> str:
    async with UDM(**udm_kwargs) as udm:
        mod = udm.get("mail/domain")
        async for obj in mod.search():
            created_domain = ""
            name = obj.props.name
            logger.debug("Using existing mail/domain %r.", name)
            break
        else:
            name = env_or_ucr("domainname") or fake.domain_name()
            logger.debug("Creating mail/domain object %r...", name)
            obj = await mod.new()
            obj.props.name = name
            await obj.save()
            wait_for_replication(obj.dn)
            created_domain = name

    yield name

    if created_domain:
        logger.debug("Deleting mail/domain object %r...", created_domain)
        async with UDM(**udm_kwargs) as udm:
            mod = udm.get("mail/domain")
            async for obj in mod.search(f"(cn={created_domain})"):
                await obj.delete()


@pytest.fixture
def school_user(mail_domain):
    """
    Not yet created lib User object (missing specific roles), you probably want to use
    new_school_user() or new_udm_user(). -> User
    """

    def _func(school: str, **kwargs) -> ucsschool.lib.models.user.User:
        if "email" not in kwargs:
            local_part = fake.unique.ascii_company_email().split("@", 1)[0]
            kwargs["email"] = f"{local_part}@{mail_domain}"
        if "schools" not in kwargs:
            kwargs["schools"] = [school]
        return UserFactory.build(school=school, **kwargs)

    return _func


@pytest.fixture
def udm_users_user_props(school_user, ldap_base):
    """
    Attributes for an UDM user that is _almost_ a school user. -> {attrs}

    Missing ucsschoolRole, role groups, role options/OCs[, ucsschoolRecordUID, ucsschoolSourceUID].
    """

    async def _func(school: str, **school_user_kwargs) -> Dict[str, Any]:
        user = school_user(school, **school_user_kwargs)
        school = sorted(user.schools)[0]
        groups = [f"cn=Domain Users {ou},cn=groups,ou={ou},{ldap_base}" for ou in user.schools]
        for school_name in school_user_kwargs.get("workgroups", {}).keys():
            groups.extend(
                [
                    f"cn={school_name}-{wg['name']},cn=schueler,cn=groups,ou={school_name},{ldap_base}"
                    for wg in school_user_kwargs["workgroups"][school_name]
                ]
            )
        for school_name in school_user_kwargs.get("school_classes", {}).keys():
            groups.extend(
                [
                    (
                        f"cn={school_name}-{sc['name']},cn=klassen,cn=schueler,"
                        f"cn=groups,ou={school_name},{ldap_base}"
                    )
                    for sc in school_user_kwargs["school_classes"][school_name]
                ]
            )
        return {
            "firstname": user.firstname,
            "lastname": user.lastname,
            "username": user.name,
            "school": user.schools,
            "birthday": user.birthday,
            "userexpiry": user.expiration_date,
            "mailPrimaryAddress": user.email,
            "e-mail": [user.email],
            "description": fake.text(max_nb_chars=50),
            "password": user.password,
            "disabled": user.disabled,
            "primaryGroup": f"cn=Domain Users {school},cn=groups,ou={school},{ldap_base}",
            "groups": groups,
        }

    return _func


@pytest_asyncio.fixture
async def new_school_class_using_udm(udm_kwargs, ldap_base, school_class_attrs, wait_for_replication):
    """Create a new school class. -> (DN, {attrs})"""
    created_school_classes = []
    created_school_shares = []

    async def _func(school: str, **kwargs) -> Tuple[str, Dict[str, str]]:
        async with UDM(**udm_kwargs) as udm:
            sc_attrs = school_class_attrs(school, **kwargs)
            grp_obj = await udm.get("groups/group").new()
            grp_obj.position = f"cn=klassen,cn=schueler,cn=groups,ou={sc_attrs['school']},{ldap_base}"
            grp_obj.props.name = f"{sc_attrs['school']}-{sc_attrs['name']}"
            grp_obj.props.description = sc_attrs["description"]
            grp_obj.props.users = sc_attrs["users"]
            grp_obj.props.ucsschoolRole = sc_attrs["ucsschool_roles"]
            await grp_obj.save()
            wait_for_replication(grp_obj.dn)
            created_school_classes.append(grp_obj.dn)
            logger.debug("Created new SchoolClass: %r.", grp_obj)

            share_obj = await udm.get("shares/share").new()
            share_obj.position = f"cn=klassen,cn=shares,ou={school},{ldap_base}"
            share_obj.props.name = grp_obj.props.name
            share_obj.props.host = f"{school}.{env_or_ucr('domainname')}"
            share_obj.props.owner = 0
            share_obj.props.group = 0
            share_obj.props.path = f"/home/tmp/{grp_obj.props.name}"
            share_obj.props.directorymode = "0770"
            share_obj.props.ucsschoolRole = [
                create_ucsschool_role_string(role_school_class_share, school),
            ]
            await share_obj.save()
            wait_for_replication(share_obj.dn)
            created_school_shares.append(share_obj.dn)
            logger.debug("Created new ClassShare: %r.", share_obj)

        return grp_obj.dn, sc_attrs

    yield _func

    async with UDM(**udm_kwargs) as udm:
        grp_mod = udm.get("groups/group")
        for dn in created_school_classes:
            try:
                grp_obj = await grp_mod.get(dn)
            except UdmNoObject:
                logger.debug("SchoolClass %r does not exist (anymore).", dn)
                continue
            await grp_obj.delete()
            logger.debug("Deleted SchoolClass %r through UDM.", dn)
        share_mod = udm.get("shares/share")
        for dn in created_school_shares:
            try:
                share_obj = await share_mod.get(dn)
            except UdmNoObject:
                logger.debug("ClassShare %r does not exist (anymore).", dn)
                continue
            await share_obj.delete()
            logger.debug("Deleted ClassShare %r through UDM.", dn)


@pytest_asyncio.fixture
async def new_workgroup_using_udm(udm_kwargs, ldap_base, workgroup_attrs, wait_for_replication):
    """Create a new work group. -> (DN, {attrs})"""
    created_workgroups = []
    created_wg_shares = []

    async def _func(school: str, **kwargs) -> Tuple[str, Dict[str, str]]:
        async with UDM(**udm_kwargs) as udm:
            wg_attrs = workgroup_attrs(school, **kwargs)
            grp_obj = await udm.get("groups/group").new()
            grp_obj.position = f"cn=schueler,cn=groups,ou={wg_attrs['school']},{ldap_base}"
            grp_obj.props.name = f"{wg_attrs['school']}-{wg_attrs['name']}"
            grp_obj.props.description = wg_attrs["description"]
            grp_obj.props.users = wg_attrs["users"]
            grp_obj.props.ucsschoolRole = wg_attrs["ucsschool_roles"]
            await grp_obj.save()
            wait_for_replication(grp_obj.dn)
            created_workgroups.append(grp_obj.dn)
            logger.debug("Created new WorkGroup: %r.", grp_obj)

            share_obj = await udm.get("shares/share").new()
            share_obj.position = f"cn=shares,ou={school},{ldap_base}"
            share_obj.props.name = grp_obj.props.name
            share_obj.props.host = f"{school}.{env_or_ucr('domainname')}"
            share_obj.props.owner = 0
            share_obj.props.group = 0
            share_obj.props.path = f"/home/tmp/{grp_obj.props.name}"
            share_obj.props.directorymode = "0770"
            share_obj.props.ucsschoolRole = [
                create_ucsschool_role_string(role_workgroup_share, school),
            ]
            await share_obj.save()
            wait_for_replication(share_obj.dn)
            created_wg_shares.append(share_obj.dn)
            logger.debug("Created new ClassShare: %r.", share_obj)

        return grp_obj.dn, wg_attrs

    yield _func

    async with UDM(**udm_kwargs) as udm:
        grp_mod = udm.get("groups/group")
        for dn in created_workgroups:
            try:
                grp_obj = await grp_mod.get(dn)
            except UdmNoObject:
                logger.debug("WorkGroup %r does not exist (anymore).", dn)
                continue
            await grp_obj.delete()
            logger.debug("Deleted WorkGroup %r through UDM.", dn)
        share_mod = udm.get("shares/share")
        for dn in created_wg_shares:
            try:
                share_obj = await share_mod.get(dn)
            except UdmNoObject:
                logger.debug("WorkgroupShare %r does not exist (anymore).", dn)
                continue
            await share_obj.delete()
            logger.debug("Deleted WorkgroupShare %r through UDM.", dn)


@pytest.fixture
def new_udm_user(
    udm_kwargs,
    ldap_base,
    udm_users_user_props,
    new_school_class_using_udm,
    new_workgroup_using_udm,
    schedule_delete_user_dn,
    wait_for_replication,
):
    """Create a new school user using UDM. -> (DN, {attrs})"""

    async def _func(
        school: str,
        role: str,
        udm_properties: Dict[str, Any] = None,
        **school_user_kwargs,
    ) -> Tuple[str, Dict[str, Any]]:
        assert role in ("staff", "student", "teacher", "teacher_and_staff", "school_admin")
        udm_properties = udm_properties or {}
        user_props = await udm_users_user_props(school, **school_user_kwargs)
        if role == "teacher_and_staff":
            user_props["ucsschoolRole"] = [
                create_ucsschool_role_string(role_staff, school),
                create_ucsschool_role_string(role_teacher, school),
            ]
        else:
            user_props["ucsschoolRole"] = [create_ucsschool_role_string(role, school)]
        extra_roles = school_user_kwargs.get("ucsschool_roles", [])
        user_props["ucsschoolRole"].extend(extra_roles)
        school_search_base = SchoolSearchBase([school])
        options = {
            "staff": ("ucsschoolStaff",),
            "student": ("ucsschoolStudent",),
            "teacher": ("ucsschoolTeacher",),
            "teacher_and_staff": ("ucsschoolStaff", "ucsschoolTeacher"),
            "school_admin": ("ucsschoolAdministrator",),
        }[role]
        position = {
            "staff": school_search_base.staff,
            "student": school_search_base.students,
            "teacher": school_search_base.teachers,
            "teacher_and_staff": school_search_base.teachersAndStaff,
            "school_admin": school_search_base.admins,
        }[role]
        role_groups = {
            "staff": [SchoolSearchBase([s]).staff_group for s in user_props.get("school", [school])],
            "student": [
                SchoolSearchBase([s]).students_group for s in user_props.get("school", [school])
            ],
            "teacher": [
                SchoolSearchBase([s]).teachers_group for s in user_props.get("school", [school])
            ],
            "teacher_and_staff": [
                SchoolSearchBase([s]).staff_group for s in user_props.get("school", [school])
            ]
            + [SchoolSearchBase([s]).teachers_group for s in user_props.get("school", [school])],
            "school_admin": [
                SchoolSearchBase([s]).admins_group for s in user_props.get("school", [school])
            ],
        }[role]
        user_props.update(udm_properties)
        async with UDM(**udm_kwargs) as udm:
            user_obj = await udm.get("users/user").new()
            user_obj.options.update(dict((opt, True) for opt in options))
            user_obj.position = position
            user_obj.props.update(user_props)
            user_obj.props.primaryGroup = f"cn=Domain Users {school},cn=groups,ou={school},{ldap_base}"
            user_obj.props.ucsschoolRecordUID = school_user_kwargs.get(
                "record_uid", user_props["username"]
            )

            user_obj.props.ucsschoolSourceUID = school_user_kwargs.get("source_uid", "Kelvin")
            user_obj.props.groups = user_props["groups"]
            user_obj.props.groups.extend(role_groups)
            if role != "staff" and "school_classes" not in school_user_kwargs:
                cls_dn1, _ = await new_school_class_using_udm(school=school)
                cls_dn2, _ = await new_school_class_using_udm(school=school)
                user_obj.props.groups.extend([cls_dn1, cls_dn2])
            if "workgroups" not in school_user_kwargs:
                wg_dn1, _ = await new_workgroup_using_udm(school=school)
                wg_dn2, _ = await new_workgroup_using_udm(school=school)
                user_obj.props.groups.extend([wg_dn1, wg_dn2])
            await user_obj.save()

            schedule_delete_user_dn(user_obj.dn)
            wait_for_replication(user_obj.dn)
            logger.debug("Created new %s%s: %r", role[0].upper(), role[1:], user_obj)

        return user_obj.dn, user_props

    yield _func


@pytest.fixture
def new_udm_admin_user(
    udm_kwargs,
    ldap_base,
    udm_users_user_props,
    new_school_class_using_udm,
    new_workgroup_using_udm,
    schedule_delete_user_dn,
    wait_for_replication,
):
    """Create a new school admin user using UDM. -> (DN, {attrs})"""

    async def _func(
        school: str,
        udm_properties: Dict[str, Any] = None,
        **school_user_kwargs,
    ) -> Tuple[str, Dict[str, Any]]:
        extra_roles = school_user_kwargs.get("ucsschool_roles", [])

        user_props = await udm_users_user_props(school, **school_user_kwargs)
        user_props.update(udm_properties or {})
        user_props["ucsschoolRole"] = [create_ucsschool_role_string(role_school_admin, school)]
        user_props["ucsschoolRole"].extend(extra_roles)

        async with UDM(**udm_kwargs) as udm:
            user_obj = await udm.get("users/user").new()
            user_obj.options["ucsschoolAdministrator"] = True
            user_obj.position = SchoolSearchBase([school]).admins
            user_obj.props.update(user_props)
            user_obj.props.primaryGroup = f"cn=Domain Users {school},cn=groups,ou={school},{ldap_base}"
            user_obj.props.ucsschoolRecordUID = school_user_kwargs.get(
                "record_uid", user_props["username"]
            )

            user_obj.props.ucsschoolSourceUID = school_user_kwargs.get("source_uid", "Kelvin")
            user_obj.props.groups = [user_obj.props.primaryGroup]
            user_obj.props.groups.extend(
                SchoolSearchBase([school]).admins_group for school in user_props.get("school", [school])
            )
            await user_obj.save()

            schedule_delete_user_dn(user_obj.dn)
            wait_for_replication(user_obj.dn)
            logger.debug("Created new Administrator: %r", user_obj)

        return user_obj.dn, user_props

    yield _func


@pytest.fixture
def new_school_user(new_udm_user, udm_kwargs):
    """
    Create a new school user using UDM. -> User

    Wrapper around new_udm_user() that returns a lib User object.
    """

    async def _func(
        school: str,
        role: str,
        udm_properties: Dict[str, Any] = None,
        **school_user_kwargs,
    ) -> User:
        dn, user_attrs = await new_udm_user(school, role, udm_properties, **school_user_kwargs)
        async with UDM(**udm_kwargs) as udm:
            user = await User.from_dn(dn, school, udm)
            user.password = user_attrs["password"]
            return user

    return _func


@pytest.fixture
def new_users(new_udm_user):
    """Create multiple new school users using UDM. -> [(DN, {attrs})]"""

    async def _func(
        school: str, roles: Dict[str, int], **school_user_kwargs
    ) -> List[Tuple[str, Dict[str, Any]]]:
        return [
            await new_udm_user(school, role, **school_user_kwargs)
            for role, amount in roles.items()
            for _ in range(amount)
        ]

    return _func


@pytest.fixture
def new_school_users(new_school_user):
    """Create multiple new school users using UDM. -> [User]"""

    async def _func(school: str, roles: Dict[str, int], **school_user_kwargs) -> List[User]:
        return [
            await new_school_user(school, role, **school_user_kwargs)
            for role, amount in roles.items()
            for _ in range(amount)
        ]

    return _func


@pytest_asyncio.fixture
async def schedule_delete_udm_obj(udm_kwargs):
    objs: List[Tuple[str, str]] = []

    def _func(dn: str, udm_mod: str):
        objs.append((dn, udm_mod))

    yield _func

    async with UDM(**udm_kwargs) as udm:
        for dn, udm_mod_name in objs:
            mod = udm.get(udm_mod_name)
            try:
                udm_obj = await mod.get(dn)
            except UdmNoObject:
                logger.debug("UDM %r object %r does not exist (anymore).", udm_mod_name, dn)
                continue
            await udm_obj.delete()
            logger.debug("Deleted UDM %r object %r through UDM.", udm_mod_name, dn)


@pytest_asyncio.fixture
async def schedule_delete_user_dn(schedule_delete_udm_obj):
    def _func(dn: str):
        schedule_delete_udm_obj(dn, "users/user")

    yield _func


@pytest_asyncio.fixture
async def schedule_delete_user_name_using_udm(udm_kwargs):
    usernames = []

    def _func(username: str):
        usernames.append(username)

    yield _func

    async with UDM(**udm_kwargs) as udm:
        user_mod = udm.get("users/user")
        for username in usernames:
            async for user_obj in user_mod.search(f"uid={username}"):
                await user_obj.delete()
                break
            else:
                logger.debug("User %r does not exist (anymore).", username)
                continue
            logger.debug("Deleted user %r through UDM.", username)


@pytest.fixture
def role2class():
    return {
        "staff": ucsschool.lib.models.user.Staff,
        "student": ucsschool.lib.models.user.Student,
        "teacher": ucsschool.lib.models.user.Teacher,
        "teacher_and_staff": ucsschool.lib.models.user.TeachersAndStaff,
        "school_admin": ucsschool.lib.models.user.SchoolAdmin,
    }


@pytest.fixture
def cn_attrs(ldap_base):
    raise NotImplementedError


@pytest_asyncio.fixture
async def new_cn(udm_kwargs, ldap_base, cn_attrs, wait_for_replication):
    """Create a new container"""
    created_cns = []

    async def _func() -> Tuple[str, Dict[str, str]]:
        async with UDM(**udm_kwargs) as udm:
            attr = cn_attrs()
            obj = await udm.get("container/cn").new()
            obj.position = f"ou={attr['school']},{ldap_base}"
            obj.props.name = attr["name"]
            obj.props.description = attr["description"]
            await obj.save()
            wait_for_replication(obj.dn)
            created_cns.append(obj.dn)
            logger.debug("Created new container: %r.", obj)

        return obj.dn, attr

    yield _func

    async with UDM(**udm_kwargs) as udm:
        mod = udm.get("container/cn")
        for dn in created_cns:
            try:
                obj = await mod.get(dn)
            except UdmNoObject:
                logger.debug("Container %r does not exist (anymore).", dn)
                continue
            await obj.delete()
            logger.debug("Deleted container %r.", dn)


@pytest.fixture
def random_logger():
    with tempfile.NamedTemporaryFile() as f:
        handler = get_file_handler("DEBUG", f.name)
        logger = logging.getLogger(f.name)
        logger.addHandler(handler)
        logger.setLevel("DEBUG")
        yield logger


@pytest.fixture(scope="session")
def installed_ssh():
    if not Path("/usr/bin/ssh").exists() or not Path("/usr/bin/sshpass").exists():
        logger.debug("Installing 'ssh' and 'sshpass'...")
        returncode, stdout, stderr = exec_cmd(
            ["apk", "add", "--no-cache", "openssh", "sshpass"], log=True
        )
        logger.debug("stdout=%s", stdout or "<empty>")
        logger.debug("stderr=%s", stderr or "<empty>")
    else:
        logger.debug("'ssh' and 'sshpass' are already installed.")


@pytest.fixture(scope="session")
def exec_with_ssh(docker_host_name, installed_ssh):
    def _func(cmd: List[str], host: str = None) -> Tuple[int, str, str]:
        host = host or docker_host_name
        ssh_cmd = [
            "/usr/bin/sshpass",
            "-p",
            "univention",
            "/usr/bin/ssh",
            "-o",
            "StrictHostKeyChecking no",
            f"root@{host}",
        ] + cmd
        logger.debug("ssh to %r and execute: %r...", host, cmd)
        returncode, stdout, stderr = exec_cmd(ssh_cmd, log=True)
        logger.debug("stdout=%s", stdout or "<empty>")
        logger.debug("stderr=%s", stderr or "<empty>")
        return returncode, stdout, stderr

    return _func


@pytest.fixture(scope="session")
def delete_ou_using_ssh(exec_with_ssh, ldap_base):
    async def _func(ou_name: str, host: str):
        logger.debug("Deleting OU %r on host %r...", ou_name, host)
        dn = f"ou={ou_name},{ldap_base}"
        retries = 2
        while retries > 0:
            _, stdout, _ = exec_with_ssh(["/usr/sbin/udm", "container/ou", "remove", "--dn", dn], host)
            if "Operation not allowed on non-leaf" in stdout:
                retries -= 1
            else:
                break

    return _func


@pytest.fixture(scope="session")
def delete_ou_cleanup(ldap_base, udm_kwargs):
    async def _func(ou_name: str):
        group_dns = [
            f"cn=admins-{ou_name.lower()},cn=ouadmins,cn=groups,{ldap_base}",
            f"cn=OU{ou_name}-Klassenarbeit,cn=ucsschool,cn=groups,{ldap_base}",
            f"cn=OU{ou_name.lower()}-DC-Edukativnetz,cn=ucsschool,cn=groups,{ldap_base}",
            f"cn=OU{ou_name.lower()}-DC-Verwaltungsnetz,cn=ucsschool,cn=groups,{ldap_base}",
            f"cn=OU{ou_name.lower()}-Member-Edukativnetz,cn=ucsschool,cn=groups,{ldap_base}",
            f"cn=OU{ou_name.lower()}-Member-Verwaltungsnetz,cn=ucsschool,cn=groups,{ldap_base}",
        ]
        async with UDM(**udm_kwargs) as udm:
            mod = udm.get("groups/group")
            for dn in group_dns:
                logger.debug("Deleting group: %r...", dn)
                try:
                    obj = await mod.get(dn)
                    await obj.delete()
                except UdmNoObject:
                    logger.debug("Error: group does not exist: %r", dn)
        if ucr.is_true("ucsschool/singlemaster"):
            master_hostname = env_or_ucr("ldap/master").split(".", 1)[0]
            async with UDM(**udm_kwargs) as udm:
                mod = udm.get("computers/domaincontroller_master")
                async for obj in mod.search(f"cn={master_hostname}"):
                    logger.debug(
                        "Removing 'ucsschoolRole=single_master:school:%s' from %r...",
                        ou_name,
                        obj.dn,
                    )
                    try:
                        obj.props.ucsschoolRole.remove(f"single_master:school:{ou_name}")
                        await obj.save()
                    except ValueError:
                        logger.debug(
                            "Error: role was no set: ucsschoolRole=%r",
                            obj.props.ucsschoolRole,
                        )

    return _func


@pytest_asyncio.fixture
async def schedule_delete_ou_using_ssh(delete_ou_using_ssh, delete_ou_cleanup):
    ous_created: List[Tuple[str, str]] = []

    def _func(ou_name: str, host: str):
        ous_created.append((ou_name, host))

    yield _func

    for ou_name, host in ous_created:
        await delete_ou_using_ssh(ou_name, host)
        await delete_ou_cleanup(ou_name)


@pytest_asyncio.fixture(scope="session")
async def schedule_delete_ou_using_ssh_at_end_of_session(delete_ou_using_ssh, delete_ou_cleanup):
    def _func(ou_name: str, host: str):
        _cached_ous.add((ou_name, host))

    yield _func

    for ou_name, host in _cached_ous:
        await delete_ou_using_ssh(ou_name, host)
        await delete_ou_cleanup(ou_name)


def create_ou_kwargs(ou_name: str = None) -> Dict[str, Any]:
    ou_name = ou_name or f"testou{fake.unique.pyint(1000, 9999)}"
    assert ou_name not in {ou[0] for ou in _cached_ous}
    short_ou_name = f"{ou_name}"[:10]
    is_single_master = ucr.is_true("ucsschool/singlemaster")
    master_hostname = env_or_ucr("ldap/master").split(".", 1)[0]
    edu_name = master_hostname if is_single_master else f"edu{short_ou_name}"
    admin_name = f"adm{short_ou_name}"
    hostname = master_hostname if is_single_master else None
    return {
        "ou_name": ou_name,
        "display_name": f"display name of {ou_name}",
        "edu_name": edu_name,
        "admin_name": admin_name,
        "share_name": edu_name,
        "baseDN": ldap_base,
        "hostname": hostname,
        "is_single_master": is_single_master,
        "alter_dhcpd_base": False,
    }


def get_ou_from_cache(ou_name: str, cache: bool) -> str:
    if ou_name in {c[0] for c in _cached_ous}:
        if not cache:
            raise ValueError(f"Requested fresh OU, but ou {ou_name!r} is in cache.")
        return ou_name
    if not ou_name and cache and len(_cached_ous) > 2:
        # Only return OUs from cache, when we have at least 3 OUs in it. This is to get a bit of
        # randomization / isolation in the tests.
        return random.choice(tuple(_cached_ous))[0]  # nosec
    return ""


@pytest.fixture
def create_ou_using_ssh(
    docker_host_name,
    exec_with_ssh,
    ldap_base,
    delete_ou_using_ssh,
    schedule_delete_ou_using_ssh,
    schedule_delete_ou_using_ssh_at_end_of_session,
    udm_kwargs,
    wait_for_replication,
):
    async def _func(ou_name: str = None, host: str = None, cache: bool = True) -> str:
        if cached_ou := get_ou_from_cache(ou_name, cache):
            logger.debug("Using OU %r from cache.", ou_name)
            return cached_ou
        args = create_ou_kwargs(ou_name)
        ou_name = args["ou_name"]
        host = host or docker_host_name
        logger.debug("Creating school %r on host %r using SSH...", ou_name, host)
        if cache:
            schedule_delete_ou_using_ssh_at_end_of_session(ou_name, host)
        else:
            schedule_delete_ou_using_ssh(ou_name, host)
        returncode, stdout, stderr = exec_with_ssh(
            [
                "/usr/share/ucs-school-import/scripts/create_ou",
                ou_name,
                args["edu_name"],
                args["admin_name"],
                f"--sharefileserver={args['share_name']}",
                f"--displayName=\"{args['display_name']}\"",
                f"--alter-dhcpd-base={str(args['alter_dhcpd_base']).lower()}",
            ]
        )
        assert (not stderr) or ("Already attached!" in stderr) or ("created successfully" in stderr)
        if "Already attached!" in stderr:
            logger.debug(" => OU %r exists in %r.", ou_name, host)
        else:
            logger.debug(" => OU %r created in %r.", ou_name, host)
        dn = f"ou={ou_name},{ldap_base}"
        async with UDM(**udm_kwargs) as udm:
            try:
                await udm.get("container/ou").get(dn)
            except UdmNoObject:
                raise AssertionError(f"Creation of OU {ou_name} failed.")
        wait_for_replication(dn)
        return ou_name

    return _func


@pytest.fixture
def create_ou_using_python(
    docker_host_name,
    ldap_base,
    delete_ou_using_ssh,
    schedule_delete_ou_using_ssh,
    schedule_delete_ou_using_ssh_at_end_of_session,
    udm_kwargs,
    wait_for_replication,
):
    async def _func(ou_name: str = None, cache: bool = True) -> str:
        if cached_ou := get_ou_from_cache(ou_name, cache):
            logger.debug("Using cached school %r.", cached_ou)
            return cached_ou
        args = create_ou_kwargs(ou_name)
        ou_name = args["ou_name"]
        logger.debug(
            " ================ Creating school %r using Python... ================",
            ou_name,
        )
        if cache:
            schedule_delete_ou_using_ssh_at_end_of_session(ou_name, docker_host_name)
        else:
            schedule_delete_ou_using_ssh(ou_name, docker_host_name)
        async with UDM(**udm_kwargs) as udm:
            if await School(ou_name).exists(udm):
                logger.debug("School %r exists.", ou_name)
                return ou_name
        is_single_master = ucr.is_true("ucsschool/singlemaster")
        master_hostname = env_or_ucr("ldap/master").split(".", 1)[0]
        hostname = master_hostname if is_single_master else None
        create_ou_python_kwargs = {
            "ou_name": ou_name,
            "display_name": args["display_name"],
            "edu_name": args["edu_name"],
            "admin_name": args["admin_name"],
            "share_name": args["share_name"],
            "baseDN": ldap_base,
            "hostname": hostname,
            "is_single_master": is_single_master,
            "alter_dhcpd_base": False,
        }
        logger.debug("=> kwargs for create_ou: %r", create_ou_python_kwargs)
        dn = f"ou={ou_name},{ldap_base}"
        async with UDM(**udm_kwargs) as udm:
            await create_ou(lo=udm, **create_ou_python_kwargs)
            try:
                await udm.get("container/ou").get(dn)
            except UdmNoObject:
                raise AssertionError(f"Creation of OU {ou_name} failed.")
        wait_for_replication(dn)
        logger.debug(
            " ====================================================%s",
            len(ou_name) * "=",
        )
        logger.debug(" ================ School %r created. ================", ou_name)
        logger.debug(
            " ====================================================%s",
            len(ou_name) * "=",
        )
        return ou_name

    return _func


@pytest.fixture
def create_multiple_ous(
    create_ou_using_python,
    random_ou_name,
    schedule_delete_ou_using_ssh_at_end_of_session,
):
    async def _func(amount: int, cache: bool = True) -> List[str]:
        if not cache:
            return [await create_ou_using_python(cache=cache) for _ in range(amount)]
        while len(_cached_ous) < amount:
            await create_ou_using_python(ou_name=random_ou_name())
        res = [c[0] for c in _cached_ous]
        random.shuffle(res)
        return res[:amount]

    return _func


@pytest.fixture(scope="session")
def wait_for_replication():
    def _wait_for_replication(dn: str, timeout: int = 60):
        conf = uldap_conf()
        if conf.host_fqdn == conf.primary_fqdn:
            return
        logger.debug("Waiting for replication of %r...", dn)
        filter_s, search_base = dn.split(",", 1)
        filter_s = f"({filter_s})"
        uldap_primary = uldap_admin_read_primary()
        assert uldap_primary.search_dn(
            search_filter=filter_s, search_base=search_base
        ), f"DN {dn!r} not found on primary."
        start = datetime.datetime.now()
        end = start + datetime.timedelta(seconds=timeout)
        uldap_local = uldap_admin_read_local()
        while datetime.datetime.now() < end:
            if uldap_local.search_dn(search_filter=filter_s, search_base=search_base):
                logger.debug(
                    "DN %r was found in local LDAP after %d seconds.",
                    dn,
                    (datetime.datetime.now() - start).seconds,
                )
                return
            time.sleep(1)
        raise AssertionError(
            f"DN {dn!r} was not found in local LDAP after {(datetime.datetime.now() - start).seconds} "
            f"seconds."
        )

    return _wait_for_replication
