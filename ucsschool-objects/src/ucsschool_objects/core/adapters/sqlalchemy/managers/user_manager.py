from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import asdict
from datetime import date
from typing import Any, cast
from uuid import UUID

from jsonpatch import JsonPatch  # type: ignore[import-untyped]
from sqlalchemy import Select, delete, select
from sqlalchemy.engine import CursorResult
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from sqlalchemy.orm.attributes import InstrumentedAttribute
from ucsschool_objects.core.adapters.sqlalchemy.managers._shared import (
    FieldColumn,
    JoinSpec,
    JoinType,
    _compose_field_map,
    _extract_public_ids,
    _get_exposed_fields,
    _load_requested_scalar_attributes,
    _role_scalar_columns,
    _school_scalar_columns,
)
from ucsschool_objects.core.adapters.sqlalchemy.mappers.to_domain import to_user, user_from_patch
from ucsschool_objects.core.adapters.sqlalchemy.mappers.to_orm import (
    resolve_user_create_relations,
    to_user_model,
)
from ucsschool_objects.core.adapters.sqlalchemy.query_filter import apply_search_query, apply_sort
from ucsschool_objects.core.domain import (
    LoadSpec,
    NotFound,
    SearchQuery,
    SortSpec,
    UnsupportedOperation,
    User,
    UserValidator,
)
from ucsschool_objects.core.domain.patch import normalise
from ucsschool_objects.core.domain.ports.manager import JSONPathOperation, Manager
from ucsschool_objects.database_models import (
    Group as GroupModel,
    Role as RoleModel,
    School as SchoolModel,
    SchoolMembership,
    User as UserModel,
)

__all__ = ["SQLAlchemyUserManager"]


async def _apply_membership_group_changes(
    model: UserModel,
    current_memberships: dict[str, object],
    patched_memberships: dict[str, object],
    session: AsyncSession,
) -> None:
    memberships_by_school = {m.school.public_id: m for m in model.school_memberships}
    for school_uuid_str, patched_m in patched_memberships.items():
        current_m = cast(dict[str, object], current_memberships.get(school_uuid_str, {}))
        current_group_ids = _extract_public_ids(cast(list[object], current_m.get("groups", [])))
        patched_group_ids = _extract_public_ids(
            cast(list[object], cast(dict[str, object], patched_m).get("groups", []))
        )
        if current_group_ids == patched_group_ids:
            continue

        school_uuid = UUID(school_uuid_str)
        orm_membership = memberships_by_school.get(school_uuid)
        if orm_membership is None:  # pragma: no cover
            continue

        if patched_group_ids:
            groups_result = await session.execute(
                select(GroupModel).where(GroupModel.public_id.in_(patched_group_ids))
            )
            orm_membership.groups = list(groups_result.scalars())
        else:
            orm_membership.groups = []


async def _apply_legal_relation_changes(
    model: UserModel,
    relation: str,
    current_list: list[object],
    patched_list: list[object],
    session: AsyncSession,
) -> None:
    current_ids = _extract_public_ids(current_list)
    patched_ids = _extract_public_ids(patched_list)
    if current_ids == patched_ids:
        return

    if patched_ids:
        users_result = await session.execute(
            select(UserModel).where(UserModel.public_id.in_(patched_ids))
        )
        new_users = list(users_result.scalars())
    else:
        new_users = []
    setattr(model, relation, new_users)


def _apply_user_patch(model: UserModel, patched: dict[str, object]) -> None:
    for field in ("record_uid", "source_uid", "name", "firstname", "lastname", "email", "active"):
        setattr(model, field, patched[field])
    birthday_val = patched["birthday"]
    model.birthday = date.fromisoformat(cast(str, birthday_val)) if birthday_val is not None else None
    exp_val = patched["expiration_date"]
    model.expiration_date = date.fromisoformat(cast(str, exp_val)) if exp_val is not None else None


def _includes_user_memberships(load: LoadSpec) -> bool:
    return any(
        load.includes(attribute)
        for attribute in ("school_memberships", "primary_school", "groups", "roles")
    )


def _group_scalar_columns() -> tuple[InstrumentedAttribute[Any], ...]:
    return (
        GroupModel.record_uid,
        GroupModel.source_uid,
        GroupModel.name,
        GroupModel.display_name,
        GroupModel.has_share,
        GroupModel.email,
    )


def _user_scalar_columns() -> tuple[InstrumentedAttribute[Any], ...]:
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
                *_school_scalar_columns(),
            )
        )
        stmt = stmt.options(
            membership_loader.selectinload(SchoolMembership.groups).load_only(
                GroupModel.public_id,
                *_group_scalar_columns(),
            )
        )
        stmt = stmt.options(
            membership_loader.selectinload(SchoolMembership.roles).load_only(
                RoleModel.public_id,
                *_role_scalar_columns(),
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


def _with_user_load_options(stmt: Select[tuple[UserModel]], load: LoadSpec) -> Select[tuple[UserModel]]:
    stmt = _load_requested_scalar_attributes(
        stmt,
        UserModel.public_id,
        load,
        SQLAlchemyUserManager._LOAD_ATTRIBUTE_MAP,
    )
    return _with_user_related_load_options(stmt, load)


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
            exposed_fields=_get_exposed_fields(GroupModel),
        ),
        "roles": JoinSpec(
            relation_name="roles",
            target_model=RoleModel,
            join_path=(SchoolMembership, RoleModel),
            join_type=JoinType.LEFT_OUTER,
            exposed_fields=_get_exposed_fields(RoleModel),
        ),
        "schools": JoinSpec(
            relation_name="schools",
            target_model=SchoolModel,
            join_path=(SchoolMembership, SchoolModel),
            join_type=JoinType.LEFT_OUTER,
            exposed_fields=_get_exposed_fields(SchoolModel),
        ),
    }
    _BASE_FIELD_MAP: dict[str, FieldColumn] = {
        "public_id": UserModel.public_id,
        **_SCALAR_FIELD_MAP,
    }
    _LOAD_ATTRIBUTE_MAP: dict[str, FieldColumn] = {
        **_SCALAR_FIELD_MAP,
    }
    _FIELD_MAP: dict[str, FieldColumn] = _compose_field_map(
        _BASE_FIELD_MAP,
        _NESTED_FIELD_REGISTRY,
    )

    def __init__(self, session: AsyncSession):
        self._session = session

    async def get(self, public_id: UUID, *, load: LoadSpec | None = None) -> User:
        stmt = select(UserModel).where(UserModel.public_id == public_id)
        if load is not None:
            stmt = _with_user_load_options(stmt, load)
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
            stmt = _with_user_load_options(stmt, load)
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
        modifies_memberships = False
        modifies_guardians = False
        modifies_wards = False

        for op in operations:
            parts = op["path"].lstrip("/").split("/")
            top = parts[0]
            depth = len(parts)

            if top == "school_memberships":
                if depth >= 3 and parts[2] == "groups" and depth <= 4:
                    modifies_memberships = True
                else:
                    raise UnsupportedOperation(f"Modifying {top!r} via patch is not supported.")
            elif top == "legal_guardians":
                if depth <= 2:
                    modifies_guardians = True
                else:
                    raise UnsupportedOperation(f"Modifying {top!r} via patch is not supported.")
            elif top == "legal_wards":
                if depth <= 2:
                    modifies_wards = True
                else:
                    raise UnsupportedOperation(f"Modifying {top!r} via patch is not supported.")

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

        result = (await self._session.execute(stmt)).scalar_one_or_none()
        if result is None:
            raise NotFound(object_type="User", public_id=str(public_id))

        current = cast(
            dict[str, object],
            normalise(
                asdict(
                    to_user(
                        result,
                        include_memberships=modifies_memberships,
                        include_legal_wards=modifies_wards,
                        include_legal_guardians=modifies_guardians,
                    )
                )
            ),
        )
        patched = cast(dict[str, object], JsonPatch(list(operations)).apply(current))
        UserValidator.validate(user_from_patch(patched, result.public_id))
        _apply_user_patch(result, patched)

        if modifies_memberships:
            await _apply_membership_group_changes(
                result,
                cast(dict[str, object], current.get("school_memberships", {})),
                cast(dict[str, object], patched.get("school_memberships", {})),
                self._session,
            )
        if modifies_guardians:
            await _apply_legal_relation_changes(
                result,
                "legal_guardians",
                cast(list[object], current.get("legal_guardians", [])),
                cast(list[object], patched.get("legal_guardians", [])),
                self._session,
            )
        if modifies_wards:
            await _apply_legal_relation_changes(
                result,
                "legal_wards",
                cast(list[object], current.get("legal_wards", [])),
                cast(list[object], patched.get("legal_wards", [])),
                self._session,
            )

    async def delete(self, public_id: UUID) -> None:
        stmt = delete(UserModel).where(UserModel.public_id == public_id)
        result = cast(CursorResult[Any], await self._session.execute(stmt))
        if result.rowcount == 0:
            raise NotFound(object_type="User", public_id=str(public_id))
