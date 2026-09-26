"""The dashboard's table: recorded figures as rows a reader can scan.

Plain HTML rather than Streamlit's data grid. The grid is drawn to a
canvas, rules every cell on both axes and cannot be restyled, so a table
of a handful of rows read as a spreadsheet dropped into the card rather
than as part of it. These are small, read-only tables; plain HTML carries
them, and carries the colour of a signed figure and the per-column
explanations with them.
"""

from html import escape
from pathlib import Path
from typing import Callable, Mapping, Sequence

import pandas as pd
import streamlit as st

_TABLE_CSS = (
    Path(__file__).resolve().parents[1] / "static" / "table.css"
).read_text()


def sign_class(value: float) -> str:
    """
    Returns: The class that colours a signed cell's figure - the winning
    colour at or above zero, where a formatted figure wears a plus, the
    losing one below - and nothing for a value that is not there.
    """
    if pd.isna(value):
        return ""
    return "jolteon-positive" if value >= 0 else "jolteon-negative"


def _header(
    columns: Sequence[str], help_text: Mapping[str, str], numeric
) -> str:
    cells = []
    for column in columns:
        classes = ' class="jolteon-num"' if column in numeric else ""
        explanation = help_text.get(column)
        mark = (
            f'<span class="jolteon-help"'
            f' title="{escape(explanation)}">?</span>'
            if explanation
            else ""
        )
        cells.append(f"<th{classes}>{escape(str(column))}{mark}</th>")
    return "<tr>" + "".join(cells) + "</tr>"


def render(
    frame: pd.DataFrame,
    *,
    shaded_columns: Sequence[str] = (),
    numeric_columns: Sequence[str] = (),
    format_fn: Callable[[float], str] | None = None,
    column_help: Mapping[str, str] | None = None,
    row_style: Callable[[pd.Series], str] | None = None,
) -> None:
    """
    Draw `frame` as a table.

    `shaded_columns` carry their sign in the colour of the figure, by
    `sign_class`, and are formatted with `format_fn`.
    `numeric_columns` are read as numbers without being coloured - for a
    column already carrying its own formatting, or one measured in units
    `format_fn` does not speak. Both align right and share one set of
    digit widths, so the decimal points line up down the column.
    `column_help` explains a column on its own header; `row_style` tints a
    whole row from its values.
    """
    columns = list(frame.columns)
    shaded = set(shaded_columns)
    numeric = shaded | set(numeric_columns)

    rows = []
    for _, row in frame.iterrows():
        cells = []
        for column in columns:
            value = row[column]
            if column in shaded:
                sign = sign_class(value)
                classes = f"jolteon-num {sign}" if sign else "jolteon-num"
                shown = format_fn(value) if format_fn else value
                cells.append(
                    f'<td class="{classes}">{escape(str(shown))}</td>'
                )
            else:
                style = row_style(row) if row_style else ""
                classes = ' class="jolteon-num"' if column in numeric else ""
                cells.append(
                    f'<td{classes} style="{style}">{escape(str(value))}</td>'
                )
        rows.append("<tr>" + "".join(cells) + "</tr>")

    st.html(
        f"<style>{_TABLE_CSS}</style>"
        f'<div class="jolteon-table-wrap"><table class="jolteon-table">'
        f"<thead>{_header(columns, column_help or {}, numeric)}</thead>"
        f"<tbody>{''.join(rows)}</tbody></table></div>"
    )
