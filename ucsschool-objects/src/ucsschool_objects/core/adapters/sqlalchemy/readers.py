from __future__ import annotations

from collections.abc import Iterable, Sequence
from typing import Generic, TypeAlias, TypeVar
from uuid import UUID

from sqlalchemy import Select, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from ucsschool_objects.core.adapters.sqlalchemy.mapping import (
    projection_group_type_name,
    to_group,
    to_role,
    to_school,
    to_user,
)
from ucsschool_objects.core.adapters.sqlalchemy.query_filter import (
    FieldColumn,
    apply_search_query,
    apply_sort,
)
from ucsschool_objects.core.domain import (
    And,
    Filter,
    Group,
    LoadSpec,
    Not,
    NotFound,
    Or,
    Role,
    School,
    SchoolClass,
    SearchQuery,
    SortSpec,
    User,
    WorkGroup,
)
from ucsschool_objects.core.ports.readers import Reader
from ucsschool_objects.database_models import (
    Group as GroupModel,
    GroupType as GroupTypeModel,
    Role as RoleModel,
    School as SchoolModel,
    SchoolMembership,
    User as UserModel,
)

__all__ = [
    "SQLAlchemyGroupReader",
    "SQLAlchemyRoleReader",
    "SQLAlchemySchoolClassReader",
    "SQLAlchemySchoolReader",
    "SQLAlchemyUserReader",
    "SQLAlchemyWorkGroupReader",
]

GroupProjectionT = TypeVar("GroupProjectionT", bound=Group)
QueryExpr: TypeAlias = Filter | And | Or | Not


def _iter_filters(expr: QueryExpr) -> Iterable[Filter]:
    if isinstance(expr, Filter):
        yield expr
        return
    if isinstance(expr, (And, Or)):
        for clause in expr.clauses:
            yield from _iter_filters(clause)
        return
    yield from _iter_filters(expr.clause)


def _with_user_load_options(stmt: Select[tuple[UserModel]], load: LoadSpec) -> Select[tuple[UserModel]]:
    options = []
    if load.includes("school_memberships") or load.includes("groups") or load.includes("roles"):
        options.extend(
            [
                selectinload(UserModel.school_memberships),
                selectinload(UserModel.school_memberships).selectinload(SchoolMembership.school),
            ]
        )
        if load.includes("groups"):
            options.append(
                selectinload(UserModel.school_memberships).selectinload(SchoolMembership.groups)
            )
            options.append(
                selectinload(UserModel.school_memberships)
                .selectinload(SchoolMembership.groups)
                .selectinload(GroupModel.group_type)
            )
            options.append(
                selectinload(UserModel.school_memberships)
                .selectinload(SchoolMembership.groups)
                .selectinload(GroupModel.allowed_email_senders_users)
            )
            options.append(
                selectinload(UserModel.school_memberships)
                .selectinload(SchoolMembership.groups)
                .selectinload(GroupModel.allowed_email_senders_groups)
            )
        if load.includes("roles"):
            options.append(
                selectinload(UserModel.school_memberships).selectinload(SchoolMembership.roles)
            )
    if load.includes("legal_wards"):
        options.append(selectinload(UserModel.legal_wards))
    if load.includes("legal_guardians"):
        options.append(selectinload(UserModel.legal_guardians))
    if not options:
        return stmt
    return stmt.options(*options)


class SQLAlchemySchoolReader(Reader[School]):
    def __init__(self, session: AsyncSession):
        self._session = session

    async def get(self, public_id: UUID, *, load: LoadSpec | None = None) -> School:
        stmt = select(SchoolModel).where(SchoolModel.public_id == public_id)
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
        return (to_school(model) for model in (await self._session.execute(stmt)).scalars())


class SQLAlchemyGroupReader(Generic[GroupProjectionT]):
    def __init__(
        self,
        session: AsyncSession,
        *,
        group_type_name: str,
        group_model: type[GroupProjectionT],
    ):
        self._session = session
        self._group_type_name = group_type_name.lower()
        self._group_model = group_model

    def _field_map(self) -> dict[str, FieldColumn]:
        field_map: dict[str, FieldColumn] = {
            "public_id": GroupModel.public_id,
            "record_uid": GroupModel.record_uid,
            "source_uid": GroupModel.source_uid,
            "name": GroupModel.name,
            "email": GroupModel.email,
            "school_public_id": SchoolModel.public_id,
            "school_name": SchoolModel.name,
        }
        return field_map

    def _base_stmt(self) -> Select[tuple[GroupModel]]:
        stmt = select(GroupModel).join(GroupModel.group_type)
        stmt = stmt.where(GroupTypeModel.name == self._group_type_name)
        stmt = stmt.options(selectinload(GroupModel.allowed_email_senders_users))
        stmt = stmt.options(selectinload(GroupModel.allowed_email_senders_groups))
        return stmt

    async def get(self, public_id: UUID, *, load: LoadSpec | None = None) -> GroupProjectionT:
        load = load or LoadSpec()
        stmt = self._base_stmt().where(GroupModel.public_id == public_id)
        if load.includes("school"):
            stmt = stmt.options(selectinload(GroupModel.school))
        result = (await self._session.execute(stmt)).scalar_one_or_none()
        if result is None:
            raise NotFound(object_type=self._group_model.__name__, public_id=str(public_id))
        return to_group(result, self._group_model, include_school=load.includes("school"))

    async def search(
        self,
        query: SearchQuery | None = None,
        *,
        sort_by: Sequence[SortSpec] = (),
        limit: int = 50,
        offset: int = 0,
        load: LoadSpec | None = None,
    ) -> Iterable[GroupProjectionT]:
        load = load or LoadSpec()
        field_map = self._field_map()

        stmt = self._base_stmt()
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
        return (
            to_group(model, self._group_model, include_school=load.includes("school"))
            for model in (await self._session.execute(stmt)).scalars()
        )


class SQLAlchemySchoolClassReader(SQLAlchemyGroupReader[SchoolClass]):
    def __init__(self, session: AsyncSession):
        super().__init__(
            session,
            group_type_name=projection_group_type_name(SchoolClass),
            group_model=SchoolClass,
        )


class SQLAlchemyWorkGroupReader(SQLAlchemyGroupReader[WorkGroup]):
    def __init__(self, session: AsyncSession):
        super().__init__(
            session,
            group_type_name=projection_group_type_name(WorkGroup),
            group_model=WorkGroup,
        )


class SQLAlchemyRoleReader(Reader[Role]):
    def __init__(self, session: AsyncSession):
        self._session = session

    async def get(self, public_id: UUID, *, load: LoadSpec | None = None) -> Role:
        stmt = select(RoleModel).where(RoleModel.public_id == public_id)
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
        field_map = {
            "public_id": RoleModel.public_id,
            "name": RoleModel.name,
        }
        stmt = select(RoleModel)
        stmt = apply_search_query(stmt, query, field_map)
        stmt = apply_sort(stmt, sort_by, field_map, default_field="public_id")
        stmt = stmt.limit(limit).offset(offset)
        return (to_role(model) for model in (await self._session.execute(stmt)).scalars())


class SQLAlchemyUserReader(Reader[User]):
    def __init__(self, session: AsyncSession):
        self._session = session

    async def get(self, public_id: UUID, *, load: LoadSpec | None = None) -> User:
        load = load or LoadSpec()
        stmt = select(UserModel).where(UserModel.public_id == public_id)
        stmt = _with_user_load_options(stmt, load)
        result = (await self._session.execute(stmt)).scalar_one_or_none()
        if result is None:
            raise NotFound(object_type="User", public_id=str(public_id))
        return to_user(
            result,
            include_memberships=(
                load.includes("school_memberships") or load.includes("groups") or load.includes("roles")
            ),
            include_groups=load.includes("groups"),
            include_roles=load.includes("roles"),
            include_legal_wards=load.includes("legal_wards"),
            include_legal_guardians=load.includes("legal_guardians"),
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
        stmt = apply_search_query(stmt, query, field_map)
        stmt = apply_sort(stmt, sort_by, field_map, default_field="public_id")
        stmt = stmt.limit(limit).offset(offset)

        return (
            to_user(
                model,
                include_memberships=(
                    load.includes("school_memberships")
                    or load.includes("groups")
                    or load.includes("roles")
                ),
                include_groups=load.includes("groups"),
                include_roles=load.includes("roles"),
                include_legal_wards=load.includes("legal_wards"),
                include_legal_guardians=load.includes("legal_guardians"),
            )
            for model in (await self._session.execute(stmt)).scalars()
        )
