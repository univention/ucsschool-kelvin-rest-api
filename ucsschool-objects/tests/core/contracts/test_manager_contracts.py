from __future__ import annotations

from typing import TYPE_CHECKING, cast

import pytest
from tests.core.contracts.contract_test_support import (
    ManagerContractFactories,
    ManagerSearchExpectation,
    ManagerSetup,
    NamedRecord,
)
from ucsschool_objects.core.adapters.sqlalchemy import (
    SQLAlchemyGroupManager,
    SQLAlchemyRoleManager,
    SQLAlchemySchoolManager,
    SQLAlchemyUserManager,
)
from ucsschool_objects.core.domain import (
    Filter,
    Operator,
    SearchQuery,
    SortSpec,
)

if TYPE_CHECKING:
    from collections.abc import Callable

    from sqlalchemy.ext.asyncio import AsyncSession
    from tests.test_types import (
        AsyncGroupFactory as GroupFactory,
        AsyncGroupTypeFactory as GroupTypeFactory,
        AsyncRoleFactory as RoleFactory,
        AsyncSchoolFactory as SchoolFactory,
        AsyncUserFactory as UserFactory,
    )
    from ucsschool_objects.core.domain.ports.manager import Manager


async def _setup_school_manager_case(factories: ManagerContractFactories) -> ManagerSearchExpectation:
    school = await factories.school_factory(name="school-1")
    return ManagerSearchExpectation(
        public_id=school.public_id,
        expected_name="school-1",
        query=SearchQuery(where=Filter(field="name", op=Operator.EQ, value="school-1")),
    )


def _build_group_manager_case(role_name: str, group_name: str) -> ManagerSetup:
    async def _setup_group_manager_case(factories: ManagerContractFactories) -> ManagerSearchExpectation:
        role = await factories.roles_factory(name=role_name)
        school = await factories.school_factory(name=f"{group_name}-school")
        sender_user = await factories.user_factory(name=f"{group_name}-sender-user")
        sender_group = await factories.group_factory(
            name=f"{group_name}-sender-group",
            roles=role,
            school=school,
        )
        group = await factories.group_factory(
            name=group_name,
            roles=role,
            school=school,
            allowed_email_senders_users=[sender_user],
            allowed_email_senders_groups=[sender_group],
        )
        return ManagerSearchExpectation(
            public_id=group.public_id,
            expected_name=group_name,
            query=SearchQuery(where=Filter(field="name", op=Operator.EQ, value=group_name)),
        )

    return _setup_group_manager_case


async def _setup_role_manager_case(factories: ManagerContractFactories) -> ManagerSearchExpectation:
    role = await factories.role_factory(name="school:admin")
    return ManagerSearchExpectation(
        public_id=role.public_id,
        expected_name="school:admin",
        query=SearchQuery(where=Filter(field="name", op=Operator.EQ, value="school:admin")),
    )


async def _setup_user_manager_case(factories: ManagerContractFactories) -> ManagerSearchExpectation:
    user = await factories.user_factory(name="anna")
    return ManagerSearchExpectation(
        public_id=user.public_id,
        expected_name="anna",
        query=SearchQuery(where=Filter(field="name", op=Operator.EQ, value="anna")),
    )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "manager_cls, setup_case",
    [
        pytest.param(SQLAlchemySchoolManager, _setup_school_manager_case, id="school"),
        pytest.param(
            SQLAlchemyGroupManager,
            _build_group_manager_case("school_class", "class-a"),
            id="group-school-class",
        ),
        pytest.param(
            SQLAlchemyGroupManager,
            _build_group_manager_case("workgroup", "admins"),
            id="group-workgroup",
        ),
        pytest.param(SQLAlchemyRoleManager, _setup_role_manager_case, id="role"),
        pytest.param(SQLAlchemyUserManager, _setup_user_manager_case, id="user"),
    ],
)
async def test_manager_get_and_search_contract(
    db_session: AsyncSession,
    school_factory: SchoolFactory,
    group_factory: GroupFactory,
    roles_factory: GroupTypeFactory,
    role_factory: RoleFactory,
    user_factory: UserFactory,
    manager_cls: Callable[[AsyncSession], object],
    setup_case: ManagerSetup,
) -> None:
    factories = ManagerContractFactories(
        school_factory=school_factory,
        group_factory=group_factory,
        roles_factory=roles_factory,
        role_factory=role_factory,
        user_factory=user_factory,
    )
    expectation = await setup_case(factories)
    manager = cast("Manager[NamedRecord]", manager_cls(db_session))

    fetched = await manager.get(expectation.public_id)
    assert fetched.name == expectation.expected_name

    results = list(await manager.search(expectation.query))
    assert len(results) == 1
    assert results[0].public_id == expectation.public_id


@pytest.mark.asyncio
async def test_group_manager_supports_sorting_by_school_fields(
    db_session: AsyncSession,
    school_factory: SchoolFactory,
    group_factory: GroupFactory,
    roles_factory: GroupTypeFactory,
) -> None:
    role = await roles_factory(name="workgroup")
    school_a = await school_factory(name="alpha")
    school_b = await school_factory(name="beta")
    await group_factory(name="group-b", school=school_b, roles=role)
    await group_factory(name="group-a", school=school_a, roles=role)
    manager = SQLAlchemyGroupManager(db_session)

    results = list(await manager.search(sort_by=(SortSpec(field="school.name", ascending=True),)))
    assert [item.name for item in results] == ["group-a", "group-b"]
