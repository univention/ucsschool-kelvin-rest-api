import uuid
from operator import attrgetter
from unittest.mock import patch

import pytest
from conftest import make_group, make_role, make_school, make_user
from kelvin_connector.models import EventType, GroupEvent, SchoolEvent, UserEvent
from kelvin_connector.nubus_compat import ObjectType
from ucsschool_objects.core.domain.models import UNLOADED, SchoolMembership

_TS = "2024-01-01T00:00:00"


# ── Event constructors ────────────────────────────────────────────────────────


def _user_event(event_type, uid, extra_props=None):
    base = {
        "univentionObjectIdentifier": str(uid),
        "username": "testuser",
        "firstname": "Test",
        "lastname": "User",
        "disabled": False,
        "school": ["testschool"],
        "ucsschoolRole": ["teacher:testschool"],
        "ucsschoolRecordUID": "testuser",
        "ucsschoolSourceUID": "src",
        "groups": [],
        "ucsschoolLegalWard": [],
        "ucsschoolLegalGuardian": [],
    }
    if extra_props:
        base.update(extra_props)
    dn = "uid=testuser,cn=users,dc=test"
    new = {"dn": dn, "properties": base} if event_type != EventType.DELETE else None
    old = (
        {"dn": dn, "properties": {"univentionObjectIdentifier": str(uid)}}
        if event_type != EventType.CREATE
        else None
    )
    return UserEvent(timestamp=_TS, sequence_number=1, event_type=event_type, old=old, new=new)


def _group_event(event_type, uid, name="testschool-group", extra_props=None):
    base = {
        "univentionObjectIdentifier": str(uid),
        "name": name,
        "ucsschoolRole": ["school_class:testschool"],
        "allowedEmailUsers": [],
        "allowedEmailGroups": [],
        "users": [],
    }
    if extra_props:
        base.update(extra_props)
    dn = f"cn={name},cn=klassen,dc=test"
    new = {"dn": dn, "properties": base} if event_type != EventType.DELETE else None
    old = (
        {"dn": dn, "properties": {"univentionObjectIdentifier": str(uid)}}
        if event_type != EventType.CREATE
        else None
    )
    return GroupEvent(timestamp=_TS, sequence_number=1, event_type=event_type, old=old, new=new)


def _school_event(event_type, uid, name="testschool", extra_props=None):
    base = {
        "univentionObjectIdentifier": str(uid),
        "name": name,
        "displayName": f"{name} Display",
    }
    if extra_props:
        base.update(extra_props)
    dn = f"ou={name},dc=test"
    new = {"dn": dn, "properties": base} if event_type != EventType.DELETE else None
    old = (
        {"dn": dn, "properties": {"univentionObjectIdentifier": str(uid)}}
        if event_type != EventType.CREATE
        else None
    )
    return SchoolEvent(timestamp=_TS, sequence_number=1, event_type=event_type, old=old, new=new)


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


async def test_fetch_roles_by_entries_returns_empty_set_immediately(manager, mock_storage):
    result = await manager._fetch_roles_by_entries([], mock_storage)
    assert result == set()
    mock_storage.roles.search.assert_not_called()


async def test_fetch_roles_by_entries_searches_for_role_names(manager, mock_storage):
    role = make_role("teacher")
    mock_storage.roles.search.return_value = [role]

    result = await manager._fetch_roles_by_entries(["teacher:testschool"], mock_storage)
    assert role in result


async def test_build_school_memberships_no_roles_skips_role_search(manager, mock_storage):
    school = make_school()
    result = await manager._build_school_memberships([school], set(), [], mock_storage)
    assert school.public_id in result
    assert result[school.public_id].roles == set()
    mock_storage.roles.search.assert_not_called()


async def test_build_school_memberships_matches_roles_to_school(manager, mock_storage):
    school = make_school(name="testschool")
    role = make_role("teacher")
    mock_storage.roles.search.return_value = [role]

    result = await manager._build_school_memberships(
        [school], set(), ["teacher:testschool"], mock_storage
    )

    assert result[school.public_id].roles == {role}


# ── Common early-return guards ────────────────────────────────────────────────


@pytest.mark.parametrize(
    "event_cls,handler_name,event_type,no_call",
    [
        pytest.param(UserEvent, "handle_user_event", EventType.CREATE, "users.create", id="user-create"),
        pytest.param(UserEvent, "handle_user_event", EventType.MODIFY, "users.get", id="user-modify"),
        pytest.param(
            GroupEvent, "handle_group_event", EventType.CREATE, "groups.create", id="group-create"
        ),
        pytest.param(
            GroupEvent, "handle_group_event", EventType.MODIFY, "groups.get", id="group-modify"
        ),
        pytest.param(
            SchoolEvent, "handle_school_event", EventType.CREATE, "schools.create", id="school-create"
        ),
        pytest.param(
            SchoolEvent, "handle_school_event", EventType.MODIFY, "schools.get", id="school-modify"
        ),
    ],
)
async def test_handler_skips_when_new_is_none(
    manager, mock_storage, mock_mapper, event_cls, handler_name, event_type, no_call
):
    event = event_cls(timestamp=_TS, sequence_number=1, event_type=event_type, old=None, new=None)
    with patch("kelvin_connector.sync.SQLAlchemyDNIDMapper", return_value=mock_mapper):
        await getattr(manager, handler_name)(event)
    attrgetter(no_call)(mock_storage).assert_not_called()


@pytest.mark.parametrize(
    "event_cls,handler_name,no_call",
    [
        pytest.param(UserEvent, "handle_user_event", "users.delete", id="user"),
        pytest.param(GroupEvent, "handle_group_event", "groups.delete", id="group"),
        pytest.param(SchoolEvent, "handle_school_event", "schools.delete", id="school"),
    ],
)
async def test_handler_skips_delete_when_old_is_none(
    manager, mock_storage, mock_mapper, event_cls, handler_name, no_call
):
    event = event_cls(timestamp=_TS, sequence_number=1, event_type=EventType.DELETE, old=None, new=None)
    with patch("kelvin_connector.sync.SQLAlchemyDNIDMapper", return_value=mock_mapper):
        await getattr(manager, handler_name)(event)
    attrgetter(no_call)(mock_storage).assert_not_called()


# ── User events ───────────────────────────────────────────────────────────────


async def test_handle_user_create_drops_event_when_school_not_found(manager, mock_storage, mock_mapper):
    mock_storage.schools.search.return_value = []
    event = _user_event(EventType.CREATE, uuid.uuid4())
    with patch("kelvin_connector.sync.SQLAlchemyDNIDMapper", return_value=mock_mapper):
        await manager.handle_user_event(event)
    mock_storage.users.create.assert_not_called()


async def test_handle_user_create_happy_path(manager, mock_storage, mock_mapper):
    uid = uuid.uuid4()
    school = make_school("testschool")
    mock_storage.schools.search.return_value = [school]
    # Ward DN is present but mapper does not know it — exercises the "DN skipped" log path
    event = _user_event(EventType.CREATE, uid, extra_props={"ucsschoolLegalWard": ["uid=ward,dc=test"]})

    with patch("kelvin_connector.sync.SQLAlchemyDNIDMapper", return_value=mock_mapper):
        await manager.handle_user_event(event)

    mock_storage.users.create.assert_called_once()
    created = mock_storage.users.create.call_args[0][0]
    assert created.public_id == uid
    assert created.name == "testuser"
    mock_mapper.set_mapping.assert_called_once_with(
        ObjectType.USER, "uid=testuser,cn=users,dc=test", uid
    )


async def test_handle_user_create_generates_record_uid_and_source_uid(
    manager, mock_storage, mock_mapper
):
    uid = uuid.uuid4()
    school = make_school("testschool")
    mock_storage.schools.search.return_value = [school]
    # Omit ucsschoolRecordUID / ucsschoolSourceUID to trigger default fallback
    props = {
        "univentionObjectIdentifier": str(uid),
        "username": "autouser",
        "firstname": "Auto",
        "lastname": "User",
        "disabled": False,
        "school": ["testschool"],
        "ucsschoolRole": [],
        "groups": [],
        "ucsschoolLegalWard": [],
        "ucsschoolLegalGuardian": [],
    }
    event = UserEvent(
        timestamp=_TS,
        sequence_number=1,
        event_type=EventType.CREATE,
        old=None,
        new={"dn": "uid=autouser,cn=users,dc=test", "properties": props},
    )

    with patch("kelvin_connector.sync.SQLAlchemyDNIDMapper", return_value=mock_mapper):
        await manager.handle_user_event(event)

    created = mock_storage.users.create.call_args[0][0]
    assert created.record_uid == "autouser"
    assert created.source_uid == "UMC"


async def test_handle_user_delete_happy_path(manager, mock_storage, mock_mapper):
    uid = uuid.uuid4()
    event = _user_event(EventType.DELETE, uid)
    with patch("kelvin_connector.sync.SQLAlchemyDNIDMapper", return_value=mock_mapper):
        await manager.handle_user_event(event)
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

    event = _user_event(
        EventType.MODIFY,
        uid,
        extra_props={"firstname": "NewFirst", "school": ["testschool"]},
    )
    with patch("kelvin_connector.sync.SQLAlchemyDNIDMapper", return_value=mock_mapper):
        await manager.handle_user_event(event)

    mock_storage.users.modify.assert_called_once()


async def test_handle_user_modify_skips_modify_when_patch_is_empty(manager, mock_storage, mock_mapper):
    uid = uuid.uuid4()
    current_user = make_user(uid=uid, school_memberships=UNLOADED)
    mock_storage.users.get.return_value = current_user

    # Props match current_user exactly; no membership props → UNLOADED paths exercised
    props = {
        "univentionObjectIdentifier": str(uid),
        "username": "testuser",
        "firstname": "Test",
        "disabled": False,
        "ucsschoolRecordUID": "testuser",
        "ucsschoolSourceUID": "src",
    }
    event = UserEvent(
        timestamp=_TS,
        sequence_number=1,
        event_type=EventType.MODIFY,
        old={"dn": "uid=testuser,dc=test", "properties": {"univentionObjectIdentifier": str(uid)}},
        new={"dn": "uid=testuser,dc=test", "properties": props},
    )
    with patch("kelvin_connector.sync.SQLAlchemyDNIDMapper", return_value=mock_mapper):
        await manager.handle_user_event(event)

    mock_storage.users.modify.assert_not_called()


async def test_handle_user_modify_generates_record_uid_and_source_uid(
    manager, mock_storage, mock_mapper
):
    uid = uuid.uuid4()
    current_user = make_user(uid=uid, school_memberships=UNLOADED)
    current_user.record_uid = "old_record"
    current_user.source_uid = "old_source"
    mock_storage.users.get.return_value = current_user

    # Omit ucsschoolRecordUID / ucsschoolSourceUID — triggers fallback to name / "UMC"
    props = {
        "univentionObjectIdentifier": str(uid),
        "username": "testuser",
        "firstname": "Test",
        "disabled": False,
    }
    event = UserEvent(
        timestamp=_TS,
        sequence_number=1,
        event_type=EventType.MODIFY,
        old={"dn": "uid=testuser,dc=test", "properties": {"univentionObjectIdentifier": str(uid)}},
        new={"dn": "uid=testuser,dc=test", "properties": props},
    )
    with patch("kelvin_connector.sync.SQLAlchemyDNIDMapper", return_value=mock_mapper):
        await manager.handle_user_event(event)

    mock_storage.users.modify.assert_called_once()


def test_apply_user_changes_covers_all_branches(manager):
    uid = uuid.uuid4()
    school = make_school()
    user = make_user(uid=uid, school_memberships=UNLOADED)
    ward = make_user(name="ward", uid=uuid.uuid4())
    membership = SchoolMembership(school=school, is_primary=True, roles=set(), groups=set())

    # school_memberships key is in user_kwargs but must be skipped in the first loop
    manager._apply_user_changes(
        user,
        user_kwargs={"name": "newname", "school_memberships": ["ignored"]},
        school_memberships={school.public_id: membership},
        legal_wards={ward},
        legal_guardians=set(),
    )

    assert user.name == "newname"
    assert user.school_memberships == {school.public_id: membership}
    assert user.legal_wards == {ward}
    assert user.legal_guardians == set()


def test_apply_user_changes_skips_unloaded_fields(manager):
    user = make_user()
    original_memberships = user.school_memberships

    manager._apply_user_changes(
        user,
        user_kwargs={},
        school_memberships=UNLOADED,
        legal_wards=UNLOADED,
        legal_guardians=UNLOADED,
    )

    assert user.school_memberships is original_memberships


# ── Group events ──────────────────────────────────────────────────────────────


async def test_handle_group_create_drops_event_when_school_not_found(manager, mock_storage, mock_mapper):
    mock_storage.schools.search.return_value = []
    event = _group_event(EventType.CREATE, uuid.uuid4())
    with patch("kelvin_connector.sync.SQLAlchemyDNIDMapper", return_value=mock_mapper):
        await manager.handle_group_event(event)
    mock_storage.groups.create.assert_not_called()


async def test_handle_group_create_happy_path(manager, mock_storage, mock_mapper):
    uid = uuid.uuid4()
    school = make_school("testschool")
    mock_storage.schools.search.return_value = [school]
    event = _group_event(EventType.CREATE, uid)

    with patch("kelvin_connector.sync.SQLAlchemyDNIDMapper", return_value=mock_mapper):
        await manager.handle_group_event(event)

    mock_storage.groups.create.assert_called_once()
    created = mock_storage.groups.create.call_args[0][0]
    assert created.public_id == uid
    assert created.name == "testschool-group"
    mock_mapper.set_mapping.assert_called_once_with(
        ObjectType.GROUP, "cn=testschool-group,cn=klassen,dc=test", uid
    )


async def test_handle_group_delete_happy_path(manager, mock_storage, mock_mapper):
    uid = uuid.uuid4()
    event = _group_event(EventType.DELETE, uid)
    with patch("kelvin_connector.sync.SQLAlchemyDNIDMapper", return_value=mock_mapper):
        await manager.handle_group_event(event)
    mock_storage.groups.delete.assert_called_once_with(uid)


async def test_handle_group_modify_calls_modify_when_patch_is_non_empty(
    manager, mock_storage, mock_mapper
):
    uid = uuid.uuid4()
    school = make_school("testschool")
    current_group = make_group("testschool-group", school, uid=uid)
    mock_storage.groups.get.return_value = current_group
    mock_storage.schools.search.return_value = [school]

    # name change + email + all relationship props → exercises non-UNLOADED paths
    event = _group_event(
        EventType.MODIFY,
        uid,
        name="testschool-newgroup",
        extra_props={
            "name": "testschool-newgroup",
            "mailAddress": "grp@example.com",
            "allowedEmailUsers": [],
            "allowedEmailGroups": [],
            "users": [],
            "ucsschoolRole": ["school_class:testschool"],
        },
    )
    with patch("kelvin_connector.sync.SQLAlchemyDNIDMapper", return_value=mock_mapper):
        await manager.handle_group_event(event)

    mock_storage.groups.modify.assert_called_once()


async def test_handle_group_modify_skips_modify_when_patch_is_empty(manager, mock_storage, mock_mapper):
    uid = uuid.uuid4()
    school = make_school("testschool")
    current_group = make_group("testschool-group", school, uid=uid)
    mock_storage.groups.get.return_value = current_group

    # Minimal props: no name/email/relationship keys → all helpers return UNLOADED
    props = {"univentionObjectIdentifier": str(uid)}
    event = GroupEvent(
        timestamp=_TS,
        sequence_number=1,
        event_type=EventType.MODIFY,
        old={
            "dn": "cn=testschool-group,dc=test",
            "properties": {"univentionObjectIdentifier": str(uid)},
        },
        new={"dn": "cn=testschool-group,dc=test", "properties": props},
    )
    with patch("kelvin_connector.sync.SQLAlchemyDNIDMapper", return_value=mock_mapper):
        await manager.handle_group_event(event)

    mock_storage.groups.modify.assert_not_called()


@pytest.mark.parametrize(
    "props,schools_rv",
    [
        pytest.param({}, None, id="name-absent"),
        pytest.param({"name": "testschool-group"}, [], id="school-not-found"),
    ],
)
async def test_maybe_fetch_school_for_group_returns_unloaded(manager, mock_storage, props, schools_rv):
    if schools_rv is not None:
        mock_storage.schools.search.return_value = schools_rv
    result = await manager._maybe_fetch_school_for_group(props, mock_storage)
    assert result is UNLOADED
    if not props:
        mock_storage.schools.search.assert_not_called()


async def test_maybe_fetch_groups_for_prop_returns_unloaded_when_key_absent(
    manager, mock_mapper, mock_storage
):
    result = await manager._maybe_fetch_groups_for_prop(
        {}, "allowedEmailGroups", "Label", mock_mapper, mock_storage
    )
    assert result is UNLOADED
    mock_storage.groups.search.assert_not_called()


async def test_maybe_fetch_group_type_roles_returns_unloaded_when_key_absent(manager, mock_storage):
    result = await manager._maybe_fetch_group_type_roles({}, mock_storage)
    assert result is UNLOADED
    mock_storage.roles.search.assert_not_called()


def test_apply_group_changes_no_name_no_email(manager):
    school = make_school()
    group = make_group("testschool-group", school)
    original_name = group.name

    manager._apply_group_changes(
        group,
        group_kwargs={},
        school=UNLOADED,
        group_type_roles=UNLOADED,
        allowed_email_senders_users=UNLOADED,
        allowed_email_senders_groups=UNLOADED,
        members=UNLOADED,
    )

    assert group.name == original_name
    assert group.email is None


def test_apply_group_changes_updates_name_and_email(manager):
    school = make_school()
    group = make_group("testschool-group", school)
    new_school = make_school("testschool")

    manager._apply_group_changes(
        group,
        group_kwargs={"name": "testschool-newgroup", "email": "grp@example.com"},
        school=new_school,
        group_type_roles=set(),
        allowed_email_senders_users=set(),
        allowed_email_senders_groups=set(),
        members=set(),
    )

    assert group.name == "testschool-newgroup"
    assert group.display_name == "testschool-newgroup"
    assert group.record_uid == "testschool-newgroup"
    assert group.email == "grp@example.com"
    assert group.school is new_school


# ── School events ─────────────────────────────────────────────────────────────


async def test_handle_school_create_happy_path(manager, mock_storage, mock_mapper):
    uid = uuid.uuid4()
    event = _school_event(EventType.CREATE, uid)

    with patch("kelvin_connector.sync.SQLAlchemyDNIDMapper", return_value=mock_mapper):
        await manager.handle_school_event(event)

    mock_storage.schools.create.assert_called_once()
    created = mock_storage.schools.create.call_args[0][0]
    assert created.public_id == uid
    assert created.name == "testschool"
    mock_mapper.set_mapping.assert_called_once_with(ObjectType.SCHOOL, "ou=testschool,dc=test", uid)


async def test_handle_school_delete_happy_path(manager, mock_storage, mock_mapper):
    uid = uuid.uuid4()
    event = _school_event(EventType.DELETE, uid)
    with patch("kelvin_connector.sync.SQLAlchemyDNIDMapper", return_value=mock_mapper):
        await manager.handle_school_event(event)
    mock_storage.schools.delete.assert_called_once_with(uid)


async def test_handle_school_modify_calls_modify_when_patch_is_non_empty(
    manager, mock_storage, mock_mapper
):
    uid = uuid.uuid4()
    current_school = make_school("testschool", uid=uid)
    current_school.display_name = "Old Display"
    mock_storage.schools.get.return_value = current_school

    event = _school_event(EventType.MODIFY, uid, extra_props={"displayName": "New Display"})
    with patch("kelvin_connector.sync.SQLAlchemyDNIDMapper", return_value=mock_mapper):
        await manager.handle_school_event(event)

    mock_storage.schools.modify.assert_called_once()


async def test_handle_school_modify_skips_modify_when_patch_is_empty(manager, mock_storage, mock_mapper):
    uid = uuid.uuid4()
    current_school = make_school("testschool", uid=uid)
    current_school.display_name = "testschool Display"
    mock_storage.schools.get.return_value = current_school

    # Props produce the same values already on current_school → empty patch
    event = _school_event(EventType.MODIFY, uid)
    with patch("kelvin_connector.sync.SQLAlchemyDNIDMapper", return_value=mock_mapper):
        await manager.handle_school_event(event)

    mock_storage.schools.modify.assert_not_called()
