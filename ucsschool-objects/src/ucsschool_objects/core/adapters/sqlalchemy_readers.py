from __future__ import annotations

from collections.abc import Iterable, Sequence
from datetime import date
from typing import Any
from uuid import UUID

from sqlalchemy import Select, and_, asc, desc, or_, select
from sqlalchemy.orm import Session, selectinload
from ucsschool_objects.core.domain import UNLOADED, Group, LoadSpec, School, UnloadedType, User
from ucsschool_objects.core.ports import GroupReader, SchoolReader, UserReader
from ucsschool_objects.core.query import And, Filter, Operator, QueryExpr, SearchQuery, SortSpec
from ucsschool_objects.database_models import (
    Group as GroupModel,
    School as SchoolModel,
    SchoolMembership,
    User as UserModel,
)


def _coerce_date(value: object) -> date | None:
    if value is None:
        return None
    return value if isinstance(value, date) else None


def _to_school(model: SchoolModel) -> School:
    return School(
        public_id=model.public_id,
        record_uid=model.record_uid,
        source_uid=model.source_uid,
        name=model.name,
        display_name=dict(model.display_name),
        educational_servers=tuple(model.educational_servers),
        administrative_servers=tuple(model.administrative_servers),
        class_share_file_server=model.class_share_file_server,
        home_share_file_server=model.home_share_file_server,
    )


def _to_group(model: GroupModel, *, include_school: bool) -> Group:
    school: School | None | UnloadedType
    if include_school:
        school = _to_school(model.school)
    else:
        school = UNLOADED

    return Group(
        public_id=model.public_id,
        record_uid=model.record_uid,
        source_uid=model.source_uid,
        name=model.name,
        display_name=dict(model.display_name),
        has_share=model.has_share,
        email=model.email,
        school=school,
    )


def _to_user(model: UserModel, *, include_school: bool, include_groups: bool) -> User:
    school: School | None | UnloadedType = UNLOADED
    groups: tuple[Group, ...] | UnloadedType = UNLOADED

    if include_school:
        primary = next(
            (membership for membership in model.school_memberships if membership.is_primary), None
        )
        if primary is not None:
            school = _to_school(primary.school)
        else:
            school = None

    if include_groups:
        by_public_id: dict[UUID, Group] = {}
        for membership in model.school_memberships:
            for group in membership.groups:
                by_public_id[group.public_id] = _to_group(group, include_school=False)
        groups = tuple(by_public_id.values())

    return User(
        public_id=model.public_id,
        record_uid=model.record_uid,
        source_uid=model.source_uid,
        name=model.name,
        firstname=model.firstname,
        lastname=model.lastname,
        email=model.email,
        birthday=_coerce_date(model.birthday),
        expiration_date=_coerce_date(model.expiration_date),
        active=model.active,
        school=school,
        groups=groups,
    )


def _build_expression(query_expr: QueryExpr, field_map: dict[str, Any]) -> Any:
    if isinstance(query_expr, Filter):
        column = field_map[query_expr.field]
        if query_expr.op is Operator.EQ:
            return column == query_expr.value
        if query_expr.op is Operator.IN:
            values = query_expr.value
            if not isinstance(values, Iterable) or isinstance(values, str):
                raise ValueError(
                    f"IN operator requires an iterable value for field '{query_expr.field}'."
                )
            return column.in_(tuple(values))
        if query_expr.op is Operator.LIKE:
            if not isinstance(query_expr.value, str):
                raise ValueError(
                    f"LIKE operator requires a string value for field '{query_expr.field}'."
                )
            return column.ilike(query_expr.value)
        raise ValueError(f"Unsupported operator: {query_expr.op}")

    if isinstance(query_expr, And):
        if not query_expr.clauses:
            raise ValueError("AND query requires at least one clause.")
        return and_(*(_build_expression(clause, field_map) for clause in query_expr.clauses))

    if not query_expr.clauses:
        raise ValueError("OR query requires at least one clause.")
    return or_(*(_build_expression(clause, field_map) for clause in query_expr.clauses))


def _apply_search_query(
    stmt: Select[Any],
    query: SearchQuery | None,
    field_map: dict[str, Any],
) -> Select[Any]:
    if query is None or query.where is None:
        return stmt
    return stmt.where(_build_expression(query.where, field_map))


def _apply_sort(
    stmt: Select[Any], sort_by: Sequence[SortSpec], field_map: dict[str, Any]
) -> Select[Any]:
    for spec in sort_by:
        column = field_map[spec.field]
        stmt = stmt.order_by(asc(column) if spec.ascending else desc(column))
    return stmt


class SqlAlchemySchoolReader(SchoolReader):
    def __init__(self, session: Session):
        self._session = session

    async def get(self, public_id: UUID, *, load: LoadSpec | None = None) -> School | None:
        del load  # no relationship loading for school in v1
        stmt = select(SchoolModel).where(SchoolModel.public_id == public_id)
        result = self._session.execute(stmt).scalar_one_or_none()
        return _to_school(result) if result is not None else None

    async def search(
        self,
        query: SearchQuery | None = None,
        *,
        sort_by: Sequence[SortSpec] = (),
        limit: int = 50,
        offset: int = 0,
        load: LoadSpec | None = None,
    ) -> Sequence[School]:
        del load  # no relationship loading for school in v1
        field_map = {
            "public_id": SchoolModel.public_id,
            "record_uid": SchoolModel.record_uid,
            "source_uid": SchoolModel.source_uid,
            "name": SchoolModel.name,
            "class_share_file_server": SchoolModel.class_share_file_server,
            "home_share_file_server": SchoolModel.home_share_file_server,
        }

        stmt = select(SchoolModel)
        stmt = _apply_search_query(stmt, query, field_map)
        stmt = _apply_sort(stmt, sort_by or (SortSpec("public_id"),), field_map)
        stmt = stmt.limit(limit).offset(offset)
        return tuple(_to_school(model) for model in self._session.execute(stmt).scalars().all())


class SqlAlchemyGroupReader(GroupReader):
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
        return _to_group(result, include_school=load.includes("school"))

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
        if query is not None and query.where is not None:
            query_fields = {term.field for term in _iter_filters(query.where)}
            if any(field.startswith("school_") for field in query_fields):
                stmt = stmt.join(GroupModel.school)
        if load.includes("school"):
            stmt = stmt.options(selectinload(GroupModel.school))
        stmt = _apply_search_query(stmt, query, field_map)
        stmt = _apply_sort(stmt, sort_by or (SortSpec("public_id"),), field_map)
        stmt = stmt.limit(limit).offset(offset)
        return tuple(
            _to_group(model, include_school=load.includes("school"))
            for model in self._session.execute(stmt).scalars().all()
        )


class SqlAlchemyUserReader(UserReader):
    def __init__(self, session: Session):
        self._session = session

    async def get(self, public_id: UUID, *, load: LoadSpec | None = None) -> User | None:
        load = load or LoadSpec()
        stmt = select(UserModel).where(UserModel.public_id == public_id)
        stmt = _with_user_load_options(stmt, load)
        result = self._session.execute(stmt).scalar_one_or_none()
        if result is None:
            return None
        return _to_user(
            result,
            include_school=load.includes("school"),
            include_groups=load.includes("groups"),
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
        }

        stmt = select(UserModel)
        stmt = _with_user_load_options(stmt, load)
        stmt = _apply_search_query(stmt, query, field_map)
        stmt = _apply_sort(stmt, sort_by or (SortSpec("public_id"),), field_map)
        stmt = stmt.limit(limit).offset(offset)

        return tuple(
            _to_user(
                model,
                include_school=load.includes("school"),
                include_groups=load.includes("groups"),
            )
            for model in self._session.execute(stmt).scalars().all()
        )


def _iter_filters(expr: QueryExpr) -> Iterable[Filter]:
    if isinstance(expr, Filter):
        yield expr
        return
    for clause in expr.clauses:
        yield from _iter_filters(clause)


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
