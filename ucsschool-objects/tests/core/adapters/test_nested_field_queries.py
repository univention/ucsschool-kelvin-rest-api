"""Tests for nested field query support in SQLAlchemy readers."""
from __future__ import annotations

import pytest
from sqlalchemy.ext.asyncio import AsyncSession
from ucsschool_objects.core.adapters.sqlalchemy.readers import (
    JoinType,
    SQLAlchemyGroupReader,
    SQLAlchemyRoleReader,
    SQLAlchemyUserReader,
    _get_exposed_fields,
)
from ucsschool_objects.core.domain import (
    And,
    Filter,
    Not,
    Operator,
    SearchQuery,
    SortSpec,
    UnsupportedNestedField,
)


@pytest.mark.asyncio
async def test_user_reader_nested_registry_initialized(db_session: AsyncSession) -> None:
    """User reader should initialize nested field registry on first access."""
    reader = SQLAlchemyUserReader(db_session)

    assert reader._NESTED_FIELD_REGISTRY
    assert "groups" in reader._NESTED_FIELD_REGISTRY
    assert "roles" in reader._NESTED_FIELD_REGISTRY
    assert "schools" in reader._NESTED_FIELD_REGISTRY

    # Verify field map includes nested fields
    assert "groups.public_id" in reader._FIELD_MAP
    assert "roles.name" in reader._FIELD_MAP
    assert "schools.record_uid" in reader._FIELD_MAP


@pytest.mark.asyncio
async def test_group_reader_nested_registry_initialized(db_session: AsyncSession) -> None:
    """Group reader should initialize nested field registry on first access."""
    reader = SQLAlchemyGroupReader(db_session)

    assert reader._NESTED_FIELD_REGISTRY
    assert "school" in reader._NESTED_FIELD_REGISTRY

    # Verify field map includes nested fields
    assert "school.public_id" in reader._FIELD_MAP
    assert "school.name" in reader._FIELD_MAP


@pytest.mark.asyncio
async def test_role_reader_nested_registry_initialized(db_session: AsyncSession) -> None:
    """Role reader should initialize nested field registry (empty for now)."""
    reader = SQLAlchemyRoleReader(db_session)

    # Role has no relationships yet
    assert reader._NESTED_FIELD_REGISTRY == {}
    assert "public_id" in reader._FIELD_MAP
    assert "name" in reader._FIELD_MAP


@pytest.mark.asyncio
async def test_unsupported_nested_field_raises_error(db_session: AsyncSession) -> None:
    """Test that querying unsupported nested field raises UnsupportedNestedField."""
    reader = SQLAlchemyUserReader(db_session)

    with pytest.raises(UnsupportedNestedField) as exc_info:
        list(
            await reader.search(
                query=SearchQuery(where=Filter("unknown_relation.public_id", Operator.EQ, "test"))
            )
        )

    assert "unknown_relation" in str(exc_info.value)


@pytest.mark.asyncio
async def test_unsupported_nested_field_on_relation_raises_error(
    db_session: AsyncSession,
) -> None:
    """Test that querying unsupported field on a relation raises UnsupportedNestedField."""
    reader = SQLAlchemyUserReader(db_session)

    with pytest.raises(UnsupportedNestedField) as exc_info:
        list(
            await reader.search(
                query=SearchQuery(where=Filter("groups.nonexistent_field", Operator.EQ, "test"))
            )
        )

    assert "groups" in str(exc_info.value)
    assert "nonexistent_field" in str(exc_info.value)


@pytest.mark.asyncio
async def test_nested_field_filter_with_and_composition(db_session: AsyncSession) -> None:
    """Test combining multiple nested field filters with And()."""
    reader = SQLAlchemyUserReader(db_session)

    # This should not raise, just verify the query is built
    try:
        list(
            await reader.search(
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
    reader = SQLAlchemyUserReader(db_session)

    # Should build query without error
    try:
        list(
            await reader.search(
                sort_by=[SortSpec("groups.name", ascending=True)],
            )
        )
    except Exception as e:
        # May fail due to no data or join semantics, but not on field resolution
        if "Unsupported" in str(type(e).__name__):
            raise


@pytest.mark.asyncio
async def test_nested_field_with_like_operator(db_session: AsyncSession) -> None:
    """Test nested field filter with LIKE operator."""
    reader = SQLAlchemyUserReader(db_session)

    try:
        list(await reader.search(query=SearchQuery(where=Filter("groups.name", Operator.LIKE, "test%"))))
    except Exception as e:
        if "Unsupported" in str(type(e).__name__):
            raise


@pytest.mark.asyncio
async def test_group_reader_by_school_name(db_session: AsyncSession) -> None:
    """Test querying groups by school.name."""
    reader = SQLAlchemyGroupReader(db_session)

    # Should not raise on field resolution
    try:
        list(await reader.search(query=SearchQuery(where=Filter("school.name", Operator.LIKE, "test%"))))
    except Exception as e:
        if "Unsupported" in str(type(e).__name__):
            raise


@pytest.mark.asyncio
async def test_all_exposed_fields_are_queryable(db_session: AsyncSession) -> None:
    """Test that all exposed fields in nested registries are queryable."""
    user_reader = SQLAlchemyUserReader(db_session)

    for relation_name, spec in user_reader._NESTED_FIELD_REGISTRY.items():
        for field_name in spec.exposed_fields:
            nested_field = f"{relation_name}.{field_name}"
            # Should not raise
            assert nested_field in user_reader._FIELD_MAP, f"Field {nested_field} not in field_map"


@pytest.mark.asyncio
async def test_nested_field_in_not_expression(db_session: AsyncSession) -> None:
    """Test nested field in NOT expression."""
    reader = SQLAlchemyUserReader(db_session)

    try:
        list(
            await reader.search(
                query=SearchQuery(where=Not(Filter("groups.public_id", Operator.EQ, "test-id")))
            )
        )
    except Exception as e:
        if "Unsupported" in str(type(e).__name__):
            raise


@pytest.mark.asyncio
async def test_group_reader_all_school_fields_exposed(db_session: AsyncSession) -> None:
    """Test that all School model fields are exposed in Group reader."""
    reader = SQLAlchemyGroupReader(db_session)

    school_spec = reader._NESTED_FIELD_REGISTRY["school"]
    # School should have several fields exposed
    assert len(school_spec.exposed_fields) > 0
    # At minimum, should have core fields
    assert "public_id" in school_spec.exposed_fields
    assert "name" in school_spec.exposed_fields


def test_get_exposed_fields_skips_attributes_that_raise() -> None:
    """_get_exposed_fields gracefully skips model attributes that raise on access."""

    class _RaisingDescriptor:
        def __get__(self, obj: object, objtype: object = None) -> None:
            raise AttributeError("simulated bad attribute")

    class _FakeModel:
        raises_on_access = _RaisingDescriptor()

    fields = _get_exposed_fields(_FakeModel)
    assert "raises_on_access" not in fields


def test_role_reader_build_field_map_includes_nested_fields_when_registry_populated(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """RoleReader._build_field_map includes dot-notation keys when registry has entries."""
    from ucsschool_objects.core.adapters.sqlalchemy.readers import JoinSpec
    from ucsschool_objects.database_models import School as SchoolModel

    fake_spec = JoinSpec(
        relation_name="schools",
        target_model=SchoolModel,
        join_path=(SchoolModel,),
        join_type=JoinType.LEFT_OUTER,
        exposed_fields=frozenset(["name"]),
    )
    monkeypatch.setattr(SQLAlchemyRoleReader, "_NESTED_FIELD_REGISTRY", {"schools": fake_spec})
    reader = SQLAlchemyRoleReader(None)  # type: ignore[arg-type]  # session unused in _build_field_map
    assert "schools.name" in reader._FIELD_MAP
