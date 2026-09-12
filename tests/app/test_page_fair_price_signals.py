import sqlite3

import pandas as pd
import pytest
from streamlit.testing.v1 import AppTest

from jolteon.app.app_pages.fair_price_signals import _MIN_SAMPLES


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


def _seed_evaluable_session(db_path: str, rows: int) -> None:
    """`rows` alternating +/-1 momentum readings, each followed one second
    later by a mid that moved exactly as far - a perfectly calibrated
    signal, so slope and correlation both come out at 1.0."""
    conn = sqlite3.connect(db_path)
    _create_adjustments_table(conn)
    _create_fair_price_table(conn)

    adjustments = []
    mids = []
    for i in range(rows):
        timestamp = 1000.0 + i
        signal = 1.0 if i % 2 == 0 else -1.0
        adjustments.append((timestamp, "BTC-USD", 100.0, signal, signal, 0))
        mids.append(
            (
                timestamp + 1,
                "BTC-USD",
                "MidPriceFairPriceModel",
                100.0 + signal,
                100.0 + signal,
            )
        )

    conn.executemany(
        "INSERT INTO fair_price_adjustment VALUES (?, ?, ?, ?, ?, ?)",
        adjustments,
    )
    conn.executemany("INSERT INTO fair_price VALUES (?, ?, ?, ?, ?)", mids)
    conn.commit()
    conn.close()


def test_renders_slope_and_correlation(tmp_path):
    db_path = str(tmp_path / "evaluation.sqlite")
    _seed_evaluable_session(db_path, rows=_MIN_SAMPLES + 5)

    at = AppTest.from_function(_script)
    at.session_state["db_path"] = db_path
    at.run()

    assert not at.exception
    markdown_values = [m.value for m in at.markdown]
    assert "**Calibration (\u03b2)**" in markdown_values
    assert "**Reliability (\u03c1)**" in markdown_values

    slope = at.dataframe[0].value.set_index("Adjustment")
    correlation = at.dataframe[1].value.set_index("Adjustment")

    assert slope.loc["Momentum", "+1s"] == pytest.approx(1.0)
    assert correlation.loc["Momentum", "+1s"] == pytest.approx(1.0)
    assert slope.loc["Total", "+1s"] == pytest.approx(1.0)


def test_shows_collecting_info_when_every_horizon_is_undersampled(tmp_path):
    db_path = str(tmp_path / "undersampled.sqlite")
    _seed_evaluable_session(db_path, rows=_MIN_SAMPLES - 1)

    at = AppTest.from_function(_script)
    at.session_state["db_path"] = db_path
    at.run()

    assert not at.exception
    assert not at.dataframe
    assert [i.value for i in at.info] == [
        "Collecting data - no horizon has enough samples to evaluate "
        "against yet."
    ]


def test_blanks_only_the_undersampled_horizons(tmp_path):
    """A 30s horizon never fills in on a short session, so it must show the
    placeholder while the 1s horizon beside it still shows its figure."""
    db_path = str(tmp_path / "partial.sqlite")
    _seed_evaluable_session(db_path, rows=_MIN_SAMPLES + 5)

    at = AppTest.from_function(_script)
    at.session_state["db_path"] = db_path
    at.run()

    assert not at.exception
    slope = at.dataframe[0].value.set_index("Adjustment")
    assert pd.notna(slope.loc["Momentum", "+1s"])
    assert pd.isna(slope.loc["Momentum", "+30s"])
