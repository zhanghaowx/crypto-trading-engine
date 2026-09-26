import sqlite3

import pandas as pd
import pytest
from streamlit.testing.v1 import AppTest

from jolteon.dashboard.cards.fair_price_signals import (
    _COLLECTING,
    _MIN_SAMPLES,
    _verdict,
)
from tests.dashboard.conftest import scoped_run


def _script():
    """The card's own body: the verdict, and nothing else."""
    from jolteon.dashboard.cards import fair_price_signals

    fair_price_signals.render()


def _details_script():
    """What the card's details modal shows: the numbers the verdict is
    drawn from, which the card itself no longer carries."""
    from jolteon.dashboard.cards import fair_price_signals

    fair_price_signals.render_details()


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


def test_renders_slope_and_correlation(tmp_path, table_lookup):
    db_path = str(tmp_path / "evaluation.sqlite")
    _seed_evaluable_session(db_path, rows=_MIN_SAMPLES + 5)

    at = AppTest.from_function(_script)
    at.session_state["db_path"] = db_path
    at.run()

    assert not at.exception
    markdown_values = [m.value for m in at.markdown]
    assert "Momentum" in markdown_values
    assert ":green-badge[Worth a weight]" in markdown_values

    at = AppTest.from_function(_details_script)
    at.session_state["db_path"] = db_path
    at.run()

    assert not at.exception
    markdown_values = [m.value for m in at.markdown]
    assert "**Calibration (\u03b2)**" in markdown_values
    assert "**Reliability (\u03c1)**" in markdown_values

    correlation = table_lookup(at, 0, "Adjustment")
    slope = table_lookup(at, 1, "Adjustment")

    assert slope["Momentum"]["+1s"] == "+1.00"
    assert correlation["Momentum"]["+1s"] == "+1.00"
    assert slope["Total"]["+1s"] == "+1.00"


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


def test_blanks_only_the_undersampled_horizons(tmp_path, table_lookup):
    """A 30s horizon never fills in on a short session, so it must show the
    placeholder while the 1s horizon beside it still shows its figure."""
    db_path = str(tmp_path / "partial.sqlite")
    _seed_evaluable_session(db_path, rows=_MIN_SAMPLES + 5)

    at = AppTest.from_function(_details_script)
    at.session_state["db_path"] = db_path
    at.run()

    assert not at.exception
    slope = table_lookup(at, 1, "Adjustment")
    assert slope["Momentum"]["+1s"] != _COLLECTING
    assert slope["Momentum"]["+30s"] == _COLLECTING


def _evaluated(correlation: float, n: int = _MIN_SAMPLES + 1) -> pd.DataFrame:
    return pd.DataFrame(
        {
            "horizon": ["1s"],
            "n": [n],
            "slope": [1.0],
            "correlation": [correlation],
        }
    )


@pytest.mark.parametrize(
    ("correlation", "expected"),
    [
        (0.9, "Worth a weight"),
        (-0.9, "Points the wrong way"),
        (0.10, "Too weak to size from"),
        (-0.10, "Too weak to size from"),
        (0.01, "No usable signal yet"),
        (float("nan"), _COLLECTING),
    ],
)
def test_verdict_reads_the_strength_before_the_direction(
    correlation, expected
):
    assert _verdict(_evaluated(correlation)) == expected


def test_verdict_waits_while_a_horizon_is_undersampled():
    assert _verdict(_evaluated(0.9, n=_MIN_SAMPLES - 1)) == _COLLECTING


def _verdict_rows_script():
    """One adjustment at each verdict, drawn as the card draws them."""
    import pandas as pd

    from jolteon.dashboard.cards.fair_price_signals import (
        _MIN_SAMPLES,
        _render_verdict,
    )

    _render_verdict(
        pd.DataFrame(
            {
                "adjustment": ["Momentum", "Flow", "Skew", "Drift", "Total"],
                "horizon": ["1s"] * 5,
                "n": [_MIN_SAMPLES + 1] * 4 + [_MIN_SAMPLES - 1],
                "slope": [1.0] * 5,
                "correlation": [0.9, -0.9, 0.10, 0.01, 0.9],
            }
        )
    )


def test_each_verdict_is_a_badge_beside_its_adjustment(tables):
    """A signal that is not yet usable is a normal state, badged
    neutral; only one pointing the wrong way is a finding to act on.
    None of them is a tinted table row."""
    at = AppTest.from_function(_verdict_rows_script)
    at.run()

    assert not at.exception
    assert not tables(at)
    assert [m.value for m in at.markdown] == [
        "**Verdict**",
        "Momentum",
        ":green-badge[Worth a weight]",
        "Flow",
        ":orange-badge[Points the wrong way]",
        "Skew",
        ":gray-badge[Too weak to size from]",
        "Drift",
        ":gray-badge[No usable signal yet]",
        "Total",
        f":gray-badge[{_COLLECTING}]",
    ]


def test_the_card_itself_carries_only_the_verdict(tmp_path, tables):
    """The numbers moved into the card's details modal, so the card is
    the verdict alone rather than a verdict over a fold."""
    db_path = str(tmp_path / "verdict_only.sqlite")
    _seed_evaluable_session(db_path, rows=_MIN_SAMPLES + 5)

    at = AppTest.from_function(_script)
    at.session_state["db_path"] = db_path
    at.run()

    assert not at.exception
    assert [m.value for m in at.markdown] == [
        "**Verdict**",
        "Momentum",
        ":green-badge[Worth a weight]",
        "Total",
        ":green-badge[Worth a weight]",
    ]
    assert not tables(at)
    assert not at.expander


def test_the_modal_says_why_when_there_is_nothing_to_show(
    empty_db_path, tables
):
    """Opening the details before the engine has recorded anything shows
    the same explanation the card would, rather than an empty modal."""
    at = AppTest.from_function(_details_script)
    at.session_state["db_path"] = empty_db_path
    at.run()

    assert not at.exception
    assert not tables(at)
    assert at.info[0].value == "No fair price adjustments recorded yet."


def test_signal_evaluation_uses_only_the_current_run(tmp_path):
    db_path = str(tmp_path / "two-runs.sqlite")
    conn = sqlite3.connect(db_path)
    try:
        conn.execute(
            "CREATE TABLE fair_price_adjustment "
            "(timestamp REAL, symbol TEXT, base_fair_price REAL, "
            '"adjustments.momentum" REAL, total_adjustment REAL, '
            "clamped INTEGER, run_id TEXT)"
        )
        conn.execute(
            "CREATE TABLE fair_price "
            "(timestamp REAL, symbol TEXT, model TEXT, bid_fair_price REAL, "
            "ask_fair_price REAL, run_id TEXT)"
        )
        adjustments = []
        mids = []
        for i in range(_MIN_SAMPLES + 5):
            timestamp = 1000.0 + i
            signal = 1.0 if i % 2 == 0 else -1.0
            adjustments.append(
                (
                    timestamp,
                    "BTC-USD",
                    100.0,
                    signal,
                    signal,
                    0,
                    "run-a",
                )
            )
            mids.append(
                (
                    timestamp + 1,
                    "BTC-USD",
                    "MidPriceFairPriceModel",
                    100.0 + signal,
                    100.0 + signal,
                    "run-a",
                )
            )
        for i in range(2):
            timestamp = 2000.0 + i
            adjustments.append(
                (timestamp, "BTC-USD", 100.0, 1.0, 1.0, 0, "run-b")
            )
            mids.append(
                (
                    timestamp + 1,
                    "BTC-USD",
                    "MidPriceFairPriceModel",
                    101.0,
                    101.0,
                    "run-b",
                )
            )
        conn.executemany(
            "INSERT INTO fair_price_adjustment VALUES (?,?,?,?,?,?,?)",
            adjustments,
        )
        conn.executemany(
            "INSERT INTO fair_price VALUES (?,?,?,?,?,?)",
            mids,
        )
        conn.commit()
    finally:
        conn.close()

    at = AppTest.from_function(_script)
    at.session_state["db_path"] = db_path
    at.session_state["engine_run"] = scoped_run("run-b")
    at.run()

    assert not at.exception
    assert [i.value for i in at.info] == [
        "Collecting data - no horizon has enough samples to evaluate "
        "against yet."
    ]
