from streamlit.testing.v1 import AppTest

from jolteon.dashboard.ui.table import sign_class


def table_script():
    import pandas as pd
    import streamlit as st

    from jolteon.dashboard.ui import table

    st.write("before")
    table.render(
        pd.DataFrame({"Side": ["BUY", "SELL"], "Edge": [2.0, -1.0]}),
        shaded_columns=["Edge"],
        format_fn=lambda value: f"{value:+.2f}",
        column_help={"Edge": 'How far from fair value <"in our favour">.'},
        row_style=(
            lambda row: (
                "background-color: pink" if row["Side"] == "SELL" else ""
            )
        ),
    )


def numeric_script():
    import pandas as pd

    from jolteon.dashboard.ui import table

    table.render(
        pd.DataFrame(
            {"Horizon": ["+1s"], "Gross": [2.0], "Gross bps": ["+95.24"]}
        ),
        shaded_columns=["Gross"],
        numeric_columns=["Gross bps"],
        format_fn=lambda value: f"{value:+.2f}",
    )


def missing_script():
    import pandas as pd

    from jolteon.dashboard.ui import table

    table.render(
        pd.DataFrame({"Horizon": ["+1s"], "Edge": [float("nan")]}),
        shaded_columns=["Edge"],
        format_fn=lambda value: "–" if pd.isna(value) else f"{value:+.2f}",
    )


def test_a_cell_is_coloured_by_its_sign_alone():
    """Zero sits with the positives, the side a formatted figure puts
    its plus on, so a figure and its colour never disagree."""
    assert sign_class(10.0) == "jolteon-positive"
    assert sign_class(0.1) == "jolteon-positive"
    assert sign_class(0.0) == "jolteon-positive"
    assert sign_class(-5.0) == "jolteon-negative"


def test_a_missing_value_is_not_coloured():
    assert sign_class(float("nan")) == ""


def test_the_table_renders_its_rows_and_colours_its_numbers(tables):
    at = AppTest.from_function(table_script).run()

    assert not at.exception
    table = tables(at)[0]
    assert table["columns"] == ["Side", "Edge"]
    assert table["rows"] == [["BUY", "+2.00"], ["SELL", "-1.00"]]
    # The winning figure is green and the losing one red, in the text
    # alone: the cell carries no tint, however large the figure.
    body = at.get("html")[-1].body
    assert '<td class="jolteon-num jolteon-positive">+2.00</td>' in body
    assert '<td class="jolteon-num jolteon-negative">-1.00</td>' in body
    assert table["styles"][0][1] == ""
    assert table["styles"][1][1] == ""


def test_a_signed_columns_colour_is_on_its_text_not_its_cell():
    at = AppTest.from_function(table_script).run()

    css = at.get("html")[-1].body.split("</style>", 1)[0]
    assert (
        ".jolteon-table td.jolteon-positive { color: var(--positive); }" in css
    )
    assert (
        ".jolteon-table td.jolteon-negative { color: var(--negative); }" in css
    )
    assert "background-color" not in css


def test_a_missing_figure_in_a_signed_column_is_left_uncoloured():
    at = AppTest.from_function(missing_script).run()

    assert not at.exception
    body = at.get("html")[-1].body
    assert '<td class="jolteon-num">–</td>' in body


def test_a_row_style_tints_the_columns_that_are_not_numbers(tables):
    at = AppTest.from_function(table_script).run()

    styles = tables(at)[0]["styles"]
    assert styles[0][0] == ""
    assert styles[1][0] == "background-color: pink"


def test_a_columns_explanation_rides_on_its_own_header():
    at = AppTest.from_function(table_script).run()

    body = at.get("html")[-1].body
    # Escaped, so an explanation carrying quotes or angle brackets cannot
    # break out of the attribute it is written into.
    assert "&lt;&quot;in our favour&quot;&gt;" in body
    assert 'class="jolteon-help"' in body


def test_a_table_rules_only_between_its_rows():
    """One hairline between rows, no vertical rules and no frame around
    the whole thing."""
    at = AppTest.from_function(table_script).run()

    body = at.get("html")[-1].body
    assert "border-top: 1px solid var(--rule)" in body
    assert "border-left" not in body
    assert "border-right" not in body


def test_a_wide_table_scrolls_inside_its_own_wrapper():
    """The page itself must never scroll sideways, so a table too wide
    for its card scrolls within it."""
    at = AppTest.from_function(table_script).run()

    body = at.get("html")[-1].body
    assert (
        '<div class="jolteon-table-wrap"><table class="jolteon-table">' in body
    )
    assert "overflow-x: auto" in body


def test_a_numeric_column_aligns_right_without_being_tinted(tables):
    """A column carrying its own formatting, or measured in units
    `format_fn` does not speak, still reads as a column of numbers."""
    at = AppTest.from_function(numeric_script).run()

    assert not at.exception
    body = at.get("html")[-1].body
    assert '<td class="jolteon-num" style="">+95.24</td>' in body
    # Its header aligns with it, and nothing tints the cell itself.
    assert body.count('<th class="jolteon-num">') == 2
    assert tables(at)[0]["styles"][0][2] == ""


def test_a_column_that_is_neither_shaded_nor_numeric_reads_as_a_label():
    at = AppTest.from_function(numeric_script).run()

    body = at.get("html")[-1].body
    assert "<th>Horizon</th>" in body
