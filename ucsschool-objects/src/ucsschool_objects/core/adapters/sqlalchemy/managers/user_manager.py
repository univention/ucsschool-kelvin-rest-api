from __future__ import annotations

from datetime import date
from typing import TYPE_CHECKING, cast
from uuid import UUID

from sqlalchemy import Select, delete, select
from sqlalchemy.engine import CursorResult
from sqlalchemy.orm import selectinload
from ucsschool_objects.core.adapters.sqlalchemy.managers._shared import (
    FieldColumn,
    JoinSpec,
    JoinType,
    PublicIdInput,
    apply_patch,
    bulk_fetch_by_public_id,
    compose_field_map,
    extract_public_ids,
    fetch_one_by_public_id,
    get_exposed_fields,
    load_requested_scalar_attributes,
    role_scalar_columns,
    school_scalar_columns,
    sync_collection,
)
from ucsschool_objects.core.adapters.sqlalchemy.mappers.to_domain import to_user, user_from_patch
from ucsschool_objects.core.adapters.sqlalchemy.mappers.to_orm import (
    resolve_user_create_relations,
    to_user_model,
)
from ucsschool_objects.core.adapters.sqlalchemy.query_filter import apply_search_query, apply_sort
from ucsschool_objects.core.domain.errors import NotFound, UnsupportedOperation
from ucsschool_objects.core.domain.json import PatchDict, to_json
from ucsschool_objects.core.domain.load_spec import LoadSpec
from ucsschool_objects.core.domain.models import User
from ucsschool_objects.core.domain.ports.manager import JSONPathOperation, Manager
from ucsschool_objects.core.domain.query import SearchQuery, SortSpec
from ucsschool_objects.core.domain.validators import UserValidator
from ucsschool_objects.database_models import (
    Group as GroupModel,
    Role as RoleModel,
    School as SchoolModel,
    SchoolMembership,
    User as UserModel,
)

if TYPE_CHECKING:
    from collections.abc import Iterable, Sequence

    from sqlalchemy.ext.asyncio import AsyncSession
    from sqlalchemy.orm.attributes import InstrumentedAttribute


async def _apply_membership_relation_changes(
    model: UserModel,
    current_memberships: PatchDict,
    patched_memberships: PatchDict,
    session: AsyncSession,
) -> None:
    memberships_by_school = {m.school.public_id: m for m in model.school_memberships}
    for school_uuid_str, patched_m in patched_memberships.items():
        current_membership = cast(PatchDict, current_memberships.get(school_uuid_str, {}))
        patched_membership = cast(PatchDict, patched_m)
        school_uuid = UUID(school_uuid_str)
        orm_membership = memberships_by_school.get(school_uuid)
        if orm_membership is None:
            school_model = await fetch_one_by_public_id(
                session, SchoolModel, school_uuid, SchoolModel.__name__
            )
            orm_membership = SchoolMembership(
                school=school_model,
                is_primary=cast(bool, patched_membership.get("is_primary", False)),
            )
            # Initialise the lazy="raise" collections while the object is still
            # transient — once appended (and thus pending), assigning them would
            # trigger a load of the current value and raise.
            orm_membership.groups = []
            orm_membership.roles = []
            model.school_memberships.append(orm_membership)

        current_group_ids = extract_public_ids(
            cast(list[PublicIdInput], current_membership.get("groups", []))
        )
        patched_group_ids = extract_public_ids(
            cast(list[PublicIdInput], patched_membership.get("groups", []))
        )
        if current_group_ids != patched_group_ids:
            if patched_group_ids:
                group_records = await bulk_fetch_by_public_id(
                    session,
                    GroupModel,
                    list(patched_group_ids),
                    GroupModel.__name__,
                )
                orm_membership.groups = list(group_records.values())
            else:
                orm_membership.groups = []

        current_role_ids = extract_public_ids(
            cast(list[PublicIdInput], current_membership.get("roles", []))
        )
        patched_role_ids = extract_public_ids(
            cast(list[PublicIdInput], patched_membership.get("roles", []))
        )
        if current_role_ids != patched_role_ids:
            if patched_role_ids:
                role_records = await bulk_fetch_by_public_id(
                    session,
                    RoleModel,
                    list(patched_role_ids),
                    RoleModel.__name__,
                )
                orm_membership.roles = list(role_records.values())
            else:
                orm_membership.roles = []

    removed_school_uuids = {UUID(key) for key in current_memberships} - {
        UUID(key) for key in patched_memberships
    }
    for school_uuid in removed_school_uuids:
        orm_membership = memberships_by_school[school_uuid]
        model.school_memberships.remove(orm_membership)
        await session.delete(orm_membership)


def _apply_user_patch(model: UserModel, patched: PatchDict) -> None:
    model.record_uid = cast(str, patched["record_uid"])
    model.source_uid = cast(str, patched["source_uid"])
    model.name = cast(str, patched["name"])
    model.firstname = cast(str, patched["firstname"])
    model.lastname = cast(str, patched["lastname"])
    model.email = cast(str | None, patched["email"])
    model.active = cast(bool, patched["active"])
    birthday_val = patched["birthday"]
    model.birthday = date.fromisoformat(cast(str, birthday_val)) if birthday_val is not None else None
    exp_val = patched["expiration_date"]
    model.expiration_date = date.fromisoformat(cast(str, exp_val)) if exp_val is not None else None


def _includes_user_memberships(load: LoadSpec) -> bool:
    return any(
        load.includes(attribute)
        for attribute in ("school_memberships", "primary_school", "groups", "roles")
    )


def _group_scalar_columns() -> tuple[InstrumentedAttribute[object], ...]:
    return (
        GroupModel.record_uid,
        GroupModel.source_uid,
        GroupModel.name,
        GroupModel.display_name,
        GroupModel.has_share,
        GroupModel.email,
    )


def _user_scalar_columns() -> tuple[InstrumentedAttribute[object], ...]:
    return (
        UserModel.record_uid,
        UserModel.source_uid,
        UserModel.name,
        UserModel.firstname,
        UserModel.lastname,
        UserModel.email,
        UserModel.birthday,
        UserModel.expiration_date,
        UserModel.active,
    )


def _with_user_related_load_options(
    stmt: Select[tuple[UserModel]], load: LoadSpec
) -> Select[tuple[UserModel]]:
    if _includes_user_memberships(load):
        membership_loader = selectinload(UserModel.school_memberships)
        stmt = stmt.options(membership_loader.load_only(SchoolMembership.is_primary))
        stmt = stmt.options(
            membership_loader.selectinload(SchoolMembership.school).load_only(
                SchoolModel.public_id,
                *school_scalar_columns(),
            )
        )
        stmt = stmt.options(
            membership_loader.selectinload(SchoolMembership.groups)
            .load_only(GroupModel.public_id, *_group_scalar_columns())
            .selectinload(GroupModel.roles)
            .load_only(RoleModel.public_id, *role_scalar_columns())
        )
        stmt = stmt.options(
            membership_loader.selectinload(SchoolMembership.roles).load_only(
                RoleModel.public_id,
                *role_scalar_columns(),
            )
        )
    if load.includes("legal_wards"):
        stmt = stmt.options(
            selectinload(UserModel.legal_wards).load_only(UserModel.public_id, *_user_scalar_columns())
        )
    if load.includes("legal_guardians"):
        stmt = stmt.options(
            selectinload(UserModel.legal_guardians).load_only(
                UserModel.public_id,
                *_user_scalar_columns(),
            )
        )
    return stmt


def _with_user_load_options(
    stmt: Select[tuple[UserModel]],
    load: LoadSpec,
    attribute_map: dict[str, FieldColumn],
) -> Select[tuple[UserModel]]:
    stmt = load_requested_scalar_attributes(
        stmt,
        UserModel.public_id,
        load,
        attribute_map,
    )
    return _with_user_related_load_options(stmt, load)


def _classify_patch_operation(parts: list[str]) -> str | None:
    """Classify one patch path: which relation does it touch, if any?

    Returns the relation name ("school_memberships", "legal_guardians" or
    "legal_wards") when the path needs relation handling, or None for plain
    scalar attributes (e.g. "/name").

    One rule governs all relations: memberships, guardians, wards, and a
    membership's groups/roles can be *linked and unlinked*, but the related
    objects themselves cannot be changed through a user patch. Paths that
    reach into a related object's attributes are rejected.

    Note that this is enforced on paths only. Op *values* may carry full
    object representations (patches generated by ``track_changes`` always
    do); references in them are resolved by public_id alone and all other
    fields are deliberately ignored, not rejected — detecting a value that
    deviates from the stored object would require fetching and diffing
    every referenced object.
    """
    top = parts[0]
    depth = len(parts)
    if top == "school_memberships":
        if depth <= 2:
            # /school_memberships             — replace the whole mapping
            # /school_memberships/<school_id> — add/remove/replace one membership
            return top
        if depth <= 4 and parts[2] in ("groups", "roles"):
            # /school_memberships/<school_id>/groups       — replace the reference list
            # /school_memberships/<school_id>/groups/<idx> — link/unlink one reference
            # (likewise for .../roles)
            return top
        # Deeper paths target a membership attribute (e.g. is_primary, school)
        # or the contents of a referenced group/role.
        raise UnsupportedOperation(f"Modifying {top!r} via patch is not supported.")
    if top in ("legal_guardians", "legal_wards"):
        if depth <= 2:
            # /legal_guardians       — replace the whole list
            # /legal_guardians/<idx> — link/unlink one reference
            return top
        # Deeper paths target attributes of the referenced user.
        raise UnsupportedOperation(f"Modifying {top!r} via patch is not supported.")
    # Scalar user attribute (e.g. /name, /email) — no relation handling needed.
    return None


class SQLAlchemyUserManager(Manager[User]):
    _SCALAR_FIELD_MAP: dict[str, FieldColumn] = {
        "record_uid": UserModel.record_uid,
        "source_uid": UserModel.source_uid,
        "name": UserModel.name,
        "firstname": UserModel.firstname,
        "lastname": UserModel.lastname,
        "email": UserModel.email,
        "active": UserModel.active,
        "birthday": UserModel.birthday,
        "expiration_date": UserModel.expiration_date,
    }
    _NESTED_FIELD_REGISTRY: dict[str, JoinSpec] = {
        "groups": JoinSpec(
            relation_name="groups",
            target_model=GroupModel,
            join_path=(SchoolMembership, GroupModel),
            join_type=JoinType.LEFT_OUTER,
            exposed_fields=get_exposed_fields(GroupModel),
        ),
        "roles": JoinSpec(
            relation_name="roles",
            target_model=RoleModel,
            join_path=(SchoolMembership, RoleModel),
            join_type=JoinType.LEFT_OUTER,
            exposed_fields=get_exposed_fields(RoleModel),
        ),
        "schools": JoinSpec(
            relation_name="schools",
            target_model=SchoolModel,
            join_path=(SchoolMembership, SchoolModel),
            join_type=JoinType.LEFT_OUTER,
            exposed_fields=get_exposed_fields(SchoolModel),
        ),
    }
    _BASE_FIELD_MAP: dict[str, FieldColumn] = {
        "public_id": UserModel.public_id,
        **_SCALAR_FIELD_MAP,
    }
    _LOAD_ATTRIBUTE_MAP: dict[str, FieldColumn] = {
        **_SCALAR_FIELD_MAP,
    }
    _FIELD_MAP: dict[str, FieldColumn] = compose_field_map(
        _BASE_FIELD_MAP,
        _NESTED_FIELD_REGISTRY,
    )

    def __init__(self, session: AsyncSession):
        self._session = session

    def _check_modify_operations(
        self, operations: Sequence[JSONPathOperation]
    ) -> tuple[bool, bool, bool]:
        flags: dict[str, bool] = {
            "school_memberships": False,
            "legal_guardians": False,
            "legal_wards": False,
        }
        for op in operations:
            key = _classify_patch_operation(op["path"].lstrip("/").split("/"))
            if key is not None:
                flags[key] = True
        return flags["school_memberships"], flags["legal_guardians"], flags["legal_wards"]

    def _modify_query(
        self,
        public_id: UUID,
        modifies_memberships: bool,
        modifies_guardians: bool,
        modifies_wards: bool,
    ) -> Select[tuple[UserModel]]:
        stmt = select(UserModel).where(UserModel.public_id == public_id)
        if modifies_memberships:
            stmt = stmt.options(
                selectinload(UserModel.school_memberships).selectinload(SchoolMembership.school),
                selectinload(UserModel.school_memberships).selectinload(SchoolMembership.groups),
                selectinload(UserModel.school_memberships).selectinload(SchoolMembership.roles),
            )
        if modifies_guardians:
            stmt = stmt.options(selectinload(UserModel.legal_guardians))
        if modifies_wards:
            stmt = stmt.options(selectinload(UserModel.legal_wards))
        return stmt

    async def get(self, public_id: UUID, *, load: LoadSpec | None = None) -> User:
        stmt = select(UserModel).where(UserModel.public_id == public_id)
        if load is not None:
            stmt = _with_user_load_options(stmt, load, self._LOAD_ATTRIBUTE_MAP)
        result = (await self._session.execute(stmt)).scalar_one_or_none()
        if result is None:
            raise NotFound(object_type="User", public_id=str(public_id))
        spec = load or LoadSpec()
        return to_user(
            result,
            include_memberships=_includes_user_memberships(spec),
            include_legal_wards=spec.includes("legal_wards"),
            include_legal_guardians=spec.includes("legal_guardians"),
        )

    async def search(
        self,
        query: SearchQuery | None = None,
        *,
        sort_by: Sequence[SortSpec] = (),
        limit: int = 50,
        offset: int = 0,
        load: LoadSpec | None = None,
    ) -> Iterable[User]:
        stmt = select(UserModel)
        if load is not None:
            stmt = _with_user_load_options(stmt, load, self._LOAD_ATTRIBUTE_MAP)
        stmt = apply_search_query(stmt, query, self._FIELD_MAP, self._NESTED_FIELD_REGISTRY)
        stmt = apply_sort(
            stmt,
            sort_by,
            self._FIELD_MAP,
            default_field="public_id",
            registry=self._NESTED_FIELD_REGISTRY,
        )
        stmt = stmt.limit(limit).offset(offset)
        spec = load or LoadSpec()

        return (
            to_user(
                model,
                include_memberships=_includes_user_memberships(spec),
                include_legal_wards=spec.includes("legal_wards"),
                include_legal_guardians=spec.includes("legal_guardians"),
            )
            for model in (await self._session.execute(stmt)).scalars()
        )

    async def create(
        self,
        data: User,
    ) -> None:
        user_model = to_user_model(data)
        relations = await resolve_user_create_relations(self._session, data)
        user_model.school_memberships = relations.school_memberships
        if relations.legal_wards is not None:
            user_model.legal_wards = relations.legal_wards
        if relations.legal_guardians is not None:
            user_model.legal_guardians = relations.legal_guardians

        self._session.add(user_model)
        await self._session.flush()

    async def modify(
        self,
        public_id: UUID,
        operations: Sequence[JSONPathOperation],
    ) -> None:
        m_memberships, m_guardians, m_wards = self._check_modify_operations(operations)

        stmt = self._modify_query(public_id, m_memberships, m_guardians, m_wards)
        result = (await self._session.execute(stmt)).scalar_one_or_none()
        if result is None:
            raise NotFound(object_type="User", public_id=str(public_id))

        current_domain = to_user(
            result,
            include_memberships=m_memberships,
            include_legal_wards=m_wards,
            include_legal_guardians=m_guardians,
        )
        patched = apply_patch(operations=operations, current_domain_obj=current_domain)
        UserValidator.validate(user_from_patch(patched, result.public_id))

        _apply_user_patch(result, patched)

        if m_memberships:
            current_dict = to_json(current_domain)
            await _apply_membership_relation_changes(
                result,
                cast(PatchDict, current_dict.get("school_memberships", {})),
                cast(PatchDict, patched.get("school_memberships", {})),
                self._session,
            )
        if m_guardians:
            current_dict = to_json(current_domain)
            await sync_collection(
                self._session,
                cast(list[PublicIdInput], patched.get("legal_guardians", [])),
                cast(list[PublicIdInput], current_dict.get("legal_guardians", [])),
                UserModel,
                lambda values: setattr(result, "legal_guardians", values),
            )
        if m_wards:
            current_dict = to_json(current_domain)
            await sync_collection(
                self._session,
                cast(list[PublicIdInput], patched.get("legal_wards", [])),
                cast(list[PublicIdInput], current_dict.get("legal_wards", [])),
                UserModel,
                lambda values: setattr(result, "legal_wards", values),
            )

    async def delete(self, public_id: UUID) -> None:
        stmt = delete(UserModel).where(UserModel.public_id == public_id)
        result = cast(CursorResult[None], await self._session.execute(stmt))
        if result.rowcount == 0:
            raise NotFound(object_type="User", public_id=str(public_id))
