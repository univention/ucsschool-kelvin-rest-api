from __future__ import annotations

from collections.abc import Iterable, Sequence
from typing import cast
from uuid import UUID

from sqlalchemy import Select, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from ucsschool_objects.core.adapters.sqlalchemy.managers._shared import (
    FieldColumn,
    JoinSpec,
    JoinType,
    _bulk_fetch_by_name,
    _bulk_fetch_by_public_id,
    _check_nullable_value_presence,
    _check_value_presence,
    _compose_field_map,
    _fetch_one_by_name,
    _fetch_one_by_public_id,
    _get_exposed_fields,
    _load_requested_scalar_attributes,
    _role_scalar_columns,
    _school_scalar_columns,
    generate_public_id,
)
from ucsschool_objects.core.adapters.sqlalchemy.mapping import to_group
from ucsschool_objects.core.adapters.sqlalchemy.query_filter import apply_search_query, apply_sort
from ucsschool_objects.core.domain import (
    UNSET,
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

        2. Separation on concerns is not great.
           The manager should be responsible for orchestrating the operation,
           but the details of how to fetch related objects and handle the various
           field types could be abstracted away into separate helper functions or
           even a dedicated Mapper module.
        """
        group_model = GroupModel(
            record_uid=_check_value_presence(
                data.record_uid, object_type="Group", field_name="record_uid"
            ),
            source_uid=_check_value_presence(
                data.source_uid, object_type="Group", field_name="source_uid"
            ),
            name=_check_value_presence(data.name, object_type="Group", field_name="name"),
            display_name=dict(
                _check_value_presence(data.display_name, object_type="Group", field_name="display_name"),
            ),
            has_share=_check_value_presence(
                data.create_share, object_type="Group", field_name="create_share"
            ),
            email=_check_nullable_value_presence(data.email, object_type="Group", field_name="email"),
        )
        if data.public_id == UNSET:
            group_model.public_id = generate_public_id()
        else:
            group_model.public_id = cast(UUID, data.public_id)

        group_type_name = _check_value_presence(
            data.group_type, object_type="Group", field_name="group_type"
        )
        group_model.group_type = await _fetch_one_by_name(
            self._session, GroupTypeModel, GroupTypeModel.name, group_type_name, "GroupType"
        )

        school = _check_value_presence(data.school, object_type="Group", field_name="school")
        if not isinstance(school.public_id, UUID):
            raise ValueError("Group.school must have a public_id for create().")
        group_model.school = await _fetch_one_by_public_id(
            self._session, SchoolModel, school.public_id, "School"
        )

        member_roles = _check_value_presence(
            data.member_roles, object_type="Group", field_name="member_roles"
        )
        role_ids = [r.public_id for r in member_roles if isinstance(r.public_id, UUID)]
        roles_by_id = await _bulk_fetch_by_public_id(self._session, RoleModel, role_ids, "Role")
        group_model.member_roles = list(roles_by_id.values())

        allowed_email_senders_users = _check_value_presence(
            data.allowed_email_senders_users,
            object_type="Group",
            field_name="allowed_email_senders_users",
        )
        users_by_name = await _bulk_fetch_by_name(
            self._session,
            UserModel,
            UserModel.name,
            list(allowed_email_senders_users),
            "User",
        )
        group_model.allowed_email_senders_users = list(users_by_name.values())

        allowed_email_senders_groups = _check_value_presence(
            data.allowed_email_senders_groups,
            object_type="Group",
            field_name="allowed_email_senders_groups",
        )
        groups_by_name = await _bulk_fetch_by_name(
            self._session,
            GroupModel,
            GroupModel.name,
            list(allowed_email_senders_groups),
            "Group",
        )
        group_model.allowed_email_senders_groups = list(groups_by_name.values())

        self._session.add(group_model)
        await self._session.flush()

    async def modify(
        self,
        public_id: UUID,
        operations: Sequence[JSONPathOperation],
    ) -> None:
        raise NotImplementedError("Group modify is not implemented yet.")  # pragma: no cover

    async def delete(self, public_id: UUID) -> None:
        raise NotImplementedError("Group delete is not implemented yet.")  # pragma: no cover
