from streamlit.testing.v1 import AppTest

from jolteon.dashboard.table import shade


def table_script():
    import pandas as pd
    import streamlit as st

    from jolteon.dashboard import table

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

    from jolteon.dashboard import table

    table.render(
        pd.DataFrame(
            {"Horizon": ["+1s"], "Gross": [2.0], "Gross bps": ["+95.24"]}
        ),
        shaded_columns=["Gross"],
        numeric_columns=["Gross bps"],
        format_fn=lambda value: f"{value:+.2f}",
    )


def _alpha(style: str) -> float:
    return float(style.split(",")[-1].rstrip(") "))


def test_a_shaded_cell_deepens_with_its_distance_from_zero():
    faint, full = shade(1.0, 10.0), shade(10.0, 10.0)

    assert "rgba(22, 163, 74" in faint
    assert "rgba(22, 163, 74" in full
    assert _alpha(faint) < _alpha(full)


def test_a_negative_cell_is_shaded_the_losing_color():
    assert "rgba(220, 38, 38" in shade(-5.0, 10.0)


def test_nothing_is_shaded_without_a_scale_or_a_value():
    assert shade(1.0, 0.0) == ""
    assert shade(float("nan"), 10.0) == ""


def test_the_table_renders_its_rows_and_shades_its_numbers(tables):
    at = AppTest.from_function(table_script).run()

    assert not at.exception
    table = tables(at)[0]
    assert table["columns"] == ["Side", "Edge"]
    assert table["rows"] == [["BUY", "+2.00"], ["SELL", "-1.00"]]
    # The winning row's number is tinted green, the losing one's red.
    assert "rgba(22, 163, 74" in table["styles"][0][1]
    assert "rgba(220, 38, 38" in table["styles"][1][1]


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
    """Untitled UI's table: one hairline between rows, no vertical rules
    and no frame around the whole thing."""
    at = AppTest.from_function(table_script).run()

    body = at.get("html")[-1].body
    assert "border-top: 1px solid #EAECF0" in body
    assert "border-left" not in body
    assert "border-right" not in body


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
