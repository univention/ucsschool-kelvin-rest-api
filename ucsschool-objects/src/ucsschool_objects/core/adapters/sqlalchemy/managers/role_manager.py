from __future__ import annotations

from collections.abc import Iterable, Sequence
from typing import cast
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from ucsschool_objects.core.adapters.sqlalchemy.managers._shared import (
    FieldColumn,
    JoinSpec,
    _check_value_presence,
    _compose_field_map,
    _load_requested_scalar_attributes,
    generate_public_id,
)
from ucsschool_objects.core.adapters.sqlalchemy.mapping import to_role
from ucsschool_objects.core.adapters.sqlalchemy.query_filter import apply_search_query, apply_sort
from ucsschool_objects.core.domain import (
    UNSET,
    LoadSpec,
    NotFound,
    Role,
    SearchQuery,
    SortSpec,
)
from ucsschool_objects.core.domain.ports.manager import JSONPathOperation, Manager
from ucsschool_objects.database_models import Role as RoleModel

__all__ = ["SQLAlchemyRoleManager"]


class SQLAlchemyRoleManager(Manager[Role]):
    _SCALAR_FIELD_MAP: dict[str, FieldColumn] = {
        "name": RoleModel.name,
    }
    _NESTED_FIELD_REGISTRY: dict[str, JoinSpec] = {}
    _BASE_FIELD_MAP: dict[str, FieldColumn] = {
        "public_id": RoleModel.public_id,
        **_SCALAR_FIELD_MAP,
    }
    _LOAD_ATTRIBUTE_MAP: dict[str, FieldColumn] = {
        **_SCALAR_FIELD_MAP,
        "display_name": RoleModel.display_name,
    }
    _FIELD_MAP: dict[str, FieldColumn] = _compose_field_map(
        _BASE_FIELD_MAP,
        _NESTED_FIELD_REGISTRY,
    )

    def __init__(self, session: AsyncSession):
        self._session = session

    async def get(self, public_id: UUID, *, load: LoadSpec | None = None) -> Role:
        stmt = select(RoleModel).where(RoleModel.public_id == public_id)
        stmt = _load_requested_scalar_attributes(
            stmt,
            RoleModel.public_id,
            load,
            self._LOAD_ATTRIBUTE_MAP,
        )
        result = (await self._session.execute(stmt)).scalar_one_or_none()
        if result is None:
            raise NotFound(object_type="Role", public_id=str(public_id))
        return to_role(result)

    async def search(
        self,
        query: SearchQuery | None = None,
        *,
        sort_by: Sequence[SortSpec] = (),
        limit: int = 50,
        offset: int = 0,
        load: LoadSpec | None = None,
    ) -> Iterable[Role]:
        stmt = select(RoleModel)
        stmt = _load_requested_scalar_attributes(
            stmt,
            RoleModel.public_id,
            load,
            self._LOAD_ATTRIBUTE_MAP,
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
        return (to_role(model) for model in (await self._session.execute(stmt)).scalars())

    async def create(
        self,
        data: Role,
    ) -> None:
        role_model = RoleModel(
            name=_check_value_presence(data.name, object_type="Role", field_name="name"),
            display_name=_check_value_presence(
                data.display_name, object_type="Role", field_name="display_name"
            ),
        )
        if data.public_id == UNSET:
            role_model.public_id = generate_public_id()
        else:
            role_model.public_id = cast(UUID, data.public_id)

        self._session.add(role_model)
        await self._session.flush()

    async def modify(
        self,
        public_id: UUID,
        operations: Sequence[JSONPathOperation],
    ) -> None:
        raise NotImplementedError("Role modify is not implemented yet.")  # pragma: no cover

    async def delete(self, public_id: UUID) -> None:
        raise NotImplementedError("Role delete is not implemented yet.")  # pragma: no cover
