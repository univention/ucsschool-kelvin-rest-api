import uuid

import pytest
from conftest import make_group, make_role, make_school, make_user
from kelvin_connector.models import (
    DeletedObjectProperties,
    DeletePayload,
    GroupCreateEvent,
    GroupDeleteEvent,
    GroupModifyEvent,
    GroupPayload,
    GroupProperties,
    HostGroupCreateEvent,
    HostGroupDeleteEvent,
    HostGroupModifyEvent,
    HostGroupPayload,
    HostGroupProperties,
    SchoolCreateEvent,
    SchoolDeleteEvent,
    SchoolModifyEvent,
    SchoolPayload,
    SchoolProperties,
    UcsschoolRole,
    UserCreateEvent,
    UserDeleteEvent,
    UserModifyEvent,
    UserPayload,
    UserProperties,
)
from kelvin_connector.sync import (
    DEFAULT_NUBUS_SOURCE_UID,
    SynchronizationException,
    _school_ou_from_dn,
    _udm_properties,
)
from pydantic import UUID4
from ucsschool_objects import ObjectType
from ucsschool_objects.core.domain.errors import NotFound
from ucsschool_objects.core.domain.models import (
    UNLOADED,
    Group,
    SchoolMembership,
    get_properties,
    is_loaded,
)

_TS = "2024-01-01T00:00:00"


def _assert_fully_loaded(created):
    """Objects handed to create() must be fully loaded.

    The mock storage hides the ORM mappers, which raise on unloaded fields;
    this assertion catches constructor calls that omit a field.
    """
    for field_name in get_properties(type(created)):
        if field_name == "public_id":
            continue
        assert is_loaded(created, field_name), f"{type(created).__name__}.{field_name} is not loaded"


# ── Event constructors ────────────────────────────────────────────────────────


def _user_create_event(uid, extra_props=None, dn="uid=testuser,cn=users,dc=test"):
    id = "testuser"
    position = "cn=users,dc=test"
    props = UserProperties.parse_obj(
        dict(
            univentionObjectIdentifier=UUID4(str(uid)),
            username="testuser",
            firstname="Test",
            lastname="User",
            disabled=False,
            school=["testschool"],
            ucsschoolRole=[UcsschoolRole(role="teacher", context="school", school="testschool")],
            ucsschoolRecordUID="testuser",
            ucsschoolSourceUID="src",
            groups=[],
            ucsschoolLegalWard=[],
            ucsschoolLegalGuardian=[],
            mailPrimaryAddress="testuser@example.com",
        )
    )
    if extra_props:
        props = type(props)(**{**props.dict(), **extra_props})
    return UserCreateEvent(
        timestamp=_TS,
        sequence_number=1,
        new=UserPayload(dn=dn, id=id, objectType="users/user", position=position, properties=props),
    )


def _user_modify_event(uid, extra_props=None, dn="uid=testuser,cn=users,dc=test"):
    id = "testuser"
    position = "cn=users,dc=test"
    objectType = "users/user"
    props = UserProperties.parse_obj(
        dict(
            univentionObjectIdentifier=UUID4(str(uid)),
            username="testuser",
            firstname="Test",
            lastname="User",
            disabled=False,
            school=["testschool"],
            ucsschoolRole=[UcsschoolRole(role="teacher", context="school", school="testschool")],
            ucsschoolRecordUID="testuser",
            ucsschoolSourceUID="src",
            groups=[],
            ucsschoolLegalWard=[],
            ucsschoolLegalGuardian=[],
            mailPrimaryAddress="testuser@example.com",
        )
    )
    if extra_props:
        props = type(props)(**{**props.dict(), **extra_props})
    return UserModifyEvent(
        timestamp=_TS,
        sequence_number=1,
        new=UserPayload(dn=dn, id=id, objectType=objectType, position=position, properties=props),
    )


def _user_delete_event(uid):
    return UserDeleteEvent(
        timestamp=_TS,
        sequence_number=1,
        old=DeletePayload(
            dn="uid=testuser,cn=users,dc=test",
            id="testuser",
            objectType="users/user",
            position="cn=users,dc=test",
            properties=DeletedObjectProperties(
                univentionObjectIdentifier=UUID4(str(uid)), username="testuser"
            ),
        ),
    )


def _group_create_event(uid, name="testschool-group", extra_props=None):
    dn = f"cn={name},cn=klassen,dc=test"
    id = name
    position = "cn=klassen,dc=test"
    objectType = "groups/group"
    props = GroupProperties(
        univentionObjectIdentifier=UUID4(str(uid)),
        name=name,
        ucsschoolRole=[UcsschoolRole(role="school_class", context="school", school="testschool")],
        allowedEmailUsers=[],
        allowedEmailGroups=[],
        users=[],
        mailAddress=None,
        guardianMemberRoles=[],
    )
    if extra_props:
        props = type(props)(**{**props.dict(), **extra_props})
    return GroupCreateEvent(
        timestamp=_TS,
        sequence_number=1,
        new=GroupPayload(dn=dn, id=id, objectType=objectType, position=position, properties=props),
    )


def _group_modify_event(uid, name="testschool-group", extra_props=None):
    dn = f"cn={name},cn=klassen,dc=test"
    id = name
    position = "cn=klassen,dc=test"
    objectType = "groups/group"
    props = GroupProperties(
        univentionObjectIdentifier=UUID4(str(uid)),
        name=name,
        ucsschoolRole=[UcsschoolRole(role="school_class", context="school", school="testschool")],
        allowedEmailUsers=[],
        allowedEmailGroups=[],
        users=[],
        mailAddress=None,
        guardianMemberRoles=[],
    )
    if extra_props:
        props = type(props)(**{**props.dict(), **extra_props})
    return GroupModifyEvent(
        timestamp=_TS,
        sequence_number=1,
        new=GroupPayload(dn=dn, id=id, objectType=objectType, position=position, properties=props),
    )


def _group_delete_event(uid, name="testschool-group"):
    dn = f"cn={name},cn=klassen,dc=test"
    props = DeletedObjectProperties(
        univentionObjectIdentifier=UUID4(str(uid)),
        name=name,
    )
    return GroupDeleteEvent(
        timestamp=_TS,
        sequence_number=1,
        old=DeletePayload(
            dn=dn, id=name, objectType="groups/group", position="cn=klassen,dc=test", properties=props
        ),
    )


def _school_create_event(uid, name="testschool", extra_props=None):
    dn = f"ou={name},dc=test"
    props = SchoolProperties(
        univentionObjectIdentifier=UUID4(str(uid)),
        name=name,
        displayName=f"{name} Display",
    )
    if extra_props:
        props = type(props)(**{**props.dict(), **extra_props})
    return SchoolCreateEvent(
        timestamp=_TS,
        sequence_number=1,
        new=SchoolPayload(
            dn=dn, id=name, objectType="container/ou", position="dc=test", properties=props
        ),
    )


def _school_modify_event(uid, name="testschool", extra_props=None):
    dn = f"ou={name},dc=test"
    props = SchoolProperties(
        univentionObjectIdentifier=UUID4(str(uid)),
        name=name,
        displayName=f"{name} Display",
    )
    if extra_props:
        props = type(props)(**{**props.dict(), **extra_props})
    return SchoolModifyEvent(
        timestamp=_TS,
        sequence_number=1,
        new=SchoolPayload(
            dn=dn, id=name, objectType="container/ou", position="dc=test", properties=props
        ),
    )


def _school_delete_event(uid, name="testschool"):
    dn = f"ou={name},dc=test"
    props = DeletedObjectProperties(
        univentionObjectIdentifier=UUID4(str(uid)),
        name=name,
    )
    return SchoolDeleteEvent(
        timestamp=_TS,
        sequence_number=1,
        old=DeletePayload(
            dn=dn, id=name, objectType="container/ou", position="dc=test", properties=props
        ),
    )


def _host_group_create_event(uid, name="OUdemoschool-DC-Edukativnetz", hosts=None):
    dn = f"cn={name},cn=ucsschool,cn=groups,dc=test"
    props = HostGroupProperties(
        univentionObjectIdentifier=UUID4(str(uid)),
        name=name,
        description="DC host group",
        hosts=hosts or [],
    )
    return HostGroupCreateEvent(
        timestamp=_TS,
        sequence_number=1,
        new=HostGroupPayload(
            dn=dn,
            id=name,
            objectType="groups/group",
            position="cn=ucsschool,cn=groups,dc=test",
            properties=props,
        ),
    )


def _host_group_modify_event(uid, name="OUdemoschool-DC-Verwaltungsnetz", hosts=None):
    dn = f"cn={name},cn=ucsschool,cn=groups,dc=test"
    props = HostGroupProperties(
        univentionObjectIdentifier=UUID4(str(uid)),
        name=name,
        description="DC host group",
        hosts=hosts or [],
    )
    return HostGroupModifyEvent(
        timestamp=_TS,
        sequence_number=1,
        new=HostGroupPayload(
            dn=dn,
            id=name,
            objectType="groups/group",
            position="cn=ucsschool,cn=groups,dc=test",
            properties=props,
        ),
    )


def _host_group_delete_event(uid, name="OUdemoschool-DC-Edukativnetz"):
    dn = f"cn={name},cn=ucsschool,cn=groups,dc=test"
    props = HostGroupProperties(
        univentionObjectIdentifier=UUID4(str(uid)),
        name=name,
        description="DC host group",
        hosts=[],
    )
    return HostGroupDeleteEvent(
        timestamp=_TS,
        sequence_number=1,
        old=HostGroupPayload(
            dn=dn,
            id=name,
            objectType="groups/group",
            position="cn=ucsschool,cn=groups,dc=test",
            properties=props,
        ),
    )


# ── Helper method unit tests ──────────────────────────────────────────────────


async def test_dns_to_known_ids_all_found(manager, mock_mapper):
    uid1, uid2 = uuid.uuid4(), uuid.uuid4()
    mock_mapper.dns_to_public_ids.return_value = {"dn1": uid1, "dn2": uid2}

    result = await manager._dns_to_known_ids(mock_mapper, ObjectType.USER, ["dn1", "dn2"], "Test")

    assert set(result) == {str(uid1), str(uid2)}


async def test_dns_to_known_ids_skips_unknown(manager, mock_mapper):
    uid1 = uuid.uuid4()
    mock_mapper.dns_to_public_ids.return_value = {"dn1": uid1}

    result = await manager._dns_to_known_ids(
        mock_mapper, ObjectType.USER, ["dn1", "dn2_unknown"], "Test"
    )

    assert result == [str(uid1)]


@pytest.mark.parametrize(
    "method,repo",
    [
        ("_fetch_users_by_dns", "users"),
        ("_fetch_groups_by_dns", "groups"),
    ],
)
async def test_fetch_by_dns_returns_empty_when_no_known_ids(
    manager, mock_mapper, mock_storage, method, repo
):
    mock_mapper.dns_to_public_ids.return_value = {}
    result = await getattr(manager, method)(["some_dn"], "Label", mock_mapper, mock_storage)
    assert result == set()
    getattr(mock_storage, repo).search.assert_not_called()


async def test_fetch_users_by_dns_searches_by_known_ids(manager, mock_mapper, mock_storage):
    uid = uuid.uuid4()
    user = make_user(uid=uid)
    mock_mapper.dns_to_public_ids.return_value = {"dn": uid}
    mock_storage.users.search.return_value = [user]

    result = await manager._fetch_users_by_dns(["dn"], "Label", mock_mapper, mock_storage)
    assert result == {user}


async def test_fetch_groups_by_dns_searches_by_known_ids(manager, mock_mapper, mock_storage):
    uid = uuid.uuid4()
    school = make_school()
    group = make_group("testschool-group", school, uid=uid)
    mock_mapper.dns_to_public_ids.return_value = {"dn": uid}
    mock_storage.groups.search.return_value = [group]

    result = await manager._fetch_groups_by_dns(["dn"], "Label", mock_mapper, mock_storage)
    assert result == {group}


def test_guardian_role_validator_accepts_pre_parsed_object():
    from kelvin_connector.models import GuardianRole

    guardian = GuardianRole(app="myapp", namespace="ns", role_name="admin")
    group_props = GroupProperties(
        univentionObjectIdentifier=uuid.uuid4(),
        name="testschool-group",
        ucsschoolRole=[UcsschoolRole(role="school_class", context="school", school="testschool")],
        allowedEmailUsers=[],
        allowedEmailGroups=[],
        users=[],
        mailAddress=None,
        guardianMemberRoles=[guardian],
    )
    assert group_props.guardianMemberRoles == [guardian]


def test_ucsschool_role_validator_keeps_colons_in_context():
    """Split like ucs-school-lib's get_role_info: the context part may itself
    contain colons (additional-context role strings)."""
    props = UserProperties.parse_obj(
        dict(
            univentionObjectIdentifier=uuid.uuid4(),
            username="testuser",
            firstname="Test",
            lastname="User",
            disabled=False,
            school=["testschool"],
            ucsschoolRole=["myrole:myapp:context:with:colons"],
            ucsschoolRecordUID="testuser",
            ucsschoolSourceUID="src",
            groups=[],
            ucsschoolLegalWard=[],
            ucsschoolLegalGuardian=[],
            mailPrimaryAddress="",
        )
    )
    assert props.ucsschoolRole == [
        UcsschoolRole(role="myrole", context="myapp", school="context:with:colons")
    ]


def test_ucsschool_role_validator_skips_malformed_role_strings():
    """One garbage role entry must not make an otherwise valid user invisible
    to the cache — it is skipped with a warning."""
    props = UserProperties.parse_obj(
        dict(
            univentionObjectIdentifier=uuid.uuid4(),
            username="testuser",
            firstname="Test",
            lastname="User",
            disabled=False,
            school=["testschool"],
            ucsschoolRole=["123", "school_admin:school:testschool"],
            ucsschoolRecordUID="testuser",
            ucsschoolSourceUID="src",
            groups=[],
            ucsschoolLegalWard=[],
            ucsschoolLegalGuardian=[],
            mailPrimaryAddress="",
        )
    )
    assert props.ucsschoolRole == [
        UcsschoolRole(role="school_admin", context="school", school="testschool")
    ]


def test_ucsschool_role_validator_rejects_user_without_any_parseable_role():
    from pydantic import ValidationError

    with pytest.raises(ValidationError, match="at least 1 item"):
        UserProperties.parse_obj(
            dict(
                univentionObjectIdentifier=uuid.uuid4(),
                username="testuser",
                firstname="Test",
                lastname="User",
                disabled=False,
                school=["testschool"],
                ucsschoolRole=["123", "teacher:school"],
                ucsschoolRecordUID="testuser",
                ucsschoolSourceUID="src",
                groups=[],
                ucsschoolLegalWard=[],
                ucsschoolLegalGuardian=[],
                mailPrimaryAddress="",
            )
        )


def test_ucsschool_role_validator_accepts_pre_parsed_object():
    role = UcsschoolRole(role="teacher", context="school", school="testschool")
    user_props = UserProperties(
        univentionObjectIdentifier=uuid.uuid4(),
        username="testuser",
        firstname="Test",
        lastname="User",
        disabled=False,
        school=["testschool"],
        ucsschoolRole=[role],
        ucsschoolRecordUID="testuser",
        ucsschoolSourceUID="src",
        groups=[],
        ucsschoolLegalWard=[],
        ucsschoolLegalGuardian=[],
        mailPrimaryAddress="",
        birthday=None,
        userexpiry=None,
    )
    assert user_props.ucsschoolRole == [role]
    group_props = GroupProperties(
        univentionObjectIdentifier=uuid.uuid4(),
        name="testschool-group",
        ucsschoolRole=[role],
        allowedEmailUsers=[],
        allowedEmailGroups=[],
        users=[],
        mailAddress=None,
        guardianMemberRoles=[],
    )
    assert group_props.ucsschoolRole == [role]


async def test_fetch_roles_by_entries_returns_empty_set_immediately(manager, mock_storage):
    result = await manager._fetch_roles_by_entries([], mock_storage)
    assert result == set()
    mock_storage.roles.search.assert_not_called()


async def test_fetch_roles_by_entries_searches_for_role_names(manager, mock_storage):
    role = make_role("teacher")
    mock_storage.roles.search.return_value = [role]

    result = await manager._fetch_roles_by_entries(
        [UcsschoolRole(role="teacher", context="school", school="testschool")],
        mock_storage,
    )
    assert role in result


async def test_build_school_memberships_no_roles_skips_role_search(manager, mock_storage):
    school = make_school()
    result = await manager._build_school_memberships([school], set(), [], mock_storage, None)
    assert school.public_id in result
    assert result[school.public_id].roles == set()
    mock_storage.roles.search.assert_not_called()


async def test_build_school_memberships_matches_roles_to_school(manager, mock_storage):
    school = make_school(name="testschool")
    role = make_role("teacher")
    mock_storage.roles.search.return_value = [role]

    result = await manager._build_school_memberships(
        [school],
        set(),
        [UcsschoolRole(role="teacher", context="school", school="testschool")],
        mock_storage,
        None,
    )

    assert result[school.public_id].roles == {role}


# ── User events ───────────────────────────────────────────────────────────────


async def test_handle_user_create_drops_event_when_school_list_is_empty(
    manager, mock_storage, mock_mapper
):
    event = _user_create_event(uuid.uuid4(), extra_props={"school": []})
    await manager.handle_user_create(event)
    mock_storage.schools.search.assert_not_called()
    mock_storage.users.create.assert_not_called()


async def test_handle_user_create_drops_event_when_school_not_found(manager, mock_storage, mock_mapper):
    mock_storage.schools.search.return_value = []
    event = _user_create_event(uuid.uuid4())
    await manager.handle_user_create(event)
    mock_storage.users.create.assert_not_called()


async def test_handle_user_create_happy_path(manager, mock_storage, mock_mapper):
    uid = uuid.uuid4()
    school = make_school("testschool")
    mock_storage.schools.search.return_value = [school]
    mock_storage.users.get.side_effect = NotFound("user", str(uid))
    event = _user_create_event(uid, extra_props={"ucsschoolLegalWard": ["uid=ward,dc=test"]})

    await manager.handle_user_create(event)

    mock_storage.users.create.assert_called_once()
    created = mock_storage.users.create.call_args[0][0]
    _assert_fully_loaded(created)
    assert created.public_id == uid
    assert created.name == "testuser"
    mock_mapper.set_mapping.assert_called_once_with(
        ObjectType.USER, "uid=testuser,cn=users,dc=test", uid
    )


async def test_handle_user_create_primary_school_from_dn(manager, mock_storage, mock_mapper):
    """A user created in school B that is also a member of school A: the DN's
    OU decides the primary membership, not the order of the (unordered)
    school property list."""
    uid = uuid.uuid4()
    school_a = make_school("schoola")
    school_b = make_school("schoolb")
    mock_storage.schools.search.return_value = [school_a, school_b]
    mock_storage.users.get.side_effect = NotFound("user", str(uid))
    event = _user_create_event(
        uid,
        extra_props={
            "school": ["schoola", "schoolb"],
            "ucsschoolRole": [
                UcsschoolRole(role="teacher", context="school", school="schoola"),
                UcsschoolRole(role="teacher", context="school", school="schoolb"),
            ],
        },
        dn="uid=testuser,cn=lehrer,cn=users,ou=schoolb,dc=test",
    )

    await manager.handle_user_create(event)

    created = mock_storage.users.create.call_args[0][0]
    assert created.school_memberships[school_a.public_id].is_primary is False
    assert created.school_memberships[school_b.public_id].is_primary is True


async def test_handle_user_create_generates_record_uid_and_source_uid(
    manager, mock_storage, mock_mapper
):
    uid = uuid.uuid4()
    school = make_school("testschool")
    mock_storage.schools.search.return_value = [school]
    props = UserProperties(
        univentionObjectIdentifier=UUID4(str(uid)),
        username="autouser",
        firstname="Auto",
        lastname="User",
        disabled=False,
        school=["testschool"],
        ucsschoolRole=[UcsschoolRole(role="teacher", context="school", school="testschool")],
        groups=[],
        ucsschoolLegalWard=[],
        ucsschoolLegalGuardian=[],
        ucsschoolRecordUID=None,
        ucsschoolSourceUID=None,
        mailPrimaryAddress="",
        birthday=None,
        userexpiry=None,
    )
    event = UserCreateEvent(
        timestamp=_TS,
        sequence_number=1,
        new=UserPayload(
            dn="uid=autouser,cn=users,dc=test",
            id="autouser",
            objectType="users/user",
            position="cn=users,dc=test",
            properties=props,
        ),
    )

    mock_storage.users.get.side_effect = NotFound("user", str(uid))
    await manager.handle_user_create(event)

    created = mock_storage.users.create.call_args[0][0]
    assert created.record_uid == "autouser"
    assert created.source_uid == DEFAULT_NUBUS_SOURCE_UID


async def test_handle_user_delete_happy_path(manager, mock_storage, mock_mapper):
    uid = uuid.uuid4()
    event = _user_delete_event(uid)
    await manager.handle_user_delete(event)
    mock_storage.users.delete.assert_called_once_with(uid)


async def test_handle_user_modify_calls_modify_when_patch_is_non_empty(
    manager, mock_storage, mock_mapper
):
    uid = uuid.uuid4()
    school = make_school("testschool")
    current_user = make_user(uid=uid, school_memberships=UNLOADED)
    current_user.firstname = "OldFirst"
    mock_storage.users.get.return_value = current_user
    mock_storage.schools.search.return_value = [school]

    event = _user_modify_event(
        uid,
        extra_props={"firstname": "NewFirst", "school": ["testschool"]},
    )
    await manager.handle_user_modify(event)

    mock_storage.users.modify.assert_called_once()


async def test_handle_user_modify_skips_modify_when_patch_is_empty(manager, mock_storage, mock_mapper):
    uid = UUID4(str(uuid.uuid4()))
    current_user = make_user(uid=uid)
    current_user.email = "testuser@example.com"
    mock_storage.users.get.return_value = current_user

    props = UserProperties(
        univentionObjectIdentifier=uid,
        username="testuser",
        firstname="Test",
        lastname="User",
        disabled=False,
        school=[],
        ucsschoolRole=[UcsschoolRole(role="teacher", context="school", school="testschool")],
        groups=[],
        ucsschoolLegalWard=[],
        ucsschoolLegalGuardian=[],
        ucsschoolRecordUID="testuser",
        ucsschoolSourceUID="src",
        mailPrimaryAddress="testuser@example.com",
        birthday=None,
        userexpiry=None,
    )
    event = UserModifyEvent(
        timestamp=_TS,
        sequence_number=1,
        new=UserPayload(
            dn="uid=testuser,dc=test",
            id="testuser",
            objectType="users/user",
            position="cn=users,dc=test",
            properties=props,
        ),
    )
    current_user.udm_properties = _udm_properties(event.new.properties)
    await manager.handle_user_modify(event)

    mock_storage.users.modify.assert_not_called()


def _half_loaded_group(name: str, school, uid) -> Group:
    """A group as a plain search returns it: scalars loaded, roles UNLOADED."""
    return Group(
        public_id=uid,
        record_uid=name,
        source_uid="kelvin-connector",
        name=name,
        display_name=name,
        create_share=False,
        roles=UNLOADED,
        allowed_email_senders_users=UNLOADED,
        allowed_email_senders_groups=UNLOADED,
        members=UNLOADED,
        member_roles=UNLOADED,
        school=school,
    )


async def test_handle_user_modify_same_group_at_different_load_depth_is_no_change(
    manager, mock_storage, mock_mapper
):
    """Regression: the baseline loads membership groups with their roles, the
    freshly searched groups come without them. jsonpatch used to diff inside
    the group objects (/school_memberships/<id>/groups/0/roles) — paths the
    user manager rejects with UnsupportedOperation. The same link set at a
    different load depth is not a change."""
    uid = uuid.uuid4()
    group_uid = uuid.uuid4()
    group_dn = "cn=testschool-group,cn=groups,dc=test"
    school = make_school("testschool")
    teacher_role = make_role("teacher")
    baseline_group = make_group("testschool-group", school, uid=group_uid)  # roles loaded
    fresh_group = _half_loaded_group("testschool-group", school, uid=group_uid)

    current_user = make_user(
        uid=uid,
        school_memberships={
            school.public_id: SchoolMembership(
                school=school, is_primary=True, roles={teacher_role}, groups={baseline_group}
            )
        },
    )
    current_user.email = "testuser@example.com"
    mock_storage.users.get.return_value = current_user
    mock_storage.schools.search.return_value = [school]
    mock_storage.roles.search.return_value = [teacher_role]
    mock_mapper.dns_to_public_ids.return_value = {group_dn: group_uid}
    mock_storage.groups.search.return_value = [fresh_group]

    event = _user_modify_event(uid, extra_props={"groups": [group_dn]})
    current_user.udm_properties = _udm_properties(event.new.properties)
    await manager.handle_user_modify(event)

    mock_storage.users.modify.assert_not_called()


async def test_handle_user_modify_group_change_replaces_membership_groups_atomically(
    manager, mock_storage, mock_mapper
):
    uid = uuid.uuid4()
    new_group_uid = uuid.uuid4()
    group_dn = "cn=testschool-newgroup,cn=groups,dc=test"
    school = make_school("testschool")
    teacher_role = make_role("teacher")
    baseline_group = make_group("testschool-oldgroup", school)
    fresh_group = _half_loaded_group("testschool-newgroup", school, uid=new_group_uid)

    current_user = make_user(
        uid=uid,
        school_memberships={
            school.public_id: SchoolMembership(
                school=school, is_primary=True, roles={teacher_role}, groups={baseline_group}
            )
        },
    )
    current_user.email = "testuser@example.com"
    mock_storage.users.get.return_value = current_user
    mock_storage.schools.search.return_value = [school]
    mock_storage.roles.search.return_value = [teacher_role]
    mock_mapper.dns_to_public_ids.return_value = {group_dn: new_group_uid}
    mock_storage.groups.search.return_value = [fresh_group]

    event = _user_modify_event(uid, extra_props={"groups": [group_dn]})
    await manager.handle_user_modify(event)

    mock_storage.users.modify.assert_called_once()
    ops = mock_storage.users.modify.call_args[0][1]
    groups_path = f"/school_memberships/{school.public_id}/groups"
    (groups_op,) = [op for op in ops if op["path"] == groups_path]
    assert groups_op["op"] == "replace"
    assert [g["public_id"] for g in groups_op["value"]] == [str(new_group_uid)]
    # no operation reaches inside a referenced group or role
    assert not any(op["path"].startswith(f"{groups_path}/") for op in ops)


async def test_handle_user_modify_school_move_moves_primary_flag(manager, mock_storage, mock_mapper):
    """A move to another OU flips is_primary on the kept memberships —
    emitted as per-membership is_primary replace ops. The primary school
    follows the DN, not the (unordered) school property list."""
    uid = uuid.uuid4()
    school_a = make_school("schoola")
    school_b = make_school("schoolb")
    teacher_role = make_role("teacher")

    current_user = make_user(
        uid=uid,
        school_memberships={
            school_a.public_id: SchoolMembership(
                school=school_a, is_primary=True, roles={teacher_role}, groups=set()
            ),
            school_b.public_id: SchoolMembership(
                school=school_b, is_primary=False, roles={teacher_role}, groups=set()
            ),
        },
    )
    current_user.email = "testuser@example.com"
    mock_storage.users.get.return_value = current_user
    mock_storage.schools.search.return_value = [school_a, school_b]
    mock_storage.roles.search.return_value = [teacher_role]

    event = _user_modify_event(
        uid,
        extra_props={
            "school": ["schoola", "schoolb"],
            "ucsschoolRole": [
                UcsschoolRole(role="teacher", context="school", school="schoola"),
                UcsschoolRole(role="teacher", context="school", school="schoolb"),
            ],
        },
        dn="uid=testuser,cn=lehrer,cn=users,ou=schoolb,dc=test",
    )
    current_user.udm_properties = _udm_properties(event.new.properties)
    await manager.handle_user_modify(event)

    mock_storage.users.modify.assert_called_once()
    ops = mock_storage.users.modify.call_args[0][1]
    assert {(op["path"], op["value"]) for op in ops} == {
        (f"/school_memberships/{school_a.public_id}/is_primary", False),
        (f"/school_memberships/{school_b.public_id}/is_primary", True),
    }


async def test_handle_user_modify_refreshes_dn_mapping(manager, mock_storage, mock_mapper):
    """A move/rename changes the dn but keeps the public_id; the mapping is
    refreshed even when nothing else changed, so later events referencing the
    new dn resolve."""
    uid = UUID4(str(uuid.uuid4()))
    current_user = make_user(uid=uid)
    current_user.email = "testuser@example.com"
    mock_storage.users.get.return_value = current_user

    event = _user_modify_event(uid)
    current_user.udm_properties = _udm_properties(event.new.properties)
    await manager.handle_user_modify(event)

    mock_storage.users.modify.assert_not_called()  # no property changes
    mock_mapper.set_mapping.assert_called_once_with(ObjectType.USER, event.new.dn, uid)


async def test_handle_user_modify_creates_missing_user(manager, mock_storage, mock_mapper):
    """A modify event carries the full desired state — if the user's create
    event was lost, the modify event repairs the gap by creating."""
    uid = uuid.uuid4()
    school = make_school("testschool")
    mock_storage.users.get.side_effect = NotFound("User", str(uid))
    mock_storage.schools.search.return_value = [school]

    event = _user_modify_event(uid)
    await manager.handle_user_modify(event)

    mock_storage.users.modify.assert_not_called()
    mock_storage.users.create.assert_called_once()
    created = mock_storage.users.create.call_args[0][0]
    assert created.public_id == uid
    mock_mapper.set_mapping.assert_called_once_with(ObjectType.USER, event.new.dn, uid)


async def test_handle_user_modify_generates_record_uid_and_source_uid(
    manager, mock_storage, mock_mapper
):
    uid = UUID4(str(uuid.uuid4()))
    current_user = make_user(uid=uid, school_memberships=UNLOADED)
    current_user.record_uid = "old_record"
    current_user.source_uid = "old_source"
    mock_storage.users.get.return_value = current_user

    props = UserProperties(
        univentionObjectIdentifier=uid,
        username="testuser",
        firstname="Test",
        lastname="User",
        disabled=False,
        school=[],
        ucsschoolRole=[UcsschoolRole(role="teacher", context="school", school="testschool")],
        groups=[],
        ucsschoolLegalWard=[],
        ucsschoolLegalGuardian=[],
        ucsschoolRecordUID="",
        ucsschoolSourceUID="",
        mailPrimaryAddress="",
        birthday=None,
        userexpiry=None,
    )
    event = UserModifyEvent(
        timestamp=_TS,
        sequence_number=1,
        new=UserPayload(
            dn="uid=testuser,dc=test",
            id="testuser",
            objectType="users/user",
            position="cn=users,dc=test",
            properties=props,
        ),
    )
    await manager.handle_user_modify(event)

    mock_storage.users.modify.assert_called_once()


def test_apply_user_changes_covers_all_branches(manager):
    uid = uuid.uuid4()
    school = make_school()
    user = make_user(uid=uid, school_memberships=UNLOADED)
    ward = make_user(name="ward", uid=uuid.uuid4())
    membership = SchoolMembership(school=school, is_primary=True, roles=set(), groups=set())

    user_props = UserProperties(
        univentionObjectIdentifier=uid,
        username="newname",
        firstname="Test",
        lastname="User",
        disabled=False,
        school=["testschool"],
        ucsschoolRole=[UcsschoolRole(role="teacher", context="school", school="testschool")],
        groups=[],
        ucsschoolLegalWard=[],
        ucsschoolLegalGuardian=[],
        ucsschoolRecordUID="newname",
        ucsschoolSourceUID="src",
        mailPrimaryAddress="",
        birthday=None,
        userexpiry=None,
    )

    manager._apply_user_changes(
        user,
        user_props=user_props,
        school_memberships={school.public_id: membership},
        legal_wards={ward},
        legal_guardians=set(),
    )

    assert user.name == "newname"
    assert user.school_memberships == {school.public_id: membership}
    assert user.legal_wards == {ward}
    assert user.legal_guardians == set()


# ── Group events ──────────────────────────────────────────────────────────────


async def test_handle_group_create_drops_event_when_school_not_found(manager, mock_storage, mock_mapper):
    mock_storage.schools.search.return_value = []
    event = _group_create_event(uuid.uuid4())
    await manager.handle_group_create(event)
    mock_storage.groups.create.assert_not_called()


async def test_handle_group_create_happy_path(manager, mock_storage, mock_mapper):
    uid = uuid.uuid4()
    school = make_school("testschool")
    mock_storage.schools.search.return_value = [school]
    mock_storage.groups.get.side_effect = NotFound("group", str(uid))
    event = _group_create_event(uid)

    await manager.handle_group_create(event)

    mock_storage.groups.create.assert_called_once()
    created = mock_storage.groups.create.call_args[0][0]
    _assert_fully_loaded(created)
    assert created.public_id == uid
    assert created.name == "testschool-group"
    assert created.create_share is True
    mock_mapper.set_mapping.assert_called_once_with(
        ObjectType.GROUP, "cn=testschool-group,cn=klassen,dc=test", uid
    )


async def test_handle_group_create_stores_description(manager, mock_storage, mock_mapper):
    uid = uuid.uuid4()
    school = make_school("testschool")
    mock_storage.schools.search.return_value = [school]
    mock_storage.groups.get.side_effect = NotFound("group", str(uid))
    event = _group_create_event(uid, extra_props={"description": "1a maths"})

    await manager.handle_group_create(event)

    created = mock_storage.groups.create.call_args[0][0]
    assert created.description == "1a maths"


async def test_handle_group_create_skips_members_without_school_membership(
    manager, mock_storage, mock_mapper
):
    """A member whose (user, school) membership row does not exist yet must
    not fail the whole group creation — the member is dropped with a warning
    and linked later by its own event, which carries the group DN."""
    uid = uuid.uuid4()
    school = make_school("testschool")
    member = make_user(name="present", uid=uuid.uuid4())
    missing_uid = uuid.uuid4()
    dns = ["uid=present,dc=test", "uid=missing,dc=test"]
    mapping = {dns[0]: member.public_id, dns[1]: missing_uid}
    mock_storage.schools.search.return_value = [school]
    mock_storage.groups.get.side_effect = NotFound("group", str(uid))
    mock_mapper.dns_to_public_ids.side_effect = lambda _type, ds: {
        d: mapping[d] for d in ds if d in mapping
    }
    # the storage-side query filters out the member without a membership row
    mock_storage.users.search.return_value = [member]

    event = _group_create_event(uid, extra_props={"users": dns})
    await manager.handle_group_create(event)

    mock_storage.groups.create.assert_called_once()
    created = mock_storage.groups.create.call_args[0][0]
    assert created.members == {member}
    # members are searched with the school membership filter applied
    query = mock_storage.users.search.call_args[0][0]
    _, school_filter = query.where.clauses
    assert school_filter.field == "schools.public_id"
    assert school_filter.value == str(school.public_id)


async def test_handle_group_modify_filters_members_against_stored_school_when_school_unknown(
    manager, mock_storage, mock_mapper
):
    """If the event's school is not in the cache the group keeps its stored
    school, so members are filtered against that one."""
    uid = uuid.uuid4()
    school = make_school("someschool")
    current_group = make_group("someschool-group", school, uid=uid)
    member = make_user(uid=uuid.uuid4())
    dn = "uid=member,dc=test"
    mock_storage.groups.get.return_value = current_group
    mock_storage.schools.search.return_value = []  # event school not in cache
    mock_mapper.dns_to_public_ids.return_value = {dn: member.public_id}
    mock_storage.users.search.return_value = [member]

    event = _group_modify_event(uid, name="someschool-group", extra_props={"users": [dn]})
    await manager.handle_group_modify(event)

    query = mock_storage.users.search.call_args[0][0]
    _, school_filter = query.where.clauses
    assert school_filter.field == "schools.public_id"
    assert school_filter.value == str(school.public_id)


async def test_handle_group_modify_refreshes_dn_mapping(manager, mock_storage, mock_mapper):
    uid = uuid.uuid4()
    school = make_school("testschool")
    current_group = make_group("testschool-group", school, uid=uid)
    mock_storage.groups.get.return_value = current_group
    mock_storage.schools.search.return_value = [school]

    event = _group_modify_event(uid)
    await manager.handle_group_modify(event)

    mock_mapper.set_mapping.assert_called_once_with(ObjectType.GROUP, event.new.dn, uid)


async def test_handle_group_modify_creates_missing_group(manager, mock_storage, mock_mapper):
    """A modify event carries the full desired state — if the group's create
    event was lost, the modify event repairs the gap by creating."""
    uid = uuid.uuid4()
    school = make_school("testschool")
    mock_storage.groups.get.side_effect = NotFound("Group", str(uid))
    mock_storage.schools.search.return_value = [school]

    event = _group_modify_event(uid)
    await manager.handle_group_modify(event)

    mock_storage.groups.modify.assert_not_called()
    mock_storage.groups.create.assert_called_once()
    created = mock_storage.groups.create.call_args[0][0]
    assert created.public_id == uid
    mock_mapper.set_mapping.assert_called_once_with(ObjectType.GROUP, event.new.dn, uid)


async def test_handle_group_delete_happy_path(manager, mock_storage, mock_mapper):
    uid = uuid.uuid4()
    event = _group_delete_event(uid)
    await manager.handle_group_delete(event)
    mock_storage.groups.delete.assert_called_once_with(uid)


async def test_handle_group_modify_calls_modify_when_patch_is_non_empty(
    manager, mock_storage, mock_mapper
):
    uid = uuid.uuid4()
    school = make_school("testschool")
    current_group = make_group("testschool-group", school, uid=uid)
    mock_storage.groups.get.return_value = current_group
    mock_storage.schools.search.return_value = [school]

    event = _group_modify_event(
        uid,
        name="testschool-newgroup",
        extra_props={
            "name": "testschool-newgroup",
            "mailAddress": "grp@example.com",
            "allowedEmailUsers": [],
            "allowedEmailGroups": [],
            "users": [],
            "ucsschoolRole": ["school_class:school:testschool"],
            "guardianMemberRoles": [],
        },
    )
    await manager.handle_group_modify(event)

    mock_storage.groups.modify.assert_called_once()


async def test_handle_group_modify_skips_modify_when_patch_is_empty(manager, mock_storage, mock_mapper):
    uid = uuid.uuid4()
    school = make_school("testschool")
    current_group = make_group("testschool-group", school, uid=uid)
    mock_storage.groups.get.return_value = current_group
    mock_storage.schools.search.return_value = [school]

    props = GroupProperties(
        univentionObjectIdentifier=UUID4(str(uid)),
        name="testschool-group",
        ucsschoolRole=[UcsschoolRole(role="school_class", context="school", school="testschool")],
        allowedEmailUsers=[],
        allowedEmailGroups=[],
        users=[],
        mailAddress=None,
        guardianMemberRoles=[],
    )
    event = GroupModifyEvent(
        timestamp=_TS,
        sequence_number=1,
        new=GroupPayload(
            dn="cn=testschool-group,dc=test",
            id="testschool-group",
            objectType="groups/group",
            position="cn=klassen,dc=test",
            properties=props,
        ),
    )
    current_group.udm_properties = _udm_properties(event.new.properties)
    await manager.handle_group_modify(event)

    mock_storage.groups.modify.assert_not_called()


def test_apply_group_changes_school_not_found_leaves_school_unmodified(manager):
    school = make_school()
    group = make_group("testschool-group", school)
    original_school = group.school

    group_props = GroupProperties(
        univentionObjectIdentifier=uuid.uuid4(),
        name="testschool-group",
        ucsschoolRole=[UcsschoolRole(role="school_class", context="school", school="testschool")],
        allowedEmailUsers=[],
        allowedEmailGroups=[],
        users=[],
        mailAddress=None,
        guardianMemberRoles=[],
    )

    manager._apply_group_changes(
        group,
        group_props=group_props,
        school=UNLOADED,
        group_roles=set(),
        allowed_email_senders_users=set(),
        allowed_email_senders_groups=set(),
        members=set(),
        member_roles=set(),
    )

    assert group.school is original_school
    with pytest.raises(ValueError, match="email is not loaded"):
        assert group.email is None


def test_apply_group_changes_updates_name_and_email(manager):
    school = make_school()
    group = make_group("testschool-group", school)
    new_school = make_school("testschool")

    group_props = GroupProperties(
        univentionObjectIdentifier=uuid.uuid4(),
        name="testschool-newgroup",
        ucsschoolRole=[UcsschoolRole(role="school_class", context="school", school="testschool")],
        allowedEmailUsers=[],
        allowedEmailGroups=[],
        users=[],
        mailAddress="grp@example.com",
        guardianMemberRoles=[],
    )

    manager._apply_group_changes(
        group,
        group_props=group_props,
        school=new_school,
        group_roles=set(),
        allowed_email_senders_users=set(),
        allowed_email_senders_groups=set(),
        members=set(),
        member_roles=set(),
    )

    assert group.name == "testschool-newgroup"
    assert group.display_name == "testschool-newgroup"
    assert group.record_uid == "testschool-newgroup"
    assert group.email == "grp@example.com"
    assert group.school is new_school


# ── School events ─────────────────────────────────────────────────────────────


async def test_handle_school_create_happy_path(manager, mock_storage, mock_mapper):
    uid = uuid.uuid4()
    mock_storage.schools.get.side_effect = NotFound("school", str(uid))
    event = _school_create_event(uid)

    await manager.handle_school_create(event)

    mock_storage.schools.create.assert_called_once()
    created = mock_storage.schools.create.call_args[0][0]
    _assert_fully_loaded(created)
    assert created.public_id == uid
    assert created.name == "testschool"
    mock_mapper.set_mapping.assert_called_once_with(ObjectType.SCHOOL, "ou=testschool,dc=test", uid)


async def test_handle_school_create_stores_share_file_servers(manager, mock_storage, mock_mapper):
    # The share file servers are carried by the OU event as DNs; the cache
    # stores the hostname, matching what v1 resolves via computer_dn2name.
    uid = uuid.uuid4()
    mock_storage.schools.get.side_effect = NotFound("school", str(uid))
    event = _school_create_event(
        uid,
        extra_props={
            "ucsschoolClassShareFileServer": "cn=master,cn=dc,dc=test",
            "ucsschoolHomeShareFileServer": "cn=master,cn=dc,dc=test",
        },
    )

    await manager.handle_school_create(event)

    created = mock_storage.schools.create.call_args[0][0]
    assert created.class_share_file_server == "master"
    assert created.home_share_file_server == "master"


async def test_handle_school_delete_happy_path(manager, mock_storage, mock_mapper):
    uid = uuid.uuid4()
    event = _school_delete_event(uid)
    await manager.handle_school_delete(event)
    mock_storage.schools.delete.assert_called_once_with(uid)


async def test_handle_school_modify_calls_modify_when_patch_is_non_empty(
    manager, mock_storage, mock_mapper
):
    uid = uuid.uuid4()
    current_school = make_school("testschool", uid=uid)
    current_school.display_name = "Old Display"
    mock_storage.schools.get.return_value = current_school

    event = _school_modify_event(uid, extra_props={"displayName": "New Display"})
    await manager.handle_school_modify(event)

    mock_storage.schools.modify.assert_called_once()


async def test_handle_school_modify_refreshes_dn_mapping(manager, mock_storage, mock_mapper):
    uid = uuid.uuid4()
    current_school = make_school("testschool", uid=uid)
    mock_storage.schools.get.return_value = current_school

    event = _school_modify_event(uid)
    await manager.handle_school_modify(event)

    mock_mapper.set_mapping.assert_called_once_with(ObjectType.SCHOOL, event.new.dn, uid)


async def test_handle_school_modify_creates_missing_school(manager, mock_storage, mock_mapper):
    """A modify event carries the full desired state — if the school's create
    event was lost, the modify event repairs the gap by creating."""
    uid = uuid.uuid4()
    mock_storage.schools.get.side_effect = NotFound("School", str(uid))

    event = _school_modify_event(uid)
    await manager.handle_school_modify(event)

    mock_storage.schools.modify.assert_not_called()
    mock_storage.schools.create.assert_called_once()
    created = mock_storage.schools.create.call_args[0][0]
    assert created.public_id == uid
    assert created.name == "testschool"
    mock_mapper.set_mapping.assert_called_once_with(ObjectType.SCHOOL, event.new.dn, uid)


async def test_handle_school_modify_updates_name(manager, mock_storage, mock_mapper):
    uid = uuid.uuid4()
    current_school = make_school("oldschool", uid=uid)
    mock_storage.schools.get.return_value = current_school

    event = _school_modify_event(uid, extra_props={"name": "newschool"})
    await manager.handle_school_modify(event)

    mock_storage.schools.modify.assert_called_once()


async def test_handle_school_modify_skips_modify_when_patch_is_empty(manager, mock_storage, mock_mapper):
    uid = uuid.uuid4()
    current_school = make_school("testschool", uid=uid)
    current_school.display_name = "testschool Display"
    mock_storage.schools.get.return_value = current_school

    event = _school_modify_event(uid)
    current_school.udm_properties = _udm_properties(event.new.properties)
    await manager.handle_school_modify(event)

    mock_storage.schools.modify.assert_not_called()


# ── Robustness / regression tests ────────────────────────────────────────────


def test_school_ou_from_dn():
    assert _school_ou_from_dn("uid=a,cn=lehrer,cn=users,ou=school1,dc=test") == "school1"
    # district mode: the school is the innermost (first) OU
    assert _school_ou_from_dn("uid=a,cn=users,OU=school1,ou=district,dc=test") == "school1"
    assert _school_ou_from_dn("uid=a,cn=users,dc=test") is None


async def test_build_school_memberships_primary_school_wins_over_list_order(manager, mock_storage):
    """The multi-valued school UDM property is unordered — the OU from the
    user's DN decides the primary membership, not list position."""
    school_a = make_school("schoola")
    school_b = make_school("schoolb")
    result = await manager._build_school_memberships(
        [school_a, school_b], set(), [], mock_storage, "schoolb"
    )
    assert result[school_a.public_id].is_primary is False
    assert result[school_b.public_id].is_primary is True


async def test_build_school_memberships_primary_school_matches_case_insensitively(
    manager, mock_storage
):
    school_a = make_school("schoola")
    school_b = make_school("schoolb")
    result = await manager._build_school_memberships(
        [school_a, school_b], set(), [], mock_storage, "SchoolB"
    )
    assert result[school_a.public_id].is_primary is False
    assert result[school_b.public_id].is_primary is True


async def test_build_school_memberships_falls_back_to_first_school(manager, mock_storage):
    """No or unknown DN OU (e.g. it was dropped as not cached): the first
    school is primary, as the only remaining order signal."""
    school_a = make_school("schoola")
    school_b = make_school("schoolb")
    for primary_school in (None, "otherschool"):
        result = await manager._build_school_memberships(
            [school_a, school_b], set(), [], mock_storage, primary_school
        )
        assert result[school_a.public_id].is_primary is True
        assert result[school_b.public_id].is_primary is False


async def test_build_school_memberships_groups_filtered_per_school(manager, mock_storage):
    school_a = make_school("schoola")
    school_b = make_school("schoolb")
    group_a = make_group("schoola-class1", school_a)
    group_b = make_group("schoolb-class1", school_b)

    result = await manager._build_school_memberships(
        [school_a, school_b], {group_a, group_b}, [], mock_storage, None
    )

    assert result[school_a.public_id].groups == {group_a}
    assert result[school_b.public_id].groups == {group_b}


async def test_handle_group_create_preserves_member_roles(manager, mock_storage, mock_mapper):
    uid = uuid.uuid4()
    school = make_school("testschool")
    role = make_role("testschool")
    mock_storage.schools.search.return_value = [school]
    mock_storage.roles.search.return_value = [role]
    mock_storage.groups.get.side_effect = NotFound("group", str(uid))
    event = _group_create_event(
        uid,
        extra_props={"guardianMemberRoles": ["teacher:school:testschool"]},
    )
    await manager.handle_group_create(event)

    mock_storage.groups.create.assert_called_once()
    created = mock_storage.groups.create.call_args[0][0]
    assert created.member_roles == {role}


# ── Host group events ─────────────────────────────────────────────────────────


async def test_handle_host_group_create_edukativnetz(manager, mock_storage, mock_mapper):
    uid = uuid.uuid4()
    school = make_school("demoschool")
    mock_storage.schools.search.return_value = [school]
    event = _host_group_create_event(uid, hosts=["cn=newserver,cn=computers,dc=test"])

    await manager.handle_host_group_create(event)

    mock_storage.schools.modify.assert_called_once()
    patch = mock_storage.schools.modify.call_args[0][1]
    # the host DN is reduced to its hostname (leaf cn), matching v1
    server_ops = [op for op in patch if "educational_servers" in op["path"]]
    assert server_ops
    assert all("newserver" in op["value"] and "cn=" not in op["value"][0] for op in server_ops)


async def test_handle_host_group_modify_verwaltungsnetz(manager, mock_storage, mock_mapper):
    uid = uuid.uuid4()
    school = make_school("demoschool")
    mock_storage.schools.search.return_value = [school]
    event = _host_group_modify_event(uid, hosts=["cn=newserver,cn=computers,dc=test"])

    await manager.handle_host_group_modify(event)

    mock_storage.schools.modify.assert_called_once()
    patch = mock_storage.schools.modify.call_args[0][1]
    server_ops = [op for op in patch if "administrative_servers" in op["path"]]
    assert server_ops
    assert all("newserver" in op["value"] and "cn=" not in op["value"][0] for op in server_ops)


async def test_handle_host_group_delete_clears_servers(manager, mock_storage, mock_mapper):
    # demoschool starts with educational_servers={"server1"}; deleting its
    # Edukativnetz host group must clear them so the cache does not keep
    # stale servers that v1 (reading the now-gone group) no longer reports.
    uid = uuid.uuid4()
    school = make_school("demoschool")
    mock_storage.schools.search.return_value = [school]
    event = _host_group_delete_event(uid, name="OUdemoschool-DC-Edukativnetz")

    await manager.handle_host_group_delete(event)

    mock_storage.schools.modify.assert_called_once()
    patch = mock_storage.schools.modify.call_args[0][1]
    server_ops = [op for op in patch if "educational_servers" in op["path"]]
    # clearing the list is expressed as element removals, never additions
    assert server_ops
    assert all(op["op"] == "remove" for op in server_ops)


async def test_handle_host_group_delete_ignores_missing_school(manager, mock_storage, mock_mapper):
    # The school may already be gone (OU deleted); deleting its host group is
    # then a no-op rather than an error.
    uid = uuid.uuid4()
    mock_storage.schools.search.return_value = []
    event = _host_group_delete_event(uid)
    await manager.handle_host_group_delete(event)
    mock_storage.schools.modify.assert_not_called()


async def test_handle_host_group_change_bad_name_raises(manager, mock_storage, mock_mapper):
    uid = uuid.uuid4()
    event = _host_group_create_event(uid, name="not-a-host-group")
    with pytest.raises(SynchronizationException, match="Unexpected host group name"):
        await manager.handle_host_group_create(event)


async def test_handle_host_group_change_school_not_found_raises(manager, mock_storage, mock_mapper):
    uid = uuid.uuid4()
    mock_storage.schools.search.return_value = []
    event = _host_group_create_event(uid)
    with pytest.raises(SynchronizationException, match="Unable to find school"):
        await manager.handle_host_group_create(event)


@pytest.mark.parametrize(
    "event_fn, handler_name, hosts",
    [
        (_host_group_create_event, "handle_host_group_create", ["cn=server1,cn=computers,dc=test"]),
        (_host_group_modify_event, "handle_host_group_modify", ["cn=server2,cn=computers,dc=test"]),
    ],
)
async def test_handle_host_group_change_skips_modify_when_patch_is_empty(
    manager, mock_storage, mock_mapper, event_fn, handler_name, hosts
):
    uid = uuid.uuid4()
    school = make_school("demoschool")
    mock_storage.schools.search.return_value = [school]
    # hosts already match the school's stored servers — no change expected
    event = event_fn(uid, hosts=hosts)

    await getattr(manager, handler_name)(event)

    mock_storage.schools.modify.assert_not_called()


async def test_handle_host_group_change_unset_public_id_raises(manager, mock_storage, mock_mapper):
    from ucsschool_objects.core.domain.models import School as SchoolModel

    uid = uuid.uuid4()
    school = SchoolModel(
        record_uid="demoschool",
        source_uid="kelvin-connector",
        name="demoschool",
        display_name="demoschool Display",
        educational_servers=set(),
        administrative_servers=set(),
    )
    mock_storage.schools.search.return_value = [school]
    event = _host_group_create_event(uid)
    with pytest.raises(ValueError, match="Unexpected UnsetType"):
        await manager.handle_host_group_create(event)


# ── Already-exists-on-create paths ───────────────────────────────────────────


async def test_handle_user_create_updates_when_already_exists(manager, mock_storage, mock_mapper):
    uid = uuid.uuid4()
    school = make_school("testschool")
    current_user = make_user(uid=uid, school_memberships=UNLOADED)
    current_user.firstname = "OldFirst"
    mock_storage.schools.search.return_value = [school]
    mock_storage.users.get.return_value = current_user

    event = _user_create_event(uid)  # firstname="Test" differs from "OldFirst"
    await manager.handle_user_create(event)

    mock_storage.users.create.assert_not_called()
    mock_storage.users.modify.assert_called_once()


async def test_handle_group_create_updates_when_already_exists(manager, mock_storage, mock_mapper):
    uid = uuid.uuid4()
    school = make_school("testschool")
    current_group = make_group("old-name", school, uid=uid)
    mock_storage.schools.search.return_value = [school]
    mock_storage.groups.get.return_value = current_group

    event = _group_create_event(uid)  # name="testschool-group" differs from "old-name"
    await manager.handle_group_create(event)

    mock_storage.groups.create.assert_not_called()
    mock_storage.groups.modify.assert_called_once()


async def test_handle_school_create_updates_when_already_exists(manager, mock_storage, mock_mapper):
    uid = uuid.uuid4()
    current_school = make_school("oldschool", uid=uid)
    mock_storage.schools.get.return_value = current_school

    event = _school_create_event(uid)  # name="testschool" differs from "oldschool"
    await manager.handle_school_create(event)

    mock_storage.schools.create.assert_not_called()
    mock_storage.schools.modify.assert_called_once()


async def test_handle_user_create_already_exists_no_changes(manager, mock_storage, mock_mapper):
    uid = UUID4(str(uuid.uuid4()))
    school = make_school("testschool")
    # Pre-build the exact SchoolMembership _build_school_memberships would produce
    # (roles.search returns [] by default, so roles=set())
    membership = SchoolMembership(school=school, groups=set(), is_primary=True, roles=set())
    current_user = make_user(uid=uid)
    current_user.email = "testuser@example.com"
    current_user.school_memberships = {school.public_id: membership}
    mock_storage.schools.search.return_value = [school]
    mock_storage.users.get.return_value = current_user

    event = _user_create_event(uid)  # identical data to current_user
    current_user.udm_properties = _udm_properties(event.new.properties)
    await manager.handle_user_create(event)

    mock_storage.users.create.assert_not_called()
    mock_storage.users.modify.assert_not_called()


async def test_handle_group_create_already_exists_no_changes(manager, mock_storage, mock_mapper):
    uid = uuid.uuid4()
    school = make_school("testschool")
    current_group = make_group("testschool-group", school, uid=uid)
    mock_storage.schools.search.return_value = [school]
    mock_storage.groups.get.return_value = current_group

    event = _group_create_event(uid)  # same name and defaults as current_group
    current_group.udm_properties = _udm_properties(event.new.properties)
    await manager.handle_group_create(event)

    mock_storage.groups.create.assert_not_called()
    mock_storage.groups.modify.assert_not_called()


async def test_handle_school_create_already_exists_no_changes(manager, mock_storage, mock_mapper):
    uid = uuid.uuid4()
    current_school = make_school("testschool", uid=uid)
    mock_storage.schools.get.return_value = current_school

    event = _school_create_event(uid)  # name="testschool", displayName="testschool Display"
    current_school.udm_properties = _udm_properties(event.new.properties)
    await manager.handle_school_create(event)

    mock_storage.schools.create.assert_not_called()
    mock_storage.schools.modify.assert_not_called()


# ── Delete-not-found paths ────────────────────────────────────────────────────


async def test_handle_user_delete_ignores_not_found(manager, mock_storage, mock_mapper):
    uid = uuid.uuid4()
    mock_storage.users.delete.side_effect = NotFound("user", str(uid))
    event = _user_delete_event(uid)
    await manager.handle_user_delete(event)
    mock_storage.users.delete.assert_called_once_with(uid)


async def test_handle_group_delete_ignores_not_found(manager, mock_storage, mock_mapper):
    uid = uuid.uuid4()
    mock_storage.groups.delete.side_effect = NotFound("group", str(uid))
    event = _group_delete_event(uid)
    await manager.handle_group_delete(event)
    mock_storage.groups.delete.assert_called_once_with(uid)


async def test_handle_school_delete_ignores_not_found(manager, mock_storage, mock_mapper):
    uid = uuid.uuid4()
    mock_storage.schools.delete.side_effect = NotFound("school", str(uid))
    event = _school_delete_event(uid)
    await manager.handle_school_delete(event)
    mock_storage.schools.delete.assert_called_once_with(uid)
