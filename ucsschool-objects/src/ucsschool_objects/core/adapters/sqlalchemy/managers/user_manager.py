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
    _bulk_fetch_by_public_id,
    _check_nullable_value_presence,
    _check_value_presence,
    _compose_field_map,
    _get_exposed_fields,
    _load_requested_scalar_attributes,
    _role_scalar_columns,
    _school_scalar_columns,
)
from ucsschool_objects.core.adapters.sqlalchemy.mapping import to_user
from ucsschool_objects.core.adapters.sqlalchemy.query_filter import apply_search_query, apply_sort
from ucsschool_objects.core.domain import (
    LoadSpec,
    NotFound,
    SchoolMembership as DomainSchoolMembership,
    SearchQuery,
    SortSpec,
    UnloadedType,
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

    async def _build_memberships(
        self,
        memberships: dict[UUID, DomainSchoolMembership] | UnloadedType,
    ) -> list[SchoolMembership]:
        if isinstance(memberships, UnloadedType):
            return []

        # Validate and extract typed UUIDs in one pass to preserve mypy narrowing
        ValidatedMembership = tuple[DomainSchoolMembership, UUID, list[UUID], list[UUID]]
        validated: list[ValidatedMembership] = []
        school_ids: list[UUID] = []
        all_role_ids: list[UUID] = []
        all_group_ids: list[UUID] = []
        for membership_school_id, m in memberships.items():
            school = m.school
            if isinstance(school, UnloadedType) or not isinstance(school.public_id, UUID):
                raise ValueError("All membership schools must be loaded with public_id for create().")
            school_id: UUID = school.public_id
            if membership_school_id != school_id:
                raise ValueError("school_memberships keys must match membership school public_id.")
            role_ids: list[UUID] = []
            for r in m.roles:
                if not isinstance(r.public_id, UUID):
                    raise ValueError("All membership roles must provide public_id for create().")
                role_ids.append(r.public_id)
            group_ids: list[UUID] = []
            for g in m.groups:
                if not isinstance(g.public_id, UUID):
                    raise ValueError("All membership groups must provide public_id for create().")
                group_ids.append(g.public_id)
            validated.append((m, school_id, role_ids, group_ids))
            school_ids.append(school_id)
            all_role_ids.extend(role_ids)
            all_group_ids.extend(group_ids)

        schools_by_id = await _bulk_fetch_by_public_id(self._session, SchoolModel, school_ids, "School")
        roles_by_id = await _bulk_fetch_by_public_id(self._session, RoleModel, all_role_ids, "Role")
        groups_by_id = await _bulk_fetch_by_public_id(self._session, GroupModel, all_group_ids, "Group")

        membership_models: list[SchoolMembership] = []
        for m, school_id, role_ids, group_ids in validated:
            membership_model = SchoolMembership(
                is_primary=m.is_primary,
                school=schools_by_id[school_id],
            )
            membership_model.roles = [roles_by_id[rid] for rid in role_ids]
            membership_model.groups = [groups_by_id[gid] for gid in group_ids]
            membership_models.append(membership_model)
        return membership_models

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
        user_model = UserModel(
            record_uid=_check_value_presence(
                data.record_uid, object_type="User", field_name="record_uid"
            ),
            source_uid=_check_value_presence(
                data.source_uid, object_type="User", field_name="source_uid"
            ),
            name=_check_value_presence(data.name, object_type="User", field_name="name"),
            firstname=_check_value_presence(data.firstname, object_type="User", field_name="firstname"),
            lastname=_check_value_presence(data.lastname, object_type="User", field_name="lastname"),
            active=_check_value_presence(data.active, object_type="User", field_name="active"),
            email=_check_nullable_value_presence(data.email, object_type="User", field_name="email"),
            birthday=_check_nullable_value_presence(
                data.birthday, object_type="User", field_name="birthday"
            ),
            expiration_date=_check_nullable_value_presence(
                data.expiration_date, object_type="User", field_name="expiration_date"
            ),
        )
        if isinstance(data.public_id, UUID):
            user_model.public_id = data.public_id

        user_model.school_memberships = await self._build_memberships(data.school_memberships)

        if not isinstance(data.legal_wards, UnloadedType):
            ward_ids = [u.public_id for u in data.legal_wards if isinstance(u.public_id, UUID)]
            wards_by_id = await _bulk_fetch_by_public_id(self._session, UserModel, ward_ids, "User")
            user_model.legal_wards = list(wards_by_id.values())
        if not isinstance(data.legal_guardians, UnloadedType):
            guardian_ids = [u.public_id for u in data.legal_guardians if isinstance(u.public_id, UUID)]
            guardians_by_id = await _bulk_fetch_by_public_id(
                self._session, UserModel, guardian_ids, "User"
            )
            user_model.legal_guardians = list(guardians_by_id.values())

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
