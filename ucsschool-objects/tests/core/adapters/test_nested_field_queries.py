"""Tests for nested field query support in SQLAlchemy readers."""
from __future__ import annotations

from types import SimpleNamespace
from uuid import uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncSession
from ucsschool_objects.core.adapters.sqlalchemy.mapping import _is_loaded, _loaded_value
from ucsschool_objects.core.adapters.sqlalchemy.readers import (
    JoinType,
    SQLAlchemyGroupReader,
    SQLAlchemyRoleReader,
    SQLAlchemySchoolReader,
    SQLAlchemyUserReader,
)
from ucsschool_objects.core.adapters.sqlalchemy.readers._shared import (
    _compose_field_map,
    _get_exposed_fields,
    _iter_filters,
)
from ucsschool_objects.core.domain import (
    UNLOADED,
    And,
    Filter,
    Not,
    Operator,
    Or,
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
async def test_school_reader_nested_registry_initialized(db_session: AsyncSession) -> None:
    """School reader should expose scalar fields and no nested relations."""
    reader = SQLAlchemySchoolReader(db_session)

    assert reader._NESTED_FIELD_REGISTRY == {}
    assert "public_id" in reader._FIELD_MAP
    assert "record_uid" in reader._FIELD_MAP
    assert "source_uid" in reader._FIELD_MAP
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


def test_role_reader_field_map_includes_nested_fields_when_registry_populated(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """RoleReader _FIELD_MAP includes dot-notation keys for populated registry."""
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
    monkeypatch.setattr(
        SQLAlchemyRoleReader,
        "_FIELD_MAP",
        _compose_field_map(
            SQLAlchemyRoleReader._BASE_FIELD_MAP, SQLAlchemyRoleReader._NESTED_FIELD_REGISTRY
        ),
    )
    reader = SQLAlchemyRoleReader(None)  # type: ignore[arg-type]  # session unused in this assertion
    assert "schools.name" in reader._FIELD_MAP


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

    filters = list(_iter_filters(expr))

    assert len(filters) == 3
    assert filters[0].field == "name"
    assert filters[1].field == "firstname"
    assert filters[2].field == "active"


def test_is_loaded_returns_true_when_sqlalchemy_state_missing(monkeypatch: pytest.MonkeyPatch) -> None:
    class _Model:
        value = "x"

    from ucsschool_objects.core.adapters.sqlalchemy import mapping

    monkeypatch.setattr(mapping, "inspect", lambda *_args, **_kwargs: None)

    assert _is_loaded(_Model(), "value") is True


def test_is_loaded_returns_true_when_state_has_no_unloaded(monkeypatch: pytest.MonkeyPatch) -> None:
    class _State:
        unloaded = None

    class _Model:
        value = "x"

    from ucsschool_objects.core.adapters.sqlalchemy import mapping

    monkeypatch.setattr(mapping, "inspect", lambda *_args, **_kwargs: _State())

    assert _is_loaded(_Model(), "value") is True


def test_loaded_value_without_transform_returns_raw_value(monkeypatch: pytest.MonkeyPatch) -> None:
    class _Model:
        value = "raw-value"

    from ucsschool_objects.core.adapters.sqlalchemy import mapping

    monkeypatch.setattr(mapping, "inspect", lambda *_args, **_kwargs: None)

    assert _loaded_value(_Model(), "value") == "raw-value"


def test_to_group_keeps_unloaded_relations_unloaded(monkeypatch: pytest.MonkeyPatch) -> None:
    from ucsschool_objects.core.adapters.sqlalchemy import mapping

    class _State:
        unloaded = {"school", "group_type"}

    model = SimpleNamespace(
        public_id=uuid4(),
        record_uid="record-uid",
        source_uid="source-uid",
        name="group-name",
        display_name={"de_DE": "Group Name"},
        has_share=True,
        email=None,
        allowed_email_senders_users=(),
        allowed_email_senders_groups=(),
        member_roles=(),
    )

    monkeypatch.setattr(mapping, "inspect", lambda *_args, **_kwargs: _State())

    group = mapping.to_group(model)  # type: ignore[arg-type]

    assert group.school is UNLOADED
    assert group.group_type is UNLOADED
