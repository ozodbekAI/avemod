from __future__ import annotations

from sqlalchemy.sql.elements import ColumnElement


def apply_sort_direction(
    column: ColumnElement, direction: str = "desc"
) -> ColumnElement:
    ordered = column.asc() if direction == "asc" else column.desc()
    try:
        return ordered.nullslast()
    except AttributeError:
        return ordered
