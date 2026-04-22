from __future__ import annotations

from collections.abc import Iterable, Sequence
from uuid import UUID

from sqlalchemy import Select, select
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
from ucsschool_objects.core.adapters.sqlalchemy.mapping import to_group
from ucsschool_objects.core.adapters.sqlalchemy.query_filter import apply_search_query, apply_sort
from ucsschool_objects.core.domain import (
    Group,
    LoadSpec,
    NotFound,
    SearchQuery,
    SortSpec,
)
from ucsschool_objects.core.domain.ports.manager import JSONPathOperation, Manager
from ucsschool_objects.database_models import (
    Group as GroupModel,
    GroupType as GroupTypeModel,
    Role as RoleModel,
    School as SchoolModel,
    User as UserModel,
)

__all__ = ["SQLAlchemyGroupManager"]


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
        raise NotImplementedError("Group create is not implemented yet.")  # pragma: no cover

    async def modify(
        self,
        public_id: UUID,
        operations: Sequence[JSONPathOperation],
    ) -> None:
        raise NotImplementedError("Group modify is not implemented yet.")  # pragma: no cover

    async def delete(self, public_id: UUID) -> None:
        raise NotImplementedError("Group delete is not implemented yet.")  # pragma: no cover
