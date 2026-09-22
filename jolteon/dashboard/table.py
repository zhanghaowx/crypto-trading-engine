"""The dashboard's table: recorded figures as rows a reader can scan.

Untitled UI's table rather than Streamlit's data grid. The grid is drawn
to a canvas, rules every cell on both axes and cannot be restyled, so a
table of a handful of rows read as a spreadsheet dropped into the card
rather than as part of it. These are small, read-only tables; plain HTML
carries them, and carries the shading and the per-column explanations
with them.
"""

from html import escape
from pathlib import Path
from typing import Callable, Mapping, Sequence

import pandas as pd
import streamlit as st

from jolteon.dashboard.components import NEGATIVE_RGB, POSITIVE_RGB

_TABLE_CSS = (
    Path(__file__).resolve().parent / "static" / "table.css"
).read_text()

# How deep a shaded cell is tinted at its column's largest magnitude. Well
# below the data grid's own shading: a hairline already separates the
# rows, so the tint only has to rank the numbers, not draw the cell.
_MIN_TINT = 0.05
_MAX_TINT = 0.22


def shade(value: float, scale: float) -> str:
    """
    Returns: A background tint for a signed cell, deeper the further
    `value` sits from zero relative to `scale` (its column's own largest
    magnitude) - so the standout numbers in a row of tightly-packed
    figures read through color rather than through size.
    """
    if pd.isna(value) or not scale:
        return ""
    intensity = min(abs(value) / scale, 1.0)
    r, g, b = POSITIVE_RGB if value >= 0 else NEGATIVE_RGB
    alpha = _MIN_TINT + (_MAX_TINT - _MIN_TINT) * intensity
    return f"background-color: rgba({r}, {g}, {b}, {alpha:.2f})"


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

    `shaded_columns` are tinted by `shade` and formatted with `format_fn`.
    `numeric_columns` are read as numbers without being tinted - for a
    column already carrying its own formatting, or one measured in units
    `format_fn` does not speak. Both align right and share one set of
    digit widths, so the decimal points line up down the column.
    `column_help` explains a column on its own header; `row_style` tints a
    whole row from its values.
    """
    columns = list(frame.columns)
    shaded = set(shaded_columns)
    numeric = shaded | set(numeric_columns)
    scales = {
        column: frame[column].abs().max(skipna=True) for column in shaded
    }

    rows = []
    for _, row in frame.iterrows():
        cells = []
        for column in columns:
            value = row[column]
            if column in shaded:
                style = shade(value, scales[column])
                shown = format_fn(value) if format_fn else value
                cells.append(
                    f'<td class="jolteon-num" style="{style}">'
                    f"{escape(str(shown))}</td>"
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
        f'<table class="jolteon-table">'
        f"<thead>{_header(columns, column_help or {}, numeric)}</thead>"
        f"<tbody>{''.join(rows)}</tbody></table>"
    )
