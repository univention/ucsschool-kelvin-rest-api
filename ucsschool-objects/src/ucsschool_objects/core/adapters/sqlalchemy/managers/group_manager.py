from __future__ import annotations

from typing import TYPE_CHECKING, cast

from sqlalchemy import Select, delete, select
from sqlalchemy.engine import CursorResult
from sqlalchemy.orm import selectinload
from ucsschool_objects.core.adapters.sqlalchemy.managers._shared import (
    FieldColumn,
    JoinSpec,
    JoinType,
    PublicIdInput,
    apply_patch,
    compose_field_map,
    extract_public_ids,
    get_exposed_fields,
    load_requested_scalar_attributes,
    role_scalar_columns,
    school_scalar_columns,
    sync_collection,
    sync_scalar_relation,
)
from ucsschool_objects.core.adapters.sqlalchemy.mappers.to_domain import group_from_patch, to_group
from ucsschool_objects.core.adapters.sqlalchemy.mappers.to_orm import (
    resolve_group_create_relations,
    to_group_model,
)
from ucsschool_objects.core.adapters.sqlalchemy.query_filter import apply_search_query, apply_sort
from ucsschool_objects.core.domain.errors import NotFound, UnsupportedOperation
from ucsschool_objects.core.domain.json import PatchDict, to_json
from ucsschool_objects.core.domain.load_spec import LoadSpec
from ucsschool_objects.core.domain.models import Group
from ucsschool_objects.core.domain.ports.manager import JSONPathOperation, Manager
from ucsschool_objects.core.domain.query import SearchQuery, SortSpec
from ucsschool_objects.core.domain.validators import GroupValidator
from ucsschool_objects.database_models import (
    Group as GroupModel,
    Role as RoleModel,
    School as SchoolModel,
    SchoolMembership as SchoolMembershipModel,
    User as UserModel,
)

if TYPE_CHECKING:
    from collections.abc import Iterable, Sequence
    from uuid import UUID

    from sqlalchemy.ext.asyncio import AsyncSession


async def _sync_group_members(
    session: AsyncSession,
    model: GroupModel,
    patched_members: list[PublicIdInput],
    current_members: list[PublicIdInput],
) -> None:
    current_ids = extract_public_ids(current_members)
    patched_ids = extract_public_ids(patched_members)
    if current_ids == patched_ids:
        return

    if patched_ids:
        stmt = (
            select(SchoolMembershipModel)
            .join(UserModel)
            .where(
                UserModel.public_id.in_(patched_ids),
                SchoolMembershipModel.school_id == model.school_id,
            )
        )
        members_result = await session.execute(stmt)
        model.members = list(members_result.scalars())
    else:
        model.members = []


async def _apply_group_patch(
    model: GroupModel,
    patched: PatchDict,
    current: PatchDict,
    session: AsyncSession,
) -> None:
    model.record_uid = cast(str, patched["record_uid"])
    model.source_uid = cast(str, patched["source_uid"])
    model.name = cast(str, patched["name"])
    model.display_name = cast(str, patched["display_name"])
    model.email = cast(str | None, patched["email"])
    model.has_share = cast(bool, patched["create_share"])
    model.description = cast(str | None, patched["description"])
    model.udm_properties = cast("dict[str, object]", patched["udm_properties"])

    await sync_collection(
        session,
        cast(list[PublicIdInput], patched["member_roles"]),
        cast(list[PublicIdInput], current["member_roles"]),
        RoleModel,
        lambda values: setattr(model, "member_roles", values),
    )
    await _sync_group_members(
        session,
        model,
        cast(list[PublicIdInput], patched["members"]),
        cast(list[PublicIdInput], current["members"]),
    )
    await sync_collection(
        session,
        cast(list[PublicIdInput], patched["allowed_email_senders_users"]),
        cast(list[PublicIdInput], current["allowed_email_senders_users"]),
        UserModel,
        lambda values: setattr(model, "allowed_email_senders_users", values),
    )
    await sync_collection(
        session,
        cast(list[PublicIdInput], patched["allowed_email_senders_groups"]),
        cast(list[PublicIdInput], current["allowed_email_senders_groups"]),
        GroupModel,
        lambda values: setattr(model, "allowed_email_senders_groups", values),
    )
    await sync_collection(
        session,
        cast(list[PublicIdInput], patched["roles"]),
        cast(list[PublicIdInput], current["roles"]),
        RoleModel,
        lambda values: setattr(model, "roles", values),
    )
    await sync_scalar_relation(
        session,
        "Group",
        "school",
        cast(PublicIdInput | None, patched["school"]),
        cast(PublicIdInput | None, current["school"]),
        SchoolModel,
        lambda value: setattr(model, "school", cast(SchoolModel, value)),
    )


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
            exposed_fields=get_exposed_fields(SchoolModel),
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
        "description": GroupModel.description,
        "udm_properties": GroupModel.udm_properties,
    }
    _JSON_FIELD_MAP: dict[str, FieldColumn] = {
        "udm_properties": GroupModel.udm_properties,
    }
    _FIELD_MAP: dict[str, FieldColumn] = compose_field_map(
        _BASE_FIELD_MAP,
        _NESTED_FIELD_REGISTRY,
    )

    def __init__(self, session: AsyncSession):
        self._session = session

    _MAX_PATCH_DEPTH: dict[str, int] = {
        "school": 1,
        "allowed_email_senders_users": 2,
        "allowed_email_senders_groups": 2,
        "members": 2,
        "member_roles": 2,
    }

    def _check_modify_operations(self, operations: Sequence[JSONPathOperation]) -> None:
        for op in operations:
            parts = op["path"].lstrip("/").split("/")
            top = parts[0]
            max_depth = self._MAX_PATCH_DEPTH.get(top)
            if max_depth is not None and len(parts) > max_depth:
                raise UnsupportedOperation(f"Modifying {top!r} via deep patch is not supported.")

    def _modify_query(self, public_id: UUID) -> Select[tuple[GroupModel]]:
        return (
            select(GroupModel)
            .where(GroupModel.public_id == public_id)
            .options(
                selectinload(GroupModel.roles).load_only(RoleModel.public_id, *role_scalar_columns()),
                selectinload(GroupModel.school),
                selectinload(GroupModel.member_roles),
                selectinload(GroupModel.members).selectinload(SchoolMembershipModel.user),
                selectinload(GroupModel.allowed_email_senders_users),
                selectinload(GroupModel.allowed_email_senders_groups),
            )
        )

    def _base_stmt(self, load: LoadSpec | None) -> Select[tuple[GroupModel]]:
        stmt = select(GroupModel)
        stmt = load_requested_scalar_attributes(
            stmt,
            GroupModel.public_id,
            load,
            self._LOAD_ATTRIBUTE_MAP,
        )
        if load is not None and load.includes("roles"):
            stmt = stmt.options(
                selectinload(GroupModel.roles).load_only(RoleModel.public_id, *role_scalar_columns())
            )
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
                    RoleModel.public_id, *role_scalar_columns()
                )
            )
        return stmt

    async def get(self, public_id: UUID, *, load: LoadSpec | None = None) -> Group:
        spec = load or LoadSpec()
        stmt = self._base_stmt(load).where(GroupModel.public_id == public_id)
        if spec.includes("school"):
            stmt = stmt.options(
                selectinload(GroupModel.school).load_only(
                    SchoolModel.public_id, *school_scalar_columns()
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
        limit: int | None = None,
        offset: int = 0,
        load: LoadSpec | None = None,
    ) -> Iterable[Group]:
        spec = load or LoadSpec()
        stmt = self._base_stmt(load)
        if spec.includes("school"):
            stmt = stmt.options(
                selectinload(GroupModel.school).load_only(
                    SchoolModel.public_id, *school_scalar_columns()
                )
            )
        stmt = apply_search_query(
            stmt,
            query,
            self._FIELD_MAP,
            self._NESTED_FIELD_REGISTRY,
            json_field_map=self._JSON_FIELD_MAP,
        )
        stmt = apply_sort(
            stmt,
            sort_by,
            self._FIELD_MAP,
            default_field="public_id",
            registry=self._NESTED_FIELD_REGISTRY,
        )
        if limit is not None:
            stmt = stmt.limit(limit)
        if offset:
            stmt = stmt.offset(offset)
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
        group_model.roles = relations.roles
        group_model.school = relations.school
        group_model.member_roles = relations.member_roles
        group_model.members = relations.members
        group_model.allowed_email_senders_users = relations.allowed_email_senders_users
        group_model.allowed_email_senders_groups = relations.allowed_email_senders_groups

        self._session.add(group_model)
        await self._session.flush()

    async def modify(
        self,
        public_id: UUID,
        operations: Sequence[JSONPathOperation],
    ) -> None:
        self._check_modify_operations(operations)

        stmt = self._modify_query(public_id)
        result = (await self._session.execute(stmt)).scalar_one_or_none()
        if result is None:
            raise NotFound(object_type="Group", public_id=str(public_id))

        current_domain = to_group(result)
        patched = apply_patch(operations=operations, current_domain_obj=current_domain)
        GroupValidator.validate(group_from_patch(patched, result.public_id))

        current_dict = to_json(current_domain)
        await _apply_group_patch(result, patched, current_dict, self._session)

    async def delete(self, public_id: UUID) -> None:
        stmt = delete(GroupModel).where(GroupModel.public_id == public_id)
        result = cast(CursorResult[None], await self._session.execute(stmt))
        if result.rowcount == 0:
            raise NotFound(object_type="Group", public_id=str(public_id))
