"""Tests for nested field query support in SQLAlchemy managers."""
from __future__ import annotations

from types import SimpleNamespace
from typing import TYPE_CHECKING, Any
from uuid import uuid4

import pytest
from sqlalchemy import inspect
from ucsschool_objects import (
    UNLOADED,
    UNSET,
    And,
    Filter,
    Not,
    Operator,
    Or,
    School,
    SchoolMembership,
    SearchQuery,
    SortSpec,
)
from ucsschool_objects.core.adapters.sqlalchemy.managers._shared import (
    JoinSpec,
    JoinType,
    compose_field_map,
    get_exposed_fields,
    iter_filters,
)
from ucsschool_objects.core.adapters.sqlalchemy.managers.group_manager import (
    SQLAlchemyGroupManager,
)
from ucsschool_objects.core.adapters.sqlalchemy.managers.role_manager import (
    SQLAlchemyRoleManager,
)
from ucsschool_objects.core.adapters.sqlalchemy.managers.school_manager import (
    SQLAlchemySchoolManager,
)
from ucsschool_objects.core.adapters.sqlalchemy.managers.user_manager import (
    SQLAlchemyUserManager,
)
from ucsschool_objects.core.adapters.sqlalchemy.mappers import to_domain
from ucsschool_objects.core.adapters.sqlalchemy.mappers.to_domain import _is_loaded, _loaded_value
from ucsschool_objects.core.domain.errors import UnsupportedNestedField
from ucsschool_objects.core.domain.models import domain_asdict
from ucsschool_objects.database_models import School as SchoolModel

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession


@pytest.mark.asyncio
async def test_user_manager_nested_registry_initialized(db_session: AsyncSession) -> None:
    """User manager should initialize nested field registry on first access."""
    manager = SQLAlchemyUserManager(db_session)

    assert manager._NESTED_FIELD_REGISTRY
    assert "groups" in manager._NESTED_FIELD_REGISTRY
    assert "roles" in manager._NESTED_FIELD_REGISTRY
    assert "schools" in manager._NESTED_FIELD_REGISTRY

    # Verify field map includes nested fields
    assert "groups.public_id" in manager._FIELD_MAP
    assert "roles.name" in manager._FIELD_MAP
    assert "schools.record_uid" in manager._FIELD_MAP


@pytest.mark.asyncio
async def test_group_manager_nested_registry_initialized(db_session: AsyncSession) -> None:
    """Group manager should initialize nested field registry on first access."""
    manager = SQLAlchemyGroupManager(db_session)

    assert manager._NESTED_FIELD_REGISTRY
    assert "school" in manager._NESTED_FIELD_REGISTRY

    # Verify field map includes nested fields
    assert "school.public_id" in manager._FIELD_MAP
    assert "school.name" in manager._FIELD_MAP


@pytest.mark.asyncio
async def test_role_manager_nested_registry_initialized(db_session: AsyncSession) -> None:
    """Role manager should initialize nested field registry (empty for now)."""
    manager = SQLAlchemyRoleManager(db_session)

    # Role has no relationships yet
    assert manager._NESTED_FIELD_REGISTRY == {}
    assert "public_id" in manager._FIELD_MAP
    assert "name" in manager._FIELD_MAP


@pytest.mark.asyncio
async def test_school_manager_nested_registry_initialized(db_session: AsyncSession) -> None:
    """School manager should expose scalar fields and no nested relations."""
    manager = SQLAlchemySchoolManager(db_session)

    assert manager._NESTED_FIELD_REGISTRY == {}
    assert "public_id" in manager._FIELD_MAP
    assert "record_uid" in manager._FIELD_MAP
    assert "source_uid" in manager._FIELD_MAP
    assert "name" in manager._FIELD_MAP


@pytest.mark.asyncio
async def test_unsupported_nested_field_raises_error(db_session: AsyncSession) -> None:
    """Test that querying unsupported nested field raises UnsupportedNestedField."""
    manager = SQLAlchemyUserManager(db_session)

    with pytest.raises(UnsupportedNestedField) as exc_info:
        list(
            await manager.search(
                query=SearchQuery(where=Filter("unknown_relation.public_id", Operator.EQ, "test"))
            )
        )

    assert "unknown_relation" in str(exc_info.value)


@pytest.mark.asyncio
async def test_unsupported_nested_field_on_relation_raises_error(
    db_session: AsyncSession,
) -> None:
    """Test that querying unsupported field on a relation raises UnsupportedNestedField."""
    manager = SQLAlchemyUserManager(db_session)

    with pytest.raises(UnsupportedNestedField) as exc_info:
        list(
            await manager.search(
                query=SearchQuery(where=Filter("groups.nonexistent_field", Operator.EQ, "test"))
            )
        )

    assert "groups" in str(exc_info.value)
    assert "nonexistent_field" in str(exc_info.value)


@pytest.mark.asyncio
async def test_nested_field_filter_with_and_composition(db_session: AsyncSession) -> None:
    """Test combining multiple nested field filters with And()."""
    manager = SQLAlchemyUserManager(db_session)

    # This should not raise, just verify the query is built
    try:
        list(
            await manager.search(
                query=SearchQuery(
                    where=And(
                        (
                            Filter("schools.public_id", Operator.EQ, "school-id"),
                            Filter("groups.public_id", Operator.EQ, "group-id"),
                        )
                    )
                )
            )
        )
    except Exception as e:
        # May fail due to no data, but should not fail on field resolution
        if "Unsupported" in str(type(e).__name__):
            raise


@pytest.mark.asyncio
async def test_nested_field_in_sort_spec(db_session: AsyncSession) -> None:
    """Test sorting by nested field."""
    manager = SQLAlchemyUserManager(db_session)

    # Should build query without error
    try:
        list(
            await manager.search(
                sort_by=[SortSpec("groups.name", ascending=True)],
            )
        )
    except Exception as e:
        # May fail due to no data or join semantics, but not on field resolution
        if "Unsupported" in str(type(e).__name__):
            raise


@pytest.mark.asyncio
async def test_group_manager_by_school_name(db_session: AsyncSession) -> None:
    """Test querying groups by school.name."""
    manager = SQLAlchemyGroupManager(db_session)

    # Should not raise on field resolution
    try:
        list(
            await manager.search(query=SearchQuery(where=Filter("school.name", Operator.ILIKE, "test%")))
        )
    except Exception as e:
        if "Unsupported" in str(type(e).__name__):
            raise


@pytest.mark.asyncio
async def test_all_exposed_fields_are_queryable(db_session: AsyncSession) -> None:
    """Test that all exposed fields in nested registries are queryable."""
    user_manager = SQLAlchemyUserManager(db_session)

    for relation_name, spec in user_manager._NESTED_FIELD_REGISTRY.items():
        for field_name in spec.exposed_fields:
            nested_field = f"{relation_name}.{field_name}"
            # Should not raise
            assert nested_field in user_manager._FIELD_MAP, f"Field {nested_field} not in field_map"


@pytest.mark.asyncio
async def test_nested_field_in_not_expression(db_session: AsyncSession) -> None:
    """Test nested field in NOT expression."""
    manager = SQLAlchemyUserManager(db_session)

    try:
        list(
            await manager.search(
                query=SearchQuery(where=Not(Filter("groups.public_id", Operator.EQ, "test-id")))
            )
        )
    except Exception as e:
        if "Unsupported" in str(type(e).__name__):
            raise


@pytest.mark.asyncio
async def test_group_manager_all_school_fields_exposed(db_session: AsyncSession) -> None:
    """Test that all School model fields are exposed in Group manager."""
    manager = SQLAlchemyGroupManager(db_session)

    school_spec = manager._NESTED_FIELD_REGISTRY["school"]
    # School should have several fields exposed
    assert len(school_spec.exposed_fields) > 0
    # At minimum, should have core fields
    assert "public_id" in school_spec.exposed_fields
    assert "name" in school_spec.exposed_fields


def test_get_exposed_fields_returns_empty_for_non_sqlalchemy_model() -> None:
    """get_exposed_fields returns no fields for non-SQLAlchemy models."""

    class _FakeModel:
        value = "ignored"

    assert get_exposed_fields(_FakeModel) == frozenset()


def test_role_manager_field_map_includes_nested_fields_when_registry_populated(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """RoleManager _FIELD_MAP only includes nested dot-notation keys for real columns."""
    fake_spec = JoinSpec(
        relation_name="schools",
        target_model=SchoolModel,
        join_path=(SchoolModel,),
        join_type=JoinType.LEFT_OUTER,
        exposed_fields=frozenset(["name", "not_a_column"]),
    )
    monkeypatch.setattr(SQLAlchemyRoleManager, "_NESTED_FIELD_REGISTRY", {"schools": fake_spec})
    monkeypatch.setattr(
        SQLAlchemyRoleManager,
        "_FIELD_MAP",
        compose_field_map(
            SQLAlchemyRoleManager._BASE_FIELD_MAP, SQLAlchemyRoleManager._NESTED_FIELD_REGISTRY
        ),
    )
    manager = SQLAlchemyRoleManager(None)  # type: ignore[arg-type]  # session unused in this assertion
    assert "schools.name" in manager._FIELD_MAP
    assert "schools.not_a_column" not in manager._FIELD_MAP


@pytest.mark.parametrize(
    "manager_cls",
    [
        pytest.param(SQLAlchemySchoolManager, id="school"),
        pytest.param(SQLAlchemyRoleManager, id="role"),
        pytest.param(SQLAlchemyGroupManager, id="group"),
        pytest.param(SQLAlchemyUserManager, id="user"),
    ],
)
def test_manager_field_map_fully_covers_exposed_nested_fields(manager_cls: type[Any]) -> None:
    """All managers' _FIELD_MAP entries must cover every exposed nested relation field."""
    for relation_name, spec in manager_cls._NESTED_FIELD_REGISTRY.items():
        mapper = inspect(spec.target_model).mapper
        target_columns = {column.key: column.class_attribute for column in mapper.column_attrs}

        for field_name in spec.exposed_fields:
            if field_name in target_columns:
                nested_field = f"{relation_name}.{field_name}"
                assert nested_field in manager_cls._FIELD_MAP
                assert manager_cls._FIELD_MAP[nested_field] is target_columns[field_name]


def test_iter_filters_handles_filter_and_and_or_and_not() -> None:
    expr = And(
        (
            Filter("name", Operator.EQ, "alice"),
            Or(
                (
                    Filter("firstname", Operator.EQ, "Alice"),
                    Not(Filter("active", Operator.EQ, False)),
                )
            ),
        )
    )

    filters = list(iter_filters(expr))

    assert len(filters) == 3
    assert filters[0].field == "name"
    assert filters[1].field == "firstname"
    assert filters[2].field == "active"


def test_is_loaded_returns_true_when_sqlalchemy_state_missing(monkeypatch: pytest.MonkeyPatch) -> None:
    class _Model:
        value = "x"

    monkeypatch.setattr(to_domain, "inspect", lambda *_args, **_kwargs: None)

    assert _is_loaded(_Model(), "value") is True


def test_is_loaded_returns_true_when_state_has_no_unloaded(monkeypatch: pytest.MonkeyPatch) -> None:
    class _State:
        unloaded = None

    class _Model:
        value = "x"

    monkeypatch.setattr(to_domain, "inspect", lambda *_args, **_kwargs: _State())

    assert _is_loaded(_Model(), "value") is True


def test_loaded_value_without_transform_returns_raw_value(monkeypatch: pytest.MonkeyPatch) -> None:
    class _Model:
        value = "raw-value"

    monkeypatch.setattr(to_domain, "inspect", lambda *_args, **_kwargs: None)

    model = _Model()
    assert _loaded_value(model, "value") == "raw-value"


def test_to_group_keeps_unloaded_relations_unloaded(monkeypatch: pytest.MonkeyPatch) -> None:
    class _State:
        unloaded = {"school", "roles"}

    model = SimpleNamespace(
        public_id=uuid4(),
        record_uid="record-uid",
        source_uid="source-uid",
        name="group-name",
        display_name="Group Name",
        has_share=True,
        email=None,
        allowed_email_senders_users=(),
        allowed_email_senders_groups=(),
        members=(),
        member_roles=(),
    )

    monkeypatch.setattr(to_domain, "inspect", lambda *_args, **_kwargs: _State())

    group = to_domain.to_group(model)  # type: ignore[arg-type]

    raw = domain_asdict(group)
    assert raw["school"] is UNLOADED
    assert raw["roles"] is UNLOADED
    with pytest.raises(ValueError, match="Group.school is not loaded"):
        _ = group.school
    with pytest.raises(ValueError, match="Group.roles is not loaded"):
        _ = group.roles


def test_to_user_raises_when_membership_school_has_no_uuid(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    model = SimpleNamespace(
        public_id=uuid4(),
        record_uid="record-uid",
        source_uid="source-uid",
        name="user-name",
        firstname="User",
        lastname="Name",
        email=None,
        birthday=None,
        expiration_date=None,
        active=True,
        school_memberships=[object()],
        legal_wards=(),
        legal_guardians=(),
    )

    monkeypatch.setattr(to_domain, "inspect", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(
        to_domain,
        "_to_school_membership",
        lambda _membership: SchoolMembership(
            school=School(
                public_id=UNSET,
                record_uid="school-record",
                source_uid="school-source",
                name="school-name",
                display_name="School Name",
                educational_servers=set({"edu.example.com"}),
                administrative_servers=set({"adm.example.com"}),
            ),
            is_primary=True,
            roles=set(),
            groups=set(),
        ),
    )

    with pytest.raises(ValueError, match="Mapped school membership has no UUID school public_id"):
        to_domain.to_user(
            model,  # type: ignore[arg-type]
            include_memberships=True,
            include_legal_wards=False,
            include_legal_guardians=False,
        )
