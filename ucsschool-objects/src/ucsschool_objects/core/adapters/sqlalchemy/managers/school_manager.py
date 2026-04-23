from __future__ import annotations

from collections.abc import Iterable, Sequence
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from ucsschool_objects.core.adapters.sqlalchemy.managers._shared import (
    FieldColumn,
    JoinSpec,
    _compose_field_map,
    _load_requested_scalar_attributes,
)
from ucsschool_objects.core.adapters.sqlalchemy.mappers.to_orm import to_school_model
from ucsschool_objects.core.adapters.sqlalchemy.mapping import to_school
from ucsschool_objects.core.adapters.sqlalchemy.query_filter import apply_search_query, apply_sort
from ucsschool_objects.core.domain import (
    LoadSpec,
    NotFound,
    School,
    SearchQuery,
    SortSpec,
)
from ucsschool_objects.core.domain.ports.manager import JSONPathOperation, Manager
from ucsschool_objects.database_models import School as SchoolModel

__all__ = ["SQLAlchemySchoolManager"]


class SQLAlchemySchoolManager(Manager[School]):
    _SCALAR_FIELD_MAP: dict[str, FieldColumn] = {
        "record_uid": SchoolModel.record_uid,
        "source_uid": SchoolModel.source_uid,
        "name": SchoolModel.name,
        "class_share_file_server": SchoolModel.class_share_file_server,
        "home_share_file_server": SchoolModel.home_share_file_server,
    }
    _NESTED_FIELD_REGISTRY: dict[str, JoinSpec] = {}
    _BASE_FIELD_MAP: dict[str, FieldColumn] = {
        "public_id": SchoolModel.public_id,
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

    async def get(self, public_id: UUID, *, load: LoadSpec | None = None) -> School:
        stmt = select(SchoolModel).where(SchoolModel.public_id == public_id)
        stmt = _load_requested_scalar_attributes(
            stmt,
            SchoolModel.public_id,
            load,
            self._LOAD_ATTRIBUTE_MAP,
        )
        result = (await self._session.execute(stmt)).scalar_one_or_none()
        if result is None:
            raise NotFound(object_type="School", public_id=str(public_id))
        return to_school(result)

    async def search(
        self,
        query: SearchQuery | None = None,
        *,
        sort_by: Sequence[SortSpec] = (),
        limit: int = 50,
        offset: int = 0,
        load: LoadSpec | None = None,
    ) -> Iterable[School]:
        stmt = select(SchoolModel)
        stmt = _load_requested_scalar_attributes(
            stmt,
            SchoolModel.public_id,
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
        return (to_school(model) for model in (await self._session.execute(stmt)).scalars())

    async def create(
        self,
        data: School,
    ) -> None:
        school_model = to_school_model(data)
        self._session.add(school_model)
        await self._session.flush()

    async def modify(
        self,
        public_id: UUID,
        operations: Sequence[JSONPathOperation],
    ) -> None:
        raise NotImplementedError("School modify is not implemented yet.")  # pragma: no cover

    async def delete(self, public_id: UUID) -> None:
        raise NotImplementedError("School delete is not implemented yet.")  # pragma: no cover
