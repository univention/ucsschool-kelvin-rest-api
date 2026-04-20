from __future__ import annotations

from collections.abc import Iterable, Sequence
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from ucsschool_objects.core.adapters.sqlalchemy.mapping import to_role
from ucsschool_objects.core.adapters.sqlalchemy.query_filter import apply_search_query, apply_sort
from ucsschool_objects.core.adapters.sqlalchemy.readers._shared import (
    FieldColumn,
    JoinSpec,
    _compose_field_map,
    _load_requested_scalar_attributes,
)
from ucsschool_objects.core.domain import (
    LoadSpec,
    NotFound,
    Role,
    SearchQuery,
    SortSpec,
)
from ucsschool_objects.core.domain.ports.readers import Reader
from ucsschool_objects.database_models import Role as RoleModel

__all__ = ["SQLAlchemyRoleReader"]


class SQLAlchemyRoleReader(Reader[Role]):
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
