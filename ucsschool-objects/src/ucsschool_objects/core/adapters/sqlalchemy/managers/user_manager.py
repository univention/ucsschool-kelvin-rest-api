from __future__ import annotations

from collections.abc import Iterable, Sequence
from typing import Any
from uuid import UUID

from sqlalchemy import Select, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from sqlalchemy.orm.attributes import InstrumentedAttribute
from ucsschool_objects.core.adapters.sqlalchemy.managers._shared import (
    FieldColumn,
    JoinSpec,
    JoinType,
    _compose_field_map,
    _get_exposed_fields,
    _load_requested_scalar_attributes,
    _role_scalar_columns,
    _school_scalar_columns,
)
from ucsschool_objects.core.adapters.sqlalchemy.mappers.to_domain import to_user
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
    User,
)
from ucsschool_objects.core.domain.ports.manager import JSONPathOperation, Manager
from ucsschool_objects.database_models import (
    Group as GroupModel,
    Role as RoleModel,
    School as SchoolModel,
    SchoolMembership,
    User as UserModel,
)

__all__ = ["SQLAlchemyUserManager"]


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
        raise NotImplementedError("User modify is not implemented yet.")  # pragma: no cover

    async def delete(self, public_id: UUID) -> None:
        raise NotImplementedError("User delete is not implemented yet.")  # pragma: no cover
