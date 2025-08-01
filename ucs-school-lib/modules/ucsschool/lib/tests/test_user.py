import datetime
import itertools
import random
from typing import Any, Dict, List, NamedTuple, Tuple, Type, Union

import pytest
from faker import Faker
from ldap.filter import filter_format

from ucsschool.lib.models.attributes import ValidationError
from ucsschool.lib.models.group import SchoolClass
from ucsschool.lib.models.user import (
    ExamStudent,
    SchoolAdmin,
    Staff,
    Student,
    Teacher,
    TeachersAndStaff,
    User,
    UserTypeConverter,
    convert_to_school_admin,
    convert_to_staff,
    convert_to_student,
    convert_to_teacher,
    convert_to_teacher_and_staff,
)
from ucsschool.lib.roles import role_school_admin
from ucsschool.lib.schoolldap import SchoolSearchBase
from udm_rest_client import UDM
from udm_rest_client.exceptions import CreateError, ModifyError
from univention.admin.uexceptions import noObject

UserType = Union[
    Type[Staff], Type[Student], Type[Teacher], Type[TeachersAndStaff], Type[SchoolAdmin], Type[User]
]
Role = NamedTuple("Role", [("name", str), ("klass", UserType)])


def _inside_docker():
    try:
        import ucsschool.kelvin.constants
    except ImportError:
        return False
    return ucsschool.kelvin.constants.CN_ADMIN_PASSWORD_FILE.exists()


pytestmark = pytest.mark.skipif(
    not _inside_docker(),
    reason="Must run inside Docker container started by appcenter.",
)
fake = Faker()
USER_ROLES: List[Role] = [
    Role("staff", Staff),
    Role("student", Student),
    Role("teacher", Teacher),
    Role("teacher_and_staff", TeachersAndStaff),
    Role("school_admin", SchoolAdmin),
]
random.shuffle(USER_ROLES)


def compare_attr_and_lib_user(attr: Dict[str, Any], user: User):
    _user_as_dict = user.to_dict()  # noqa: F841 for pytest output
    for k, v in attr.items():
        if k in ("description", "password", "primaryGroup", "groups"):
            continue
        if k == "username":
            val1 = v
            val2 = user.name
        elif k == "school":
            val1 = v
            val2 = user.schools
        elif k == "birthday":
            val1 = str(v)
            val2 = user.birthday
        elif k == "userexpiry":
            val1 = str(v)
            val2 = user.expiration_date
        elif k == "mailPrimaryAddress":
            val1 = v
            val2 = user.email
        elif k == "e-mail":
            val1 = set(v)
            val2 = {user.email}
        elif k == "ucsschoolRole":
            val1 = v
            val2 = user.ucsschool_roles
        else:
            val1 = v
            val2 = getattr(user, k)
        if isinstance(v, list):
            val1 = set(val1)
            val2 = set(val2)
        assert val1 == val2


def make_ucsschool_roles(user_cls: Type[User], schools: List[str]) -> List[str]:
    return [f"{role}:school:{school}" for role in user_cls.default_roles for school in schools]


def role_id(value: Role) -> str:
    return value.name


def two_roles_id(value: List[Role]) -> str:
    return f"{value[0].name} -> {value[1].name}"


@pytest.mark.asyncio
@pytest.mark.parametrize("role", USER_ROLES, ids=role_id)
async def test_exists(create_ou_using_python, new_udm_user, udm_kwargs, role: Role):
    ou = await create_ou_using_python()
    dn, attr = await new_udm_user(ou, role.name)
    async with UDM(**udm_kwargs) as udm:
        for kls in (role.klass, User):
            user0 = await kls.from_dn(dn, ou, udm)
            assert await user0.exists(udm) is True
            user1 = kls(name=attr["username"], school=ou)
            assert await user1.exists(udm) is True
            user2 = kls(name=fake.pystr(), school=ou)
            assert await user2.exists(udm) is False


@pytest.mark.asyncio
@pytest.mark.parametrize("role", USER_ROLES, ids=role_id)
async def test_from_dn(create_ou_using_python, new_udm_user, udm_kwargs, role: Role):
    ou = await create_ou_using_python()
    dn, attr = await new_udm_user(ou, role.name)
    async with UDM(**udm_kwargs) as lo_udm:
        for kls in (role.klass, User):
            user = await kls.from_dn(dn, ou, lo_udm)
            assert isinstance(user, role.klass)
            compare_attr_and_lib_user(attr, user)


@pytest.mark.asyncio
@pytest.mark.parametrize("role", USER_ROLES, ids=role_id)
async def test_from_udm_obj(create_ou_using_python, new_udm_user, udm_kwargs, role: Role):
    ou = await create_ou_using_python()
    dn, attr = await new_udm_user(ou, role.name)
    async with UDM(**udm_kwargs) as udm:
        for kls in (role.klass, User):
            udm_mod = udm.get(kls._meta.udm_module)
            udm_obj = await udm_mod.get(dn)
            user = await kls.from_udm_obj(udm_obj, ou, udm)
            assert isinstance(user, role.klass)
            compare_attr_and_lib_user(attr, user)


@pytest.mark.asyncio
@pytest.mark.parametrize("role", USER_ROLES, ids=role_id)
async def test_get_all(create_ou_using_python, new_udm_user, udm_kwargs, role: Role):
    ou = await create_ou_using_python()
    dn, attr = await new_udm_user(ou, role.name)
    async with UDM(**udm_kwargs) as udm:
        for kls in (role.klass, User):
            for obj in await kls.get_all(udm, ou):
                if obj.dn == dn:
                    break
            else:
                raise AssertionError(f"DN {dn!r} not found in {kls.__name__}.get_all(udm, {ou}).")
            filter_str = filter_format("(uid=%s)", (attr["username"],))
            objs = await kls.get_all(udm, ou, filter_str=filter_str)
            assert len(objs) == 1
            assert isinstance(objs[0], role.klass)
            compare_attr_and_lib_user(attr, objs[0])


@pytest.mark.asyncio
@pytest.mark.parametrize("role", USER_ROLES, ids=role_id)
async def test_get_class_for_udm_obj(
    create_ou_using_python, new_udm_user, role2class, udm_kwargs, role: Role
):
    ou = await create_ou_using_python()
    dn, attr = await new_udm_user(ou, role.name)
    async with UDM(**udm_kwargs) as udm:
        udm_obj = await udm.get(User._meta.udm_module).get(dn)
        klass = await User.get_class_for_udm_obj(udm_obj, ou)
        assert klass is role.klass


@pytest.mark.asyncio
@pytest.mark.parametrize("role", USER_ROLES, ids=role_id)
async def test_create(
    create_ou_using_python,
    new_school_class_using_udm,
    udm_users_user_props,
    udm_kwargs,
    role: Role,
):
    school = await create_ou_using_python()
    async with UDM(**udm_kwargs) as udm:
        user_props = await udm_users_user_props(school)
        user_props["name"] = user_props["username"]
        user_props["email"] = user_props["mailPrimaryAddress"]
        user_props["school"] = school
        user_props["birthday"] = str(user_props["birthday"])
        user_props["expiration_date"] = str(user_props["userexpiry"])
        del user_props["e-mail"]
        del user_props["userexpiry"]
        if role.klass != Staff:
            cls_dn1, cls_attr1 = await new_school_class_using_udm(school=school)
            cls_dn2, cls_attr2 = await new_school_class_using_udm(school=school)
            user_props["school_classes"] = {
                school: [
                    f"{school}-{cls_attr1['name']}",
                    f"{school}-{cls_attr2['name']}",
                ]
            }
        user = role.klass(**user_props)
        success = await user.create(udm)
        assert success is True
        user = await role.klass.from_dn(user.dn, school, udm)
        user_props["school"] = [school]
        compare_attr_and_lib_user(user_props, user)


@pytest.mark.asyncio
@pytest.mark.parametrize("role", USER_ROLES, ids=role_id)
@pytest.mark.parametrize(
    "extra_role,allowed",
    [
        ("my:funny:role", True),
        ("not:funny", False),
        ("123", False),
        ("my:school:not_allowed", False),
    ],
)
async def test_create_arbitrary_extra_roles(
    create_ou_using_python,
    new_school_class_using_udm,
    udm_users_user_props,
    udm_kwargs,
    role: Role,
    extra_role,
    allowed,
):
    """
    00_ucsschool_roles
    """
    school = await create_ou_using_python()
    async with UDM(**udm_kwargs) as udm:
        user_props = await udm_users_user_props(school)
        user_props["name"] = user_props["username"]
        user_props["email"] = user_props["mailPrimaryAddress"]
        user_props["school"] = school
        if extra_role == "duplicate_role":
            extra_role = "{}:school:{}".format(role.name, school)
        user_props["ucsschool_roles"] = [extra_role]
        del user_props["e-mail"]
        del user_props["userexpiry"]
        if role.klass != Staff:
            cls_dn1, cls_attr1 = await new_school_class_using_udm(school=school)
            cls_dn2, cls_attr2 = await new_school_class_using_udm(school=school)
            user_props["school_classes"] = {
                school: [
                    f"{school}-{cls_attr1['name']}",
                    f"{school}-{cls_attr2['name']}",
                ]
            }
        user = role.klass(**user_props)
        if allowed:
            success = await user.create(udm)
            assert success is True
            user = await role.klass.from_dn(user.dn, school, udm)
            user_props["school"] = [school]
            compare_attr_and_lib_user(user_props, user)
        else:
            expected_error = r"Role has bad format" if "school" not in extra_role else r"Unknown role"
            with pytest.raises(ValidationError, match=expected_error):
                await user.create(udm)


@pytest.mark.asyncio
@pytest.mark.parametrize("role", USER_ROLES, ids=role_id)
@pytest.mark.parametrize(
    "extra_role,allowed",
    [
        ("my:funny:role", True),
        ("not:funny", False),
        ("123", False),
        ("my:school:existing_school", False),
    ],
)
async def test_modify_arbitrary_extra_roles(
    create_ou_using_python, new_udm_user, udm_kwargs, role: Role, extra_role, allowed
):
    """
    00_ucsschool_roles
    """
    ou = await create_ou_using_python()
    dn, attr = await new_udm_user(ou, role.name)
    async with UDM(**udm_kwargs) as udm:
        user: User = await role.klass.from_dn(dn, ou, udm)
        extra_role = extra_role.replace("existing_school", ou)
        user.ucsschool_roles.append(extra_role)
        if allowed:
            await user.modify(udm)
        else:
            expected_error = r"Role has bad format" if "school" not in extra_role else r"Unknown role"
            with pytest.raises(ValidationError, match=expected_error):
                await user.modify(udm)


@pytest.mark.asyncio
@pytest.mark.parametrize("role", USER_ROLES, ids=role_id)
@pytest.mark.parametrize("check_password_policies", [True, False])
async def test_create_check_password_policies(
    create_ou_using_python,
    new_school_class_using_udm,
    udm_users_user_props,
    udm_kwargs,
    role: Role,
    check_password_policies,
):
    school = await create_ou_using_python()
    async with UDM(**udm_kwargs) as udm:
        user_props = await udm_users_user_props(school)
        user_props["name"] = user_props["username"]
        user_props["school"] = school
        del user_props["e-mail"]
        del user_props["userexpiry"]
        if role.klass != Staff:
            cls_dn1, cls_attr1 = await new_school_class_using_udm(school=school)
            cls_dn2, cls_attr2 = await new_school_class_using_udm(school=school)
            user_props["school_classes"] = {
                school: [
                    f"{school}-{cls_attr1['name']}",
                    f"{school}-{cls_attr2['name']}",
                ]
            }
        user_props["password"] = "s"  # nosec
        user = role.klass(**user_props)
        if check_password_policies:
            with pytest.raises(CreateError, match=r".*Password policy error.*"):
                await user.create(udm, check_password_policies=check_password_policies)
        else:
            await user.create(udm, check_password_policies=check_password_policies)


@pytest.mark.asyncio
@pytest.mark.parametrize("role", USER_ROLES, ids=role_id)
async def test_modify(create_ou_using_python, new_udm_user, udm_kwargs, role: Role):
    ou = await create_ou_using_python()
    dn, attr = await new_udm_user(ou, role.name)
    async with UDM(**udm_kwargs) as udm:
        user: User = await role.klass.from_dn(dn, ou, udm)
        description = fake.text(max_nb_chars=50)
        user.description = description
        firstname = fake.first_name()
        user.firstname = firstname
        lastname = fake.last_name()
        user.lastname = lastname
        birthday = fake.date_of_birth(minimum_age=6, maximum_age=65).strftime("%Y-%m-%d")
        user.birthday = birthday
        start_date = datetime.datetime.strptime(user.expiration_date, "%Y-%m-%d").date()
        expiration_date = fake.date_between(start_date=start_date, end_date="+15y").strftime("%Y-%m-%d")
        user.expiration_date = expiration_date
        success = await user.modify(udm)
        assert success is True
        user = await role.klass.from_dn(dn, ou, udm)
    attr.update(
        {
            "firstname": firstname,
            "lastname": lastname,
            "birthday": birthday,
            "userexpiry": expiration_date,
        }
    )
    compare_attr_and_lib_user(attr, user)


@pytest.mark.asyncio
@pytest.mark.parametrize("role", USER_ROLES, ids=role_id)
@pytest.mark.parametrize("check_password_policies", [True, False])
async def test_modify_check_password_policies(
    create_ou_using_python, new_udm_user, udm_kwargs, role: Role, check_password_policies
):
    ou = await create_ou_using_python()
    dn, attr = await new_udm_user(ou, role.name)
    async with UDM(**udm_kwargs) as udm:
        user: User = await role.klass.from_dn(dn, ou, udm)
        user.password = "s"  # nosec
        if check_password_policies:
            with pytest.raises(ModifyError, match=r".*Password policy error.*"):
                await user.modify(udm, check_password_policies=check_password_policies)
        else:
            await user.modify(udm, check_password_policies=check_password_policies)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "roles",
    set(itertools.product(USER_ROLES, USER_ROLES))
    - {(Role("school_admin", SchoolAdmin), Role("student", Student))},
    ids=two_roles_id,
)
async def test_modify_role(
    ldap_base,
    new_school_class_using_udm,
    new_udm_user,
    udm_kwargs,
    roles: Tuple[Role, Role],
    schedule_delete_user_dn,
    create_multiple_ous,
):
    role_from, role_to = roles
    ou1, ou2 = await create_multiple_ous(2)
    dn, attr = await new_udm_user(ou1, role_from.name)
    async with UDM(**udm_kwargs) as udm:
        use_old_udm = await udm.get("users/user").get(dn)
        # add a school class also to staff users, so we can check if it is kept upon conversion to other
        # role
        cls_dn1, cls_attr1 = await new_school_class_using_udm(school=ou1)
        cls_dn2, cls_attr2 = await new_school_class_using_udm(school=ou1)
        role_ou2 = f"teacher:school:{ou2}"
        cls_dn3, cls_attr3 = await new_school_class_using_udm(school=ou2)
        use_old_udm.props.school.append(ou2)
        role_group_prefix = {
            "staff": "mitarbeiter",
            "student": "schueler",
            "teacher": "lehrer",
            "teacher_and_staff": "mitarbeiter",
            "school_admin": "admins",
        }[role_from.name]
        ou2_group_cn = f"cn=groups,ou={ou2},{ldap_base}"
        role_groupdn_suffix = (
            f"cn=ouadmins,cn=groups,{ldap_base}" if role_from.name == "school_admin" else ou2_group_cn
        )
        use_old_udm.props.groups.extend(
            [
                cls_dn1,
                cls_dn3,
                f"cn=Domain Users {ou2},{ou2_group_cn}",
                f"cn={role_group_prefix}-{ou2.lower()},{role_groupdn_suffix}",
            ]
        )
        non_school_role = f"{fake.first_name()}:{fake.last_name()}:{fake.user_name()}"
        use_old_udm.props.ucsschoolRole.extend([role_ou2, non_school_role])
        await use_old_udm.save()
        user_old = await role_from.klass.from_dn(dn, attr["school"][0], udm)
        assert isinstance(user_old, role_from.klass)
        # check 'addition_class' functionality
        addition_class = {cls_attr2["school"]: [cls_attr2["name"]]}
        if issubclass(role_from.klass, Staff) and issubclass(role_to.klass, Student):
            # Staff user will have no school_class, but for conversion to Student it needs one class per
            # school:
            addition_class[ou2] = [cls_attr3["name"]]

        if issubclass(role_to.klass, Staff):
            user_new = await convert_to_staff(user_old, udm, addition_class)
        elif issubclass(role_to.klass, Student):
            user_new = await convert_to_student(user_old, udm, addition_class)
        elif issubclass(role_to.klass, TeachersAndStaff):
            user_new = await convert_to_teacher_and_staff(user_old, udm, addition_class)
        elif issubclass(role_to.klass, Teacher):
            user_new = await convert_to_teacher(user_old, udm, addition_class)
        elif issubclass(role_to.klass, SchoolAdmin):
            user_new = await convert_to_school_admin(user_old, udm, addition_class)
        else:
            raise RuntimeError(f"Unknown user class: {role_to.klass!r}")

        schedule_delete_user_dn(user_new.dn)

        if role_from.klass == role_to.klass:
            assert user_old is user_new
            return

        user_new_udm = await udm.get("users/user").get(user_new.dn)
        user_new_ucsschool_roles = set(user_new.ucsschool_roles)
        new_groups = {grp.lower() for grp in user_new_udm.props.groups}

        # check class
        assert isinstance(user_new, role_to.klass)
        assert user_new.__class__ is role_to.klass
        # check domain users OU
        for ou in user_new.schools:
            assert f"cn=Domain Users {ou},cn=groups,ou={ou},{ldap_base}".lower() in new_groups
        # check non-school role is ignored
        assert non_school_role in user_new_ucsschool_roles
        if isinstance(user_new, Staff):
            # check school class
            assert cls_dn1.lower() not in new_groups
            assert cls_dn2.lower() not in new_groups
            assert cls_dn3.lower() not in new_groups
            # check options
            assert user_new_udm.options.get("ucsschoolStaff") is True
            assert user_new_udm.options.get("ucsschoolStudent", False) is False
            assert user_new_udm.options.get("ucsschoolTeacher", False) is False
            assert user_new_udm.options.get("ucsschoolAdministrator", False) is False
            # check position
            assert user_new_udm.position == f"cn=mitarbeiter,cn=users,ou={user_new.school},{ldap_base}"
            # check roles
            assert {f"staff:school:{ou}" for ou in user_new.schools}.issubset(user_new_ucsschool_roles)
            assert {
                f"{role}:school:{ou}"
                for ou in user_new.schools
                for role in ("student", "teacher", "school_admin")
            }.isdisjoint(user_new_ucsschool_roles)
        elif isinstance(user_new, Student):
            assert cls_dn1.lower() in new_groups
            assert cls_dn2.lower() in new_groups
            assert cls_dn3.lower() in new_groups
            assert user_new_udm.options.get("ucsschoolStudent") is True
            assert user_new_udm.options.get("ucsschoolAdministrator", False) is False
            assert user_new_udm.options.get("ucsschoolStaff", False) is False
            assert user_new_udm.options.get("ucsschoolTeacher", False) is False
            assert user_new_udm.position == f"cn=schueler,cn=users,ou={user_new.school},{ldap_base}"
            assert {f"student:school:{ou}" for ou in user_new.schools}.issubset(user_new_ucsschool_roles)
            assert {
                f"{role}:school:{ou}"
                for ou in user_new.schools
                for role in ("school_admin", "staff", "teacher")
            }.isdisjoint(user_new_ucsschool_roles)
        elif isinstance(user_new, TeachersAndStaff):
            assert cls_dn1.lower() in new_groups
            assert cls_dn2.lower() in new_groups
            assert cls_dn3.lower() in new_groups
            assert user_new_udm.options.get("ucsschoolStaff") is True
            assert user_new_udm.options.get("ucsschoolTeacher") is True
            assert user_new_udm.options.get("ucsschoolStudent", False) is False
            assert user_new_udm.options.get("ucsschoolAdministrator", False) is False
            assert (
                user_new_udm.position == f"cn=lehrer und mitarbeiter,cn=users,ou={user_new.school},"
                f"{ldap_base}"
            )
            assert {
                f"{role}:school:{ou}" for ou in user_new.schools for role in ("staff", "teacher")
            }.issubset(user_new_ucsschool_roles)
            assert {
                f"{role}:school:{ou}" for ou in user_new.schools for role in ("student", "school_admin")
            }.isdisjoint(user_new_ucsschool_roles)
        elif isinstance(user_new, Teacher):
            assert cls_dn1.lower() in new_groups
            assert cls_dn2.lower() in new_groups
            assert cls_dn3.lower() in new_groups
            assert user_new_udm.options.get("ucsschoolTeacher") is True
            assert user_new_udm.options.get("ucsschoolStaff", False) is False
            assert user_new_udm.options.get("ucsschoolStudent", False) is False
            assert user_new_udm.options.get("ucsschoolAdministrator", False) is False
            assert user_new_udm.position == f"cn=lehrer,cn=users,ou={user_new.school},{ldap_base}"
            assert {f"teacher:school:{ou}" for ou in user_new.schools}.issubset(user_new_ucsschool_roles)
            assert {
                f"{role}:school:{ou}"
                for ou in user_new.schools
                for role in ("student", "staff", "school_admin")
            }.isdisjoint(user_new_ucsschool_roles)
        elif isinstance(user_new, SchoolAdmin):
            assert cls_dn1.lower() in new_groups
            assert cls_dn2.lower() in new_groups
            assert cls_dn3.lower() in new_groups
            assert user_new_udm.options.get("ucsschoolTeacher", False) is False
            assert user_new_udm.options.get("ucsschoolStaff", False) is False
            assert user_new_udm.options.get("ucsschoolStudent", False) is False
            assert user_new_udm.options.get("ucsschoolAdministrator") is True
            assert user_new_udm.position == f"cn=admins,cn=users,ou={user_new.school},{ldap_base}"
            assert {f"{role_school_admin}:school:{ou}" for ou in user_new.schools}.issubset(
                user_new_ucsschool_roles
            )
            assert {
                f"{role}:school:{ou}"
                for ou in user_new.schools
                for role in ("student", "staff", "teacher")
            }.isdisjoint(user_new_ucsschool_roles)
        else:
            raise RuntimeError(f"Unknown user class: {user_new!r}")


@pytest.mark.asyncio
async def test_modify_role_forbidden(
    ldap_base,
    new_school_class_using_udm,
    udm_users_user_props,
    new_udm_user,
    udm_kwargs,
    schedule_delete_user_dn,
    create_multiple_ous,
):
    ou1, ou2 = await create_multiple_ous(2)
    # illegal source objects
    cls_dn, cls_attr = await new_school_class_using_udm(school=ou1)
    async with UDM(**udm_kwargs) as udm:
        sc_obj = await SchoolClass.from_dn(cls_dn, cls_attr["school"], udm)
        with pytest.raises(TypeError, match=r"is not an object of a 'User' subclass"):
            new_user_obj = await convert_to_staff(sc_obj, udm)
            schedule_delete_user_dn(new_user_obj.dn)

        dn, attr = await new_udm_user(ou1, "school_admin")
        user_obj = await SchoolAdmin.from_dn(dn, ou1, udm)
        user_udm = await user_obj.get_udm_object(udm)
        user_udm.options["ucsschoolAdministrator"] = True
        with pytest.raises(TypeError, match=r"not allowed for school administrator"):
            new_user_obj = await convert_to_student(user_obj, udm)
            schedule_delete_user_dn(new_user_obj.dn)

    user_props = await udm_users_user_props(ou1)
    user_props["name"] = user_props.pop("username")
    user_props["school"] = ou1
    user_props["email"] = user_props.pop("mailPrimaryAddress")
    del user_props["description"]
    del user_props["e-mail"]

    user_obj = User(**user_props)
    with pytest.raises(TypeError, match=r"is not an object of a 'User' subclass"):
        new_user_obj = await convert_to_staff(user_obj, udm)
        schedule_delete_user_dn(new_user_obj.dn)

    user_obj = ExamStudent(**user_props)
    with pytest.raises(TypeError, match=r"from or to 'ExamStudent' is not allowed"):
        new_user_obj = await convert_to_teacher(user_obj, udm)
        schedule_delete_user_dn(new_user_obj.dn)

    # illegal convert target
    dn, attr = await new_udm_user(ou1, "student")
    async with UDM(**udm_kwargs) as udm:
        user_obj = await Student.from_dn(dn, attr["school"][0], udm)

        with pytest.raises(TypeError, match=r"is not a subclass of 'User'"):
            new_user_obj = await UserTypeConverter.convert(user_obj, User, udm)
            schedule_delete_user_dn(new_user_obj.dn)

        with pytest.raises(TypeError, match=r"from or to 'ExamStudent' is not allowed"):
            new_user_obj = await UserTypeConverter.convert(user_obj, ExamStudent, udm)
            schedule_delete_user_dn(new_user_obj.dn)

        with pytest.raises(TypeError, match=r"is not a subclass of 'User'"):
            new_user_obj = await UserTypeConverter.convert(user_obj, SchoolClass, udm)
            schedule_delete_user_dn(new_user_obj.dn)

        # no school_class for student target
        dn, attr = await new_udm_user(ou1, "staff")
        user_obj = await Staff.from_dn(dn, attr["school"][0], udm)
        with pytest.raises(TypeError, match=r"requires at least one school class per school"):
            new_user_obj = await UserTypeConverter.convert(user_obj, Student, udm)
            schedule_delete_user_dn(new_user_obj.dn)

        # not enough school_classes for student target
        dn, attr = await new_udm_user(ou1, "teacher")
        user_obj = await Teacher.from_dn(dn, ou1, udm)
        user_obj.schools.append(ou2)
        with pytest.raises(TypeError, match=r"requires at least one school class per school"):
            new_user_obj = await UserTypeConverter.convert(user_obj, Student, udm)
            schedule_delete_user_dn(new_user_obj.dn)


@pytest.mark.asyncio
@pytest.mark.parametrize("role", USER_ROLES, ids=role_id)
async def test_modify_add_school(create_multiple_ous, new_udm_user, udm_kwargs, role: Role):
    """User(ou1, [ou1]) -> User(ou1, [ou1, ou2])"""
    ou1, ou2 = await create_multiple_ous(2)
    dn, attr = await new_udm_user(ou1, role.name)
    async with UDM(**udm_kwargs) as udm:
        user: User = await role.klass.from_dn(dn, ou1, udm)
        assert user.schools == [ou1]
        user.schools = [ou1, ou2]
        success = await user.modify(udm)
        assert success is True
        assert user.school == ou1
        user = await role.klass.from_dn(dn, ou1, udm)
    attr.update(
        {
            "school": [ou1, ou2],
            "ucsschoolRole": make_ucsschool_roles(role.klass, [ou1, ou2]),
        }
    )
    compare_attr_and_lib_user(attr, user)


@pytest.mark.asyncio
@pytest.mark.parametrize("role", USER_ROLES, ids=role_id)
async def test_modify_remove_primary_school(create_multiple_ous, new_udm_user, udm_kwargs, role: Role):
    """User(ou1, [ou1, ou2]) -> User(ou2, [ou2])"""
    ou1, ou2 = await create_multiple_ous(2)
    dn, attr = await new_udm_user(
        ou1,
        role.name,
        schools=[ou1, ou2],
        ucsschool_roles=make_ucsschool_roles(role.klass, [ou1, ou2]),
    )
    async with UDM(**udm_kwargs) as udm:
        user: User = await role.klass.from_dn(dn, ou1, udm)
        assert user.school == ou1
        assert set(user.schools) == {ou1, ou2}
        user.school = ou2
        user.schools = [ou2]
        user.school_classes.pop(ou1, None)
        success = await user.change_school(ou2, udm)
        assert success is True
        assert user.school == ou2
        user = await role.klass.from_dn(user.dn, user.school, udm)
    attr.update({"school": [ou2], "ucsschoolRole": make_ucsschool_roles(role.klass, [ou2])})
    compare_attr_and_lib_user(attr, user)


@pytest.mark.asyncio
@pytest.mark.parametrize("role", USER_ROLES, ids=role_id)
async def test_modify_remove_additional_school(
    create_multiple_ous, new_udm_user, udm_kwargs, role: Role
):
    """User(ou1, [ou1, ou2]) -> User(ou1, [ou1])"""
    ou1, ou2 = await create_multiple_ous(2)
    dn, attr = await new_udm_user(
        ou1,
        role.name,
        schools=[ou1, ou2],
        ucsschool_roles=make_ucsschool_roles(role.klass, [ou1, ou2]),
    )
    async with UDM(**udm_kwargs) as udm:
        user: User = await role.klass.from_dn(dn, ou1, udm)
        assert user.school == ou1
        assert set(user.schools) == {ou1, ou2}
        user.schools = [ou1]
        user.school_classes.pop(ou2, None)
        success = await user.modify(udm)
        assert success is True
        user = await role.klass.from_dn(user.dn, user.school, udm)
    attr.update({"school": [ou1], "ucsschoolRole": make_ucsschool_roles(role.klass, [ou1])})
    compare_attr_and_lib_user(attr, user)


@pytest.mark.asyncio
@pytest.mark.parametrize("role", USER_ROLES, ids=role_id)
async def test_modify_add_and_remove_primary_school(
    create_multiple_ous, new_udm_user, udm_kwargs, role: Role
):
    """User(ou1, [ou1, ou2]) -> User(ou2, [ou2, ou3])"""
    ou1, ou2, ou3 = await create_multiple_ous(3)
    dn, attr = await new_udm_user(
        ou1,
        role.name,
        schools=[ou1, ou2],
        ucsschool_roles=make_ucsschool_roles(role.klass, [ou1, ou2]),
        workgroups={},
    )
    async with UDM(**udm_kwargs) as udm:
        user: User = await role.klass.from_dn(dn, ou1, udm)
        assert user.school == ou1
        assert set(user.schools) == {ou1, ou2}
        user.school = ou2
        user.schools = [ou2, ou3]
        user.school_classes.pop(ou1, None)
        success = await user.change_school(ou2, udm)
        assert success is True
        assert set(user.schools) == {ou2, ou3}
        # a dedicated modify() is required for actually adding ou3
        success = await user.modify(udm)
        assert success is True
        user = await role.klass.from_dn(user.dn, user.school, udm)
    attr.update(
        {
            "school": [ou2, ou3],
            "ucsschoolRole": make_ucsschool_roles(role.klass, [ou2, ou3]),
        }
    )
    compare_attr_and_lib_user(attr, user)


@pytest.mark.asyncio
@pytest.mark.parametrize("role", USER_ROLES, ids=role_id)
async def test_modify_add_and_remove_additional_school(
    create_multiple_ous, new_udm_user, udm_kwargs, role: Role
):
    """User(ou1, [ou1, ou2]) -> User(ou1, [ou1, ou3])"""
    ou1, ou2, ou3 = await create_multiple_ous(3)
    dn, attr = await new_udm_user(
        ou1,
        role.name,
        schools=[ou1, ou2],
        ucsschool_roles=make_ucsschool_roles(role.klass, [ou1, ou2]),
    )
    async with UDM(**udm_kwargs) as udm:
        user: User = await role.klass.from_dn(dn, ou1, udm)
        assert user.school == ou1
        assert set(user.schools) == {ou1, ou2}
        user.schools = [ou1, ou3]
        success = await user.modify(udm)
        assert success is True
        user = await role.klass.from_dn(user.dn, user.school, udm)
    attr.update(
        {
            "school": [ou1, ou3],
            "ucsschoolRole": make_ucsschool_roles(role.klass, [ou1, ou3]),
        }
    )
    compare_attr_and_lib_user(attr, user)


@pytest.mark.asyncio
@pytest.mark.parametrize("role", USER_ROLES, ids=role_id)
async def test_move(create_multiple_ous, new_udm_user, role: Role, udm_kwargs):
    ou1, ou2 = await create_multiple_ous(2)
    dn, attr = await new_udm_user(ou1, role.name)
    assert attr["school"][0] == ou1
    async with UDM(**udm_kwargs) as udm:
        user = await role.klass.from_dn(dn, ou1, udm)
        user.school = ou2
        user.schools = [ou2]
        success = await user.change_school(ou2, udm)
        assert success is True
        users = await role.klass.get_all(udm, ou2, f"uid={user.name}")
    assert len(users) == 1
    user = users[0]
    assert user.school == ou2
    assert user.schools == [ou2]
    assert f"ou={ou1}" not in user.dn
    assert f"ou={ou2}" in user.dn


@pytest.mark.asyncio
@pytest.mark.parametrize("role", USER_ROLES, ids=role_id)
@pytest.mark.parametrize(
    "extra_role,allowed",
    [
        ("my:funny:role", True),
        ("not:funny", False),
        ("123", False),
        ("my:school:existing_school", False),
    ],
)
async def test_move_keep_arbitrary_extra_roles(
    create_multiple_ous, new_udm_user, role: Role, udm_kwargs, extra_role, allowed
):
    """
    00_ucsschool_roles
    """
    ou1, ou2 = await create_multiple_ous(2)
    extra_role = extra_role.replace("existing_school", ou2)
    dn, attr = await new_udm_user(ou1, role.name, ucsschool_roles=[extra_role])
    assert attr["school"][0] == ou1
    async with UDM(**udm_kwargs) as udm:
        user = await role.klass.from_dn(dn, ou1, udm)
        assert extra_role in user.ucsschool_roles
        user.school = ou2
        user.schools = [ou2]
        success = await user.change_school(ou2, udm)
        assert success
        users = await role.klass.get_all(udm, ou2, f"uid={user.name}")
    assert len(users) == 1
    user = users[0]
    if allowed:
        assert extra_role in user.ucsschool_roles
    else:
        assert extra_role not in user.ucsschool_roles


@pytest.mark.asyncio
@pytest.mark.parametrize("role", USER_ROLES, ids=role_id)
async def test_remove(create_ou_using_python, udm_kwargs, new_udm_user, role: Role):
    ou = await create_ou_using_python()
    dn, attr = await new_udm_user(ou, role.name)
    async with UDM(**udm_kwargs) as udm:
        user = await role.klass.from_dn(dn, ou, udm)
        assert await user.exists(udm)
        success = await user.remove(udm)
        assert success is True
        assert not await user.exists(udm)


unixhomes = {
    "student": "schueler",
    "teacher": "lehrer",
    "staff": "mitarbeiter",
    "teacher_and_staff": "lehrer",
    "school_admin": "admins",  # TODO FIXME this has never been defined yet!
}


@pytest.mark.asyncio
@pytest.mark.parametrize("role", USER_ROLES, ids=role_id)
async def test_unixhome(
    create_ou_using_python,
    new_school_class_using_udm,
    udm_users_user_props,
    udm_kwargs,
    role: Role,
):
    school = await create_ou_using_python()
    async with UDM(**udm_kwargs) as udm:
        user_props = await udm_users_user_props(school)
        user_props.update(
            {
                "name": user_props["username"],
                "email": user_props["mailPrimaryAddress"],
                "school": school,
                "birthday": str(user_props["birthday"]),
                "expiration_date": str(user_props["userexpiry"]),
            }
        )
        del user_props["e-mail"]
        del user_props["userexpiry"]
        if role.klass != Staff:
            cls_dn1, cls_attr1 = await new_school_class_using_udm(school=school)
            cls_dn2, cls_attr2 = await new_school_class_using_udm(school=school)
            user_props["school_classes"] = {
                school: [
                    f"{school}-{cls_attr1['name']}",
                    f"{school}-{cls_attr2['name']}",
                ]
            }
        user = role.klass(**user_props)
        success = await user.create(udm)
        assert success is True
        user = await role.klass.from_dn(user.dn, school, udm)
        udm_user = await user.get_udm_object(udm)
        assert f"/home/{school}/{unixhomes[role.name]}/{user.name}" == udm_user.props.unixhome


@pytest.mark.asyncio
async def test_remove_from_groups_of_school_admin_user(
    create_multiple_ous,
    ldap_base,
    new_school_class_using_udm,
    new_udm_user,
    new_workgroup_using_udm,
    udm_kwargs,
):
    # Test scenario:
    # A user who is a teacher and an admin in two schools.
    # When the user is removed from the second school,
    # both the admin and teacher groups will be completely removed for the second school,
    # leaving the first school as-is

    school1_name, school2_name = await create_multiple_ous(2)
    school_names = [school1_name, school2_name]

    school1 = SchoolSearchBase([school1_name])
    school1_domain_users = f"cn=Domain Users {school1_name},cn=groups,ou={school1_name},{ldap_base}"
    school1_teachers = school1.teachers_group
    school1_admins = school1.admins_group

    school2 = SchoolSearchBase([school2_name])
    school2_domain_users = f"cn=Domain Users {school2_name},cn=groups,ou={school2_name},{ldap_base}"
    school2_teachers = school2.teachers_group
    school2_admins = school2.admins_group

    class1_dn, class1_name = await new_school_class_using_udm(school=school1_name)
    class2_dn, class2_name = await new_school_class_using_udm(school=school2_name)
    wg1_dn, wg1_name = await new_workgroup_using_udm(school=school1_name)
    wg2_dn, wg2_name = await new_workgroup_using_udm(school=school2_name)

    user_dn, user_name = await new_udm_user(
        school=school1_name,
        role="teacher",
        schools=school_names,
        school_classes={
            school1_name: [class1_name],
            school2_name: [class2_name],
        },
        workgroups={
            school1_name: [wg1_name],
            school2_name: [wg2_name],
        },
    )
    async with UDM(**udm_kwargs) as udm:
        user_udm = await udm.get("users/user").get(user_dn)
        user_udm.options["ucsschoolAdministrator"] = True
        user_udm.props.groups.extend(
            [
                school2_domain_users,
                school2_teachers,
                school1_admins,
                school2_admins,
                class1_dn,
                class2_dn,
                wg1_dn,
                wg2_dn,
            ],
        )
        await user_udm.save()

        # Verification of pre-test state
        expected_pre_test_groups = {
            school1_domain_users,
            school2_domain_users,
            school1_teachers,
            school2_teachers,
            school1_admins,
            school2_admins,
            class1_dn,
            class2_dn,
            wg1_dn,
            wg2_dn,
        }
        user_udm_saved = await udm.get("users/user").get(user_dn)
        assert set(user_udm_saved.props.groups) == expected_pre_test_groups

        # Testing
        user = await User.from_dn(user_dn, school1_name, udm)
        await user.remove_from_groups_of_school(school2_name, udm)

        expected_post_test_groups = {
            school1_domain_users,
            school1_teachers,
            school1_admins,
            class1_dn,
            wg1_dn,
        }
        user_udm_post_test = await udm.get("users/user").get(user_dn)
        assert set(user_udm_post_test.props.groups) == expected_post_test_groups


@pytest.mark.asyncio
async def test_add_and_remove_from_groups_of_school_on_school_change_with_modify(
    create_multiple_ous,
    ldap_base,
    new_school_class_using_udm,
    new_udm_user,
    new_workgroup_using_udm,
    udm_kwargs,
):
    # Test scenario:
    # A user who is a teacher and an admin in two schools.
    # When the user is removed from the second school,
    # both the admin and teacher groups will be completely removed for the second school,
    # leaving the first school as-is
    # Aditionally, the user is added to a thrid schools,
    # and the expected groups should be added for it automatically (Domain users, lehrer, ...)

    school1_name, school2_name, school3_name = await create_multiple_ous(3)
    school_names = [school1_name, school2_name]

    school1 = SchoolSearchBase([school1_name])
    school1_domain_users = f"cn=Domain Users {school1_name},cn=groups,ou={school1_name},{ldap_base}"
    school1_teachers = school1.teachers_group
    school1_admins = school1.admins_group

    school2 = SchoolSearchBase([school2_name])
    school2_domain_users = f"cn=Domain Users {school2_name},cn=groups,ou={school2_name},{ldap_base}"
    school2_teachers = school2.teachers_group
    school2_admins = school2.admins_group

    school3 = SchoolSearchBase([school3_name])
    school3_domain_users = f"cn=Domain Users {school3_name},cn=groups,ou={school3_name},{ldap_base}"
    school3_teachers = school3.teachers_group

    class1_dn, class1_attr = await new_school_class_using_udm(school=school1_name)
    class2_dn, class2_attr = await new_school_class_using_udm(school=school2_name)
    class3_dn, class3_attr = await new_school_class_using_udm(school=school3_name)
    wg1_dn, wg1_attr = await new_workgroup_using_udm(school=school1_name)
    wg2_dn, wg2_attr = await new_workgroup_using_udm(school=school2_name)
    wg3_dn, wg3_attr = await new_workgroup_using_udm(school=school3_name)

    user_dn, user_name = await new_udm_user(
        school=school1_name,
        role="teacher",
        schools=school_names,
        school_classes={
            school1_name: [class1_attr],
            school2_name: [class2_attr],
        },
        workgroups={
            school1_name: [wg1_attr],
            school2_name: [wg2_attr],
        },
    )
    async with UDM(**udm_kwargs) as udm:
        user_udm = await udm.get("users/user").get(user_dn)
        user_udm.options["ucsschoolAdministrator"] = True
        user_udm.props.groups.extend(
            [
                school1_admins,
                school2_admins,
            ],
        )
        await user_udm.save()

        # Verification of pre-test state
        expected_pre_test_groups = {
            school1_domain_users,
            school2_domain_users,
            school1_teachers,
            school2_teachers,
            school1_admins,
            school2_admins,
            class1_dn,
            class2_dn,
            wg1_dn,
            wg2_dn,
        }
        user_udm_saved = await udm.get("users/user").get(user_dn)
        assert set(user_udm_saved.props.groups) == expected_pre_test_groups

        # Testing
        user = await User.from_dn(user_dn, school1_name, udm)
        user.schools = [school1_name, school3_name]
        del user.school_classes[school2_name]
        del user.workgroups[school2_name]
        user.school_classes[school3_name] = [class3_attr["name"]]
        user.workgroups[school3_name] = [wg3_attr["name"]]
        await user.modify(udm)

        expected_post_test_groups = {
            school1_domain_users,
            school1_teachers,
            school1_admins,
            class1_dn,
            wg1_dn,
            school3_domain_users,
            school3_teachers,
            class3_dn,
            wg3_dn,
        }
        user_udm_post_test = await udm.get("users/user").get(user_dn)
        assert set(user_udm_post_test.props.groups) == expected_post_test_groups


@pytest.mark.asyncio
async def test_is_student(create_ou_using_python, new_udm_user, udm_kwargs):
    ou = await create_ou_using_python()
    dn, _ = await new_udm_user(ou, "student")

    async with UDM(**udm_kwargs) as udm:
        user = await User.from_dn(dn, ou, udm)
        is_student = await user.is_student(udm)
        assert is_student


@pytest.mark.asyncio
@pytest.mark.parametrize("role", ("staff", "teacher", "teacher_and_staff", "school_admin"))
async def test_is_student_false(create_ou_using_python, new_udm_user, udm_kwargs, role: str):
    ou = await create_ou_using_python()
    dn, _ = await new_udm_user(ou, role)

    async with UDM(**udm_kwargs) as udm:
        user = await User.from_dn(dn, ou, udm)
        is_student = await user.is_student(udm)
        assert not is_student


@pytest.mark.asyncio
async def test_is_student_with_fallback(create_ou_using_python, new_udm_user, udm_kwargs):
    ou = await create_ou_using_python()
    dn, _ = await new_udm_user(ou, "student")

    async with UDM(**udm_kwargs) as udm:
        user = await User.from_dn(dn, ou, udm)
        # Let's artificially create a legacy user
        user_udm = await user.get_udm_object(udm)
        user_udm.options["ucsschoolStudent"] = None
        await user_udm.save()

        is_student = await user.is_student(udm)
        assert is_student


@pytest.mark.asyncio
async def test_is_student_with_object_does_not_exist(udm_kwargs):
    async with UDM(**udm_kwargs) as udm:
        user = User()
        try:
            await user.is_student(udm)
            assert False, "is_student should throw error when no udm object"
        except noObject:
            assert True


@pytest.mark.asyncio
async def test_is_exam_student(create_ou_using_python, new_udm_user, udm_kwargs):
    ou = await create_ou_using_python()
    dn, _ = await new_udm_user(ou, "student")

    async with UDM(**udm_kwargs) as udm:
        user = await User.from_dn(dn, ou, udm)
        # Let's artifically create an exam user,
        # because the process of creating a correct ExamStudent
        # isn't ported from ucsschool.
        user_udm = await user.get_udm_object(udm)
        user_udm.options["ucsschoolExam"] = True
        user_udm.save()

        is_exam_student = await user.is_exam_student(udm)
        assert is_exam_student


@pytest.mark.asyncio
@pytest.mark.parametrize("role", ("student", "staff", "teacher", "teacher_and_staff", "school_admin"))
async def test_is_exam_student_false(create_ou_using_python, new_udm_user, udm_kwargs, role: str):
    ou = await create_ou_using_python()
    dn, _ = await new_udm_user(ou, role)

    async with UDM(**udm_kwargs) as udm:
        user = await User.from_dn(dn, ou, udm)
        is_exam_student = await user.is_exam_student(udm)
        assert not is_exam_student


@pytest.mark.asyncio
async def test_is_exam_student_with_object_does_not_exist(udm_kwargs):
    async with UDM(**udm_kwargs) as udm:
        user = User()
        try:
            await user.is_exam_student(udm)
            assert False, "is_exam_student should throw error when no UDM object"
        except noObject:
            assert True


@pytest.mark.asyncio
async def test_is_teacher(create_ou_using_python, new_udm_user, udm_kwargs):
    ou = await create_ou_using_python()
    dn, _ = await new_udm_user(ou, "teacher")

    async with UDM(**udm_kwargs) as udm:
        user = await User.from_dn(dn, ou, udm)
        is_teacher = await user.is_teacher(udm)
        assert is_teacher


@pytest.mark.asyncio
async def test_is_teacher_when_teacher_and_staff(create_ou_using_python, new_udm_user, udm_kwargs):
    ou = await create_ou_using_python()
    dn, _ = await new_udm_user(ou, "teacher_and_staff")

    async with UDM(**udm_kwargs) as udm:
        user = await User.from_dn(dn, ou, udm)
        is_teacher = await user.is_teacher(udm)
        assert is_teacher


@pytest.mark.asyncio
@pytest.mark.parametrize("role", ("student", "staff", "school_admin"))
async def test_is_teacher_false(create_ou_using_python, new_udm_user, udm_kwargs, role: str):
    ou = await create_ou_using_python()
    dn, _ = await new_udm_user(ou, role)

    async with UDM(**udm_kwargs) as udm:
        user = await User.from_dn(dn, ou, udm)
        is_teacher = await user.is_teacher(udm)
        assert not is_teacher


@pytest.mark.asyncio
async def test_is_teacher_with_fallback(create_ou_using_python, new_udm_user, udm_kwargs):
    ou = await create_ou_using_python()
    dn, _ = await new_udm_user(ou, "teacher")

    async with UDM(**udm_kwargs) as udm:
        user = await User.from_dn(dn, ou, udm)
        # Let's artificially create a legacy user
        user_udm = await user.get_udm_object(udm)
        user_udm.options["ucsschoolTeacher"] = None
        user_udm.save()

        is_teacher = await user.is_teacher(udm)
        assert is_teacher


@pytest.mark.asyncio
async def test_is_teacher_with_object_does_not_exist(udm_kwargs):
    async with UDM(**udm_kwargs) as udm:
        user = User()
        try:
            await user.is_teacher(udm)
            assert False, "is_teacher should error when no UDM object"
        except noObject:
            assert True


@pytest.mark.asyncio
async def test_is_staff(create_ou_using_python, new_udm_user, udm_kwargs):
    ou = await create_ou_using_python()
    dn, _ = await new_udm_user(ou, "staff")

    async with UDM(**udm_kwargs) as udm:
        user = await User.from_dn(dn, ou, udm)
        is_staff = await user.is_staff(udm)
        assert is_staff


@pytest.mark.asyncio
async def test_is_staff_when_teacher_and_staff(create_ou_using_python, new_udm_user, udm_kwargs):
    ou = await create_ou_using_python()
    dn, _ = await new_udm_user(ou, "teacher_and_staff")

    async with UDM(**udm_kwargs) as udm:
        user = await User.from_dn(dn, ou, udm)
        is_staff = await user.is_staff(udm)
        assert is_staff


@pytest.mark.asyncio
@pytest.mark.parametrize("role", ("student", "teacher", "school_admin"))
async def test_is_staff_false(create_ou_using_python, new_udm_user, udm_kwargs, role: str):
    ou = await create_ou_using_python()
    dn, _ = await new_udm_user(ou, role)

    async with UDM(**udm_kwargs) as udm:
        user = await User.from_dn(dn, ou, udm)
        is_staff = await user.is_staff(udm)
        assert not is_staff


@pytest.mark.asyncio
async def test_is_staff_with_fallback(create_ou_using_python, new_udm_user, udm_kwargs):
    ou = await create_ou_using_python()
    dn, _ = await new_udm_user(ou, "staff")

    async with UDM(**udm_kwargs) as udm:
        user = await User.from_dn(dn, ou, udm)
        # Let's artificially create a legacy user
        user_udm = await user.get_udm_object(udm)
        user_udm.options["ucsschoolStaff"] = None
        user_udm.save()

        is_staff = await user.is_staff(udm)
        assert is_staff


@pytest.mark.asyncio
async def test_is_staff_with_object_does_not_exist(udm_kwargs):
    async with UDM(**udm_kwargs) as udm:
        user = User()
        try:
            await user.is_staff(udm)
            assert False, "is_staff should throw an error when no UDM object"
        except noObject:
            assert True


@pytest.mark.asyncio
async def test_is_administrator(create_ou_using_python, new_udm_admin_user, udm_kwargs):
    ou = await create_ou_using_python()
    dn, _ = await new_udm_admin_user(ou)

    async with UDM(**udm_kwargs) as udm:
        user = await User.from_dn(dn, ou, udm)
        is_administrator = await user.is_administrator(udm)
        assert is_administrator


@pytest.mark.asyncio
@pytest.mark.parametrize("role", ("staff", "student", "teacher", "teacher_and_staff"))
async def test_is_administrator_false(create_ou_using_python, new_udm_user, udm_kwargs, role: str):
    ou = await create_ou_using_python()
    dn, _ = await new_udm_user(ou, role)

    async with UDM(**udm_kwargs) as udm:
        user = await User.from_dn(dn, ou, udm)
        is_administrator = await user.is_administrator(udm)
        assert not is_administrator


@pytest.mark.asyncio
async def test_is_administrator_with_fallback(create_ou_using_python, new_udm_admin_user, udm_kwargs):
    ou = await create_ou_using_python()
    dn, _ = await new_udm_admin_user(ou)

    async with UDM(**udm_kwargs) as udm:
        user = await User.from_dn(dn, ou, udm)
        # Let's artificially create a legacy user
        user_udm = await user.get_udm_object(udm)
        user_udm.options["ucsschoolAdministrator"] = None
        user_udm.save()

        is_administrator = await user.is_administrator(udm)
        assert is_administrator


@pytest.mark.asyncio
async def test_is_administrator_with_object_does_not_exist(udm_kwargs):
    async with UDM(**udm_kwargs) as udm:
        user = User()
        try:
            await user.is_administrator(udm)
            assert False, "is_administrator should throw error if no UDM object"
        except noObject:
            assert True
