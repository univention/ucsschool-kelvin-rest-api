import pytest
from ucsschool_objects.core.domain import And, Filter, Not, Operator, Or, SearchQuery, SortSpec


@pytest.mark.parametrize("operator", [Operator.LIKE, Operator.ILIKE])
def test_query_ast_structures(operator: Operator) -> None:
    expr = And(
        clauses=(
            Filter(field="name", op=operator, value="alice%"),
            Not(clause=Or(clauses=(Filter(field="active", op=Operator.EQ, value=False),))),
        )
    )
    query = SearchQuery(where=expr)
    sort = SortSpec(field="public_id", ascending=False)

    assert isinstance(query.where, And)
    assert sort.ascending is False
