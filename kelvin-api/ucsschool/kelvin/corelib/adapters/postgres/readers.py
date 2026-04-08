from __future__ import annotations

from collections.abc import Iterable, Sequence
from typing import Any
from uuid import UUID

from sqlalchemy import Select, select
from sqlalchemy.orm import Session, selectinload
from ucsschool_objects.database_models import (
    Group as GroupModel,
    School as SchoolModel,
    SchoolMembership,
    User as UserModel,
)

from ucsschool.kelvin.corelib.adapters.postgres.mapping import to_group, to_school, to_user
from ucsschool.kelvin.corelib.domain import (
    Filter,
    Group,
    InvalidFilter,
    LoadSpec,
    School,
    SearchQuery,
    SortSpec,
    User,
)
from ucsschool.kelvin.corelib.translation.query_to_backend import apply_search_query, apply_sort


def _iter_filters(expr: Any) -> Iterable[Filter]:
    if isinstance(expr, Filter):
        yield expr
        return
    if hasattr(expr, "clauses"):
        for clause in expr.clauses:
            yield from _iter_filters(clause)
        return
    if hasattr(expr, "clause"):
        yield from _iter_filters(expr.clause)


def _with_user_load_options(stmt: Select[tuple[UserModel]], load: LoadSpec) -> Select[tuple[UserModel]]:
    needs_memberships = load.includes("school") or load.includes("groups")
    if not needs_memberships:
        return stmt

    options = [selectinload(UserModel.school_memberships)]
    if load.includes("school"):
        options.append(selectinload(UserModel.school_memberships).selectinload(SchoolMembership.school))
    if load.includes("groups"):
        options.append(selectinload(UserModel.school_memberships).selectinload(SchoolMembership.groups))
    return stmt.options(*options)


class PostgresSchoolReader:
    def __init__(self, session: Session):
        self._session = session

    async def get(self, public_id: UUID, *, load: LoadSpec | None = None) -> School | None:
        del load
        stmt = select(SchoolModel).where(SchoolModel.public_id == public_id)
        result = self._session.execute(stmt).scalar_one_or_none()
        return to_school(result) if result is not None else None

    async def search(
        self,
        query: SearchQuery | None = None,
        *,
        sort_by: Sequence[SortSpec] = (),
        limit: int = 50,
        offset: int = 0,
        load: LoadSpec | None = None,
    ) -> Sequence[School]:
        del load
        field_map = {
            "public_id": SchoolModel.public_id,
            "record_uid": SchoolModel.record_uid,
            "source_uid": SchoolModel.source_uid,
            "name": SchoolModel.name,
            "class_share_file_server": SchoolModel.class_share_file_server,
            "home_share_file_server": SchoolModel.home_share_file_server,
        }
        stmt = select(SchoolModel)
        stmt = apply_search_query(stmt, query, field_map)
        stmt = apply_sort(stmt, sort_by, field_map, default_field="public_id")
        stmt = stmt.limit(limit).offset(offset)
        return tuple(to_school(model) for model in self._session.execute(stmt).scalars().all())


class PostgresGroupReader:
    def __init__(self, session: Session):
        self._session = session

    async def get(self, public_id: UUID, *, load: LoadSpec | None = None) -> Group | None:
        load = load or LoadSpec()
        stmt = select(GroupModel).where(GroupModel.public_id == public_id)
        if load.includes("school"):
            stmt = stmt.options(selectinload(GroupModel.school))
        result = self._session.execute(stmt).scalar_one_or_none()
        if result is None:
            return None
        return to_group(result, include_school=load.includes("school"))

    async def search(
        self,
        query: SearchQuery | None = None,
        *,
        sort_by: Sequence[SortSpec] = (),
        limit: int = 50,
        offset: int = 0,
        load: LoadSpec | None = None,
    ) -> Sequence[Group]:
        load = load or LoadSpec()
        field_map = {
            "public_id": GroupModel.public_id,
            "record_uid": GroupModel.record_uid,
            "source_uid": GroupModel.source_uid,
            "name": GroupModel.name,
            "email": GroupModel.email,
            "school_public_id": SchoolModel.public_id,
            "school_name": SchoolModel.name,
        }

        stmt = select(GroupModel)
        sort_fields = {spec.field for spec in sort_by}
        needs_school_join = any(field.startswith("school_") for field in sort_fields)
        if query is not None and query.where is not None:
            query_fields = {term.field for term in _iter_filters(query.where)}
            if any(field.startswith("school_") for field in query_fields):
                needs_school_join = True

        if needs_school_join:
            stmt = stmt.join(GroupModel.school)

        if load.includes("school"):
            stmt = stmt.options(selectinload(GroupModel.school))
        stmt = apply_search_query(stmt, query, field_map)
        stmt = apply_sort(stmt, sort_by, field_map, default_field="public_id")
        stmt = stmt.limit(limit).offset(offset)
        return tuple(
            to_group(model, include_school=load.includes("school"))
            for model in self._session.execute(stmt).scalars().all()
        )


class PostgresUserReader:
    def __init__(self, session: Session):
        self._session = session

    async def get(self, public_id: UUID, *, load: LoadSpec | None = None) -> User | None:
        load = load or LoadSpec()
        stmt = select(UserModel).where(UserModel.public_id == public_id)
        stmt = _with_user_load_options(stmt, load)
        result = self._session.execute(stmt).scalar_one_or_none()
        if result is None:
            return None
        return to_user(
            result, include_school=load.includes("school"), include_groups=load.includes("groups")
        )

    async def search(
        self,
        query: SearchQuery | None = None,
        *,
        sort_by: Sequence[SortSpec] = (),
        limit: int = 50,
        offset: int = 0,
        load: LoadSpec | None = None,
    ) -> Sequence[User]:
        load = load or LoadSpec()
        field_map = {
            "public_id": UserModel.public_id,
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

        stmt = select(UserModel)
        stmt = _with_user_load_options(stmt, load)
        try:
            stmt = apply_search_query(stmt, query, field_map)
            stmt = apply_sort(stmt, sort_by, field_map, default_field="public_id")
        except InvalidFilter:
            raise
        stmt = stmt.limit(limit).offset(offset)

        return tuple(
            to_user(
                model, include_school=load.includes("school"), include_groups=load.includes("groups")
            )
            for model in self._session.execute(stmt).scalars().all()
        )
