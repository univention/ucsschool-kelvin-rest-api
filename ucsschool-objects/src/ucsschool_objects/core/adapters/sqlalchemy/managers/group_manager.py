from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import asdict
from typing import Any, cast
from uuid import UUID

from jsonpatch import JsonPatch  # type: ignore[import-untyped]
from sqlalchemy import Select, delete, select
from sqlalchemy.engine import CursorResult
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
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
from ucsschool_objects.core.adapters.sqlalchemy.mappers.to_domain import group_from_patch, to_group
from ucsschool_objects.core.adapters.sqlalchemy.mappers.to_orm import (
    resolve_group_create_relations,
    to_group_model,
)
from ucsschool_objects.core.adapters.sqlalchemy.query_filter import apply_search_query, apply_sort
from ucsschool_objects.core.domain import (
    Group,
    GroupValidator,
    LoadSpec,
    NotFound,
    Role,
    SearchQuery,
    SortSpec,
    UnsupportedOperation,
)
from ucsschool_objects.core.domain.patch import normalise
from ucsschool_objects.core.domain.ports.manager import JSONPathOperation, Manager
from ucsschool_objects.database_models import (
    Group as GroupModel,
    GroupType as GroupTypeModel,
    Role as RoleModel,
    School as SchoolModel,
    SchoolMembership as SchoolMembershipModel,
    User as UserModel,
)

__all__ = ["SQLAlchemyGroupManager"]


async def _apply_group_patch(
    model: GroupModel,
    patched: dict[str, object],
    current: dict[str, object],
    session: AsyncSession,
) -> None:
    for field in ("record_uid", "source_uid", "name", "display_name", "email"):
        setattr(model, field, patched[field])
    model.has_share = cast(bool, patched["create_share"])

    if patched["member_roles"] != current["member_roles"]:
        role_ids = [cast(Role, r).public_id for r in cast(list[object], patched["member_roles"])]
        roles_result = await session.execute(select(RoleModel).where(RoleModel.public_id.in_(role_ids)))
        model.member_roles = list(roles_result.scalars())

    if patched["group_type"] != current["group_type"]:
        gt_result = await session.execute(
            select(GroupTypeModel).where(GroupTypeModel.name == patched["group_type"])
        )
        new_gt = gt_result.scalar_one_or_none()
        if new_gt is None:
            raise NotFound(object_type="GroupType", public_id=str(patched["group_type"]))
        model.group_type = new_gt


class SQLAlchemyGroupManager(Manager[Group]):
    _SCALAR_FIELD_MAP: dict[str, FieldColumn] = {
        "record_uid": GroupModel.record_uid,
        "source_uid": GroupModel.source_uid,
        "name": GroupModel.name,
        "email": GroupModel.email,
    }
    _NESTED_FIELD_REGISTRY: dict[str, JoinSpec] = {
        "school": JoinSpec(
            relation_name="school",
            target_model=SchoolModel,
            join_path=(SchoolModel,),
            join_type=JoinType.LEFT_OUTER,
            exposed_fields=_get_exposed_fields(SchoolModel),
        ),
    }
    _BASE_FIELD_MAP: dict[str, FieldColumn] = {
        "public_id": GroupModel.public_id,
        **_SCALAR_FIELD_MAP,
    }
    _LOAD_ATTRIBUTE_MAP: dict[str, FieldColumn] = {
        **_SCALAR_FIELD_MAP,
        "display_name": GroupModel.display_name,
        "create_share": GroupModel.has_share,
    }
    _FIELD_MAP: dict[str, FieldColumn] = _compose_field_map(
        _BASE_FIELD_MAP,
        _NESTED_FIELD_REGISTRY,
    )

    def __init__(self, session: AsyncSession):
        self._session = session

    def _base_stmt(self, load: LoadSpec | None) -> Select[tuple[GroupModel]]:
        stmt = select(GroupModel)
        stmt = _load_requested_scalar_attributes(
            stmt,
            GroupModel.public_id,
            load,
            self._LOAD_ATTRIBUTE_MAP,
        )
        if load is not None and load.includes("group_type"):
            stmt = stmt.options(selectinload(GroupModel.group_type).load_only(GroupTypeModel.name))
        if load is not None and load.includes("allowed_email_senders_users"):
            stmt = stmt.options(
                selectinload(GroupModel.allowed_email_senders_users).load_only(
                    UserModel.public_id, UserModel.name
                )
            )
        if load is not None and load.includes("allowed_email_senders_groups"):
            stmt = stmt.options(
                selectinload(GroupModel.allowed_email_senders_groups).load_only(
                    GroupModel.public_id,
                    GroupModel.name,
                )
            )
        if load is not None and load.includes("members"):
            stmt = stmt.options(
                selectinload(GroupModel.members)
                .selectinload(SchoolMembershipModel.user)
                .load_only(UserModel.public_id, UserModel.name)
            )
        if load is not None and load.includes("member_roles"):
            stmt = stmt.options(
                selectinload(GroupModel.member_roles).load_only(
                    RoleModel.public_id, *_role_scalar_columns()
                )
            )
        return stmt

    async def get(self, public_id: UUID, *, load: LoadSpec | None = None) -> Group:
        spec = load or LoadSpec()
        stmt = self._base_stmt(load).where(GroupModel.public_id == public_id)
        if spec.includes("school"):
            stmt = stmt.options(
                selectinload(GroupModel.school).load_only(
                    SchoolModel.public_id, *_school_scalar_columns()
                )
            )
        result = (await self._session.execute(stmt)).scalar_one_or_none()
        if result is None:
            raise NotFound(object_type="Group", public_id=str(public_id))
        return to_group(result)

    async def search(
        self,
        query: SearchQuery | None = None,
        *,
        sort_by: Sequence[SortSpec] = (),
        limit: int = 50,
        offset: int = 0,
        load: LoadSpec | None = None,
    ) -> Iterable[Group]:
        spec = load or LoadSpec()
        stmt = self._base_stmt(load)
        if spec.includes("school"):
            stmt = stmt.options(
                selectinload(GroupModel.school).load_only(
                    SchoolModel.public_id, *_school_scalar_columns()
                )
            )
        stmt = apply_search_query(stmt, query, self._FIELD_MAP, self._NESTED_FIELD_REGISTRY)
        stmt = apply_sort(
            stmt,
            sort_by,
            self._FIELD_MAP,
            default_field="public_id",
            registry=self._NESTED_FIELD_REGISTRY,
        )
        stmt = stmt.limit(limit).offset(offset)
        return (to_group(model) for model in (await self._session.execute(stmt)).scalars())

    async def create(
        self,
        data: Group,
    ) -> None:
        """
        NOTE Refactor me!!!

        1. Current design fetches nested objects by public_id or name, which requires
           additional queries and may not be ideal for performance.

           SqlAlchemy offers::

                role_public_id = "a497387d-e432-4120-b43e-964abb23eef1"
                group_name = "Class 10A"

                stmt = insert(Group).from_select(
                    [Group.name, Group.role_id],
                    select(
                        literal(group_name),
                        Role.id,
                    ).where(Role.public_id == role_public_id)
                )

                result = session.execute(stmt)
        """
        group_model = to_group_model(data)
        relations = await resolve_group_create_relations(self._session, data)
        group_model.group_type = relations.group_type
        group_model.school = relations.school
        group_model.member_roles = relations.member_roles
        group_model.members = cast(list[SchoolMembershipModel], getattr(relations, "members"))
        group_model.allowed_email_senders_users = relations.allowed_email_senders_users
        group_model.allowed_email_senders_groups = relations.allowed_email_senders_groups

        self._session.add(group_model)
        await self._session.flush()

    async def modify(
        self,
        public_id: UUID,
        operations: Sequence[JSONPathOperation],
    ) -> None:
        _UNSUPPORTED = {"school", "allowed_email_senders_users", "allowed_email_senders_groups"}
        for op in operations:
            top_level = op["path"].lstrip("/").split("/")[0]
            if top_level in _UNSUPPORTED:
                raise UnsupportedOperation(f"Modifying {top_level!r} via patch is not supported.")

        stmt = (
            select(GroupModel)
            .where(GroupModel.public_id == public_id)
            .options(
                selectinload(GroupModel.group_type),
                selectinload(GroupModel.school),
                selectinload(GroupModel.member_roles),
                selectinload(GroupModel.allowed_email_senders_users),
                selectinload(GroupModel.allowed_email_senders_groups),
            )
        )
        result = (await self._session.execute(stmt)).scalar_one_or_none()
        if result is None:
            raise NotFound(object_type="Group", public_id=str(public_id))

        current = cast(dict[str, object], normalise(asdict(to_group(result))))
        patched = cast(dict[str, object], JsonPatch(list(operations)).apply(current))
        GroupValidator.validate(group_from_patch(patched, result.public_id))
        await _apply_group_patch(result, patched, current, self._session)

    async def delete(self, public_id: UUID) -> None:
        stmt = delete(GroupModel).where(GroupModel.public_id == public_id)
        result = cast(CursorResult[Any], await self._session.execute(stmt))
        if result.rowcount == 0:
            raise NotFound(object_type="Group", public_id=str(public_id))
