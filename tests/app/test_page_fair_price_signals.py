import sqlite3

import pytest
from streamlit.testing.v1 import AppTest


def _script():
    from jolteon.app.app_pages import fair_price_signals

    fair_price_signals.render()


def _create_adjustments_table(conn: sqlite3.Connection) -> None:
    conn.execute(
        "CREATE TABLE fair_price_adjustment "
        "(timestamp REAL, symbol TEXT, base_fair_price REAL, "
        '"adjustments.momentum" REAL, total_adjustment REAL, '
        "clamped INTEGER)"
    )


def _create_fair_price_table(conn: sqlite3.Connection) -> None:
    conn.execute(
        "CREATE TABLE fair_price "
        "(timestamp REAL, symbol TEXT, model TEXT, bid_fair_price REAL, "
        "ask_fair_price REAL)"
    )


def test_shows_warning_when_db_missing(missing_db_path):
    at = AppTest.from_function(_script)
    at.session_state["db_path"] = missing_db_path
    at.run()

    assert not at.exception
    assert at.warning
    assert not at.info


def test_shows_info_when_no_adjustments_recorded(empty_db_path):
    at = AppTest.from_function(_script)
    at.session_state["db_path"] = empty_db_path
    at.run()

    assert not at.exception
    assert not at.warning
    assert [i.value for i in at.info] == [
        "No fair price adjustments recorded yet."
    ]


def test_shows_info_when_waiting_for_fair_price_data(tmp_path):
    db_path = str(tmp_path / "adjustments_only.sqlite")
    conn = sqlite3.connect(db_path)
    _create_adjustments_table(conn)
    conn.execute(
        "INSERT INTO fair_price_adjustment VALUES "
        "(1700000000, 'BTC-USD', 100.0, 0.5, 0.5, 0)"
    )
    conn.commit()
    conn.close()

    at = AppTest.from_function(_script)
    at.session_state["db_path"] = db_path
    at.run()

    assert not at.exception
    assert [i.value for i in at.info] == [
        "Waiting for fair price data to evaluate against."
    ]


def test_renders_slope_and_correlation(tmp_path):
    db_path = str(tmp_path / "evaluation.sqlite")
    conn = sqlite3.connect(db_path)
    _create_adjustments_table(conn)
    conn.executemany(
        "INSERT INTO fair_price_adjustment VALUES (?, ?, ?, ?, ?, ?)",
        [
            (1000.0, "BTC-USD", 100.0, 1.0, 1.0, 0),
            (1001.0, "BTC-USD", 100.0, -1.0, -1.0, 0),
        ],
    )
    _create_fair_price_table(conn)
    conn.executemany(
        "INSERT INTO fair_price VALUES (?, ?, ?, ?, ?)",
        [
            (1001.0, "BTC-USD", "MidPriceFairPriceModel", 101.0, 101.0),
            (1002.0, "BTC-USD", "MidPriceFairPriceModel", 99.0, 99.0),
        ],
    )
    conn.commit()
    conn.close()

    at = AppTest.from_function(_script)
    at.session_state["db_path"] = db_path
    at.run()

    assert not at.exception
    markdown_values = [m.value for m in at.markdown]
    assert "**Calibration (slope)**" in markdown_values
    assert "**Reliability (correlation)**" in markdown_values

    slope = at.dataframe[0].value.set_index("Adjustment")
    correlation = at.dataframe[1].value.set_index("Adjustment")

    assert slope.loc["momentum", "+1s"] == pytest.approx(1.0)
    assert correlation.loc["momentum", "+1s"] == pytest.approx(1.0)
    assert slope.loc["Total", "+1s"] == pytest.approx(1.0)
