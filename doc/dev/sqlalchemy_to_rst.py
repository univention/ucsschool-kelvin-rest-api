"""
Convert SQLAlchemy ORM models to Sphinx/RST list-table directives.

LLM generated with minor adjustments

Usage:
    from model_to_rst import model_to_rst
    print(model_to_rst(MyModel))

Ref: https://docs.sqlalchemy.org/en/20/orm/mapping_api.html
"""

import pathlib
from typing import Any

import pytest
from sqlalchemy import Integer, String, UniqueConstraint, inspect as sa_inspect
from sqlalchemy.ext.hybrid import hybrid_property
from sqlalchemy.orm import DeclarativeBase, Mapped, RelationshipDirection, mapped_column

# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _fmt_default(col) -> str:
    """Render column default (Python-side or server-side) as a string."""
    if col.default is not None:
        arg = col.default.arg
        if callable(arg) and not isinstance(arg, str):
            return f"``{arg.__name__}()``"
        return f"``{arg!r}``"
    if col.server_default is not None:
        text = col.server_default.arg
        if hasattr(text, "text"):  # text clause
            text = text.text
        return f"``{text}`` *(server)*"
    return ""


def _fmt_type(col_type) -> str:
    """Render a column type, handling dialect-specific types gracefully."""
    try:
        # Compile to a generic string, e.g. VARCHAR(50)
        s = str(col_type)
    except Exception:
        s = type(col_type).__name__
    return f"``{s}``"


def _bool_icon(val: bool) -> str:
    return "✓" if val else ""


def _rst_escape(text: str) -> str:
    """Escape characters that would break RST table cells."""
    return text.replace("*", "\\*").replace("|", "\\|")


def _list_table(
    title: str,
    headers: list[str],
    widths: list[int],
    rows: list[list[str]],
) -> str:
    """Build a ``.. list-table::`` directive."""
    lines: list[str] = []
    lines.append(f".. list-table:: {title}")
    lines.append("   :header-rows: 1")
    lines.append(f"   :widths: {' '.join(str(w) for w in widths)}")
    lines.append("")

    def _row(cells: list[str]) -> str:
        first, *rest = cells
        parts = [f"   * - {first}"]
        parts.extend(f"     - {c}" if c else "     -" for c in rest)
        return "\n".join(parts)

    lines.append(_row(headers))
    for row in rows:
        lines.append(_row(row))

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def model_to_rst(
    model_class: type[Any],
    *,
    include_columns: bool = False,
    # include_columns_descriptions: bool = False,
    include_constraints: bool = False,
    include_hybrid: bool = False,
    include_relationships: bool = False,
) -> str:
    """Return an RST string documenting *model_class*'s columns & relationships.

    Parameters
    ----------
    model_class:
        A mapped SQLAlchemy ORM class.
    include_columns:
        Emit the columns table.
    include_constraints:
        Emit a table for composite unique constraints.
        Documents the ``info={"doc": "..."}`` metadata on each constraint.
    include_hybrid:
        Also list ``@hybrid_property`` descriptors.
    include_relationships:
        Emit a second table for relationships.
    """
    mapper = sa_inspect(model_class)
    name = model_class.__name__

    sections: list[str] = []

    # ---- columns table ----------------------------------------------------
    if include_columns:
        # Collect columns that participate in composite unique constraints

        composite_uq: dict[str, list[str]] = {}  # col_name -> list of constraint labels
        for const in mapper.local_table.constraints:
            if isinstance(const, UniqueConstraint) and len(const.columns) > 1:
                col_names = [c.name for c in const.columns]
                # label = const.name or "(" + ", ".join(col_names) + ")"
                label = "(" + ", ".join(col_names) + ")"
                for cn in col_names:
                    composite_uq.setdefault(cn, []).append(label)

        col_headers = ["Name", "Type", "PK", "Nullable", "Unique", "Default"]  # , "Description"]
        col_widths = [14, 12, 5, 5, 10, 15]  # , 35]
        col_rows: list[list[str]] = []

        for col in mapper.columns:
            # Determine unique status
            if col.unique:
                uq_cell = "✓"
            elif col.name in composite_uq:
                uq_cell = ", ".join(
                    f"``{constraint_label}``" for constraint_label in composite_uq[col.name]
                )
            else:
                uq_cell = ""

            col_rows.append(
                [
                    f"``{col.name}``",
                    _fmt_type(col.type),
                    _bool_icon(col.primary_key),
                    _bool_icon(col.nullable),
                    uq_cell,
                    _fmt_default(col)
                    # _rst_escape(col.doc or ""),
                ]
            )

        col_headers_2 = ["Name", "Description", "UDM"]
        col_widths_2 = [14, 28, 14]
        col_rows_2: list[list[str]] = []

        for col in mapper.columns:
            doc = col.info["doc"] if "doc" in col.info else ""
            udm_attr = col.info["udm_attr"] if "udm_attr" in col.info else ""
            if len(doc) == 0 and len(udm_attr) == 0:
                continue
            col_rows_2.append(
                [
                    f"``{col.name}``",
                    _rst_escape(doc),
                    f"``{_rst_escape(udm_attr)}``",
                ]
            )
        if len(col_rows_2) > 0:
            sections.append(_list_table(f"{name} — Columns (Part 1)", col_headers, col_widths, col_rows))
            sections.append("")
            sections.append(
                _list_table(f"{name} — Columns (Part 2)", col_headers_2, col_widths_2, col_rows_2)
            )
            sections.append("")
        else:
            sections.append(_list_table(f"{name} — Columns", col_headers, col_widths, col_rows))
            sections.append("")

    # ---- unique constraints -----------------------------------------------
    if include_constraints:
        uq_rows: list[list[str]] = []
        for const in mapper.local_table.constraints:
            if isinstance(const, UniqueConstraint):
                cols = [c.name for c in const.columns]
                if len(cols) < 2:
                    continue  # single-column uniques already shown in the column table
                label = const.name or "(unnamed)"
                doc = const.info.get("doc", "") if const.info else ""
                uq_rows.append([f"``{label}``", ", ".join(f"``{c}``" for c in cols), _rst_escape(doc)])

        if uq_rows:
            uq_headers = ["Constraint", "Columns", "Description"]
            uq_widths = [25, 35, 40]
            sections.append(_list_table(f"{name} — Unique constraints", uq_headers, uq_widths, uq_rows))
            sections.append("")

    # ---- hybrid properties ------------------------------------------------
    if include_hybrid:
        hybrids: list[tuple[str, str, str]] = []
        for key, desc in mapper.all_orm_descriptors.items():
            if isinstance(desc, hybrid_property):
                rtype = ""
                if desc.fget is not None:
                    ann = getattr(desc.fget, "__annotations__", {})
                    if "return" in ann:
                        rtype = f"``{ann['return']}``"
                doc = ""
                if desc.fget and desc.fget.__doc__:
                    doc = desc.fget.__doc__.strip().split("\n")[0]
                hybrids.append((f"``{key}``", rtype, doc))

        if hybrids:
            h_headers = ["Name", "Return type", "Description"]
            h_widths = [25, 25, 50]
            h_rows = [list(h) for h in hybrids]
            sections.append(_list_table(f"{name} — Hybrid properties", h_headers, h_widths, h_rows))
            sections.append("")

    # ---- relationships table ----------------------------------------------
    if include_relationships and mapper.relationships:
        _DIR_LABEL = {
            RelationshipDirection.ONETOMANY: "One → Many",
            RelationshipDirection.MANYTOONE: "Many → One",
            RelationshipDirection.MANYTOMANY: "Many ↔ Many",
        }
        rel_headers = ["Attribute", "Target", "Direction", "Collection", "Back-ref"]
        rel_widths = [20, 20, 15, 10, 20]
        rel_rows: list[list[str]] = []

        for rel in mapper.relationships:
            back = rel.back_populates or ""
            if not back and rel.backref:
                back = rel.backref if isinstance(rel.backref, str) else rel.backref[0]
            rel_rows.append(
                [
                    f"``{rel.key}``",
                    f"``{rel.mapper.class_.__name__}``",
                    _DIR_LABEL.get(rel.direction, str(rel.direction)),
                    _bool_icon(rel.uselist),
                    f"``{back}``" if back else "",
                ]
            )

        sections.append(_list_table(f"{name} — Relationships", rel_headers, rel_widths, rel_rows))
        sections.append("")

    return "\n".join(sections)


def render_rst():
    from argparse import ArgumentParser

    parser = ArgumentParser()
    parser.add_argument("model", nargs="+", type=str, help="Models to render")
    parser.add_argument("outdir", type=str, help="Output directory")
    parser.add_argument(
        "--table-types",
        nargs="+",
        type=str,
        default=["attributes", "relations"],
        help="Table types to render.",
        choices=["attributes", "relations", "constraints"],
    )
    args = parser.parse_args()

    outdir = pathlib.Path(args.outdir)
    outdir.mkdir(parents=True, exist_ok=True)

    import ucsschool_objects.database_models

    for model in args.model:
        sql_model = getattr(ucsschool_objects.database_models, model)
        for table_type in args.table_types:
            rst_table = ""
            match table_type:
                case "attributes":
                    rst_table = model_to_rst(sql_model, include_columns=True)
                case "relations":
                    rst_table = model_to_rst(sql_model, include_relationships=True)
                case "constraints":
                    rst_table = model_to_rst(sql_model, include_constraints=True)
                case _:
                    raise ValueError(f"Unknown table type: {table_type}")

            with open(outdir / f"{model.lower()}-{table_type}.rst", "w") as f:
                f.write(rst_table)


if __name__ == "__main__":
    render_rst()


# ---------------------------------------------------------------------------
# Inline unit tests  (run with:  pytest doc/dev/sqlalchemy_to_rst.py)
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def sample_model():
    """A minimal in-memory SQLAlchemy model used across model_to_rst tests."""

    class Base(DeclarativeBase):
        pass

    class SampleModel(Base):
        __tablename__ = "sample"
        __table_args__ = (UniqueConstraint("first_name", "last_name", name="uq_full_name"),)

        id: Mapped[int] = mapped_column(Integer, primary_key=True)
        first_name: Mapped[str] = mapped_column(
            String(50), nullable=False, info={"doc": "Given name", "udm_attr": "firstname"}
        )
        last_name: Mapped[str] = mapped_column(
            String(50), nullable=False, info={"doc": "Family name", "udm_attr": "lastname"}
        )
        status: Mapped[str] = mapped_column(String(20), default="active")

        @hybrid_property
        def full_name(self) -> str:
            """Full name of the person."""
            return f"{self.first_name} {self.last_name}"

    return SampleModel


def test_model_to_rst_columns_section_present(sample_model):
    out = model_to_rst(sample_model, include_columns=True)
    assert "SampleModel" in out
    assert "``id``" in out
    assert "``first_name``" in out


def test_model_to_rst_columns_part2_rendered_when_info_present(sample_model):
    out = model_to_rst(sample_model, include_columns=True)
    assert "Part 2" in out
    assert "Given name" in out
    assert "``firstname``" in out


def test_model_to_rst_default_shown_in_columns(sample_model):
    out = model_to_rst(sample_model, include_columns=True)
    assert "``'active'``" in out


def test_model_to_rst_constraints_section(sample_model):
    out = model_to_rst(sample_model, include_constraints=True)
    assert "Unique constraints" in out
    assert "uq_full_name" in out


def test_model_to_rst_hybrid_section(sample_model):
    out = model_to_rst(sample_model, include_hybrid=True)
    assert "Hybrid properties" in out
    assert "``full_name``" in out


def test_model_to_rst_empty_output_when_nothing_enabled(sample_model):
    assert model_to_rst(sample_model).strip() == ""


def test_model_to_rst_no_relationships_when_none_defined(sample_model):
    out = model_to_rst(sample_model, include_relationships=True)
    assert "Relationships" not in out
