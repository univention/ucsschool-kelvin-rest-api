from ucsschool.kelvin.corelib.domain import And, Filter, Not, Operator, Or, SearchQuery, SortSpec


def test_query_ast_structures() -> None:
    expr = And(
        clauses=(
            Filter(field="name", op=Operator.LIKE, value="alice%"),
            Not(clause=Or(clauses=(Filter(field="active", op=Operator.EQ, value=False),))),
        )
    )
    query = SearchQuery(where=expr)
    sort = SortSpec(field="public_id", ascending=False)

    assert isinstance(query.where, And)
    assert sort.ascending is False
