import sqlite3
import time
from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

from jolteon.engine.core.storage import paths

_PAGE_PATH = str(
    Path(__file__).resolve().parents[2]
    / "jolteon"
    / "app"
    / "app_pages"
    / "post_trade.py"
)

STOPPED = "20260920T100000Z-def456"
INTERRUPTED = "20260920T110000Z-c0ffee11"
RUNNING = "20260920T120000Z-abc123"
MODEL = "AdjustedFairPriceModel"
SYMBOL = "BTC/USD"


def _page(db_path: str, root: str) -> AppTest:
    at = AppTest.from_file(_PAGE_PATH)
    at.session_state["db_path"] = db_path
    at.session_state["root"] = root
    return at


def _recording(path: str, runs, fills, heartbeat=None) -> None:
    """A recording holding `runs` - each `(run_id, started_at, ended_at)` -
    and `fills`, each `(run_id, side, price, qty)`."""
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    try:
        conn.execute(
            "CREATE TABLE engine_run "
            "(run_id TEXT PRIMARY KEY, exchange TEXT, symbol TEXT, "
            "started_at REAL, ended_at REAL)"
        )
        conn.executemany(
            "INSERT INTO engine_run VALUES (?, 'Kraken', ?, ?, ?)",
            [
                (run_id, SYMBOL, started, ended)
                for run_id, started, ended in runs
            ],
        )
        conn.execute(
            "CREATE TABLE decorated_order_fill "
            "(timestamp REAL, run_id TEXT, side TEXT, fill_price REAL, "
            "fee REAL, fill_qty REAL, inventory_before REAL, symbol TEXT, "
            "fair_price_model TEXT)"
        )
        conn.executemany(
            "INSERT INTO decorated_order_fill VALUES "
            "(?, ?, ?, ?, 0.0, ?, 0.0, ?, ?)",
            [
                (index * 100.0, run_id, side, price, qty, SYMBOL, MODEL)
                for index, (run_id, side, price, qty) in enumerate(fills)
            ],
        )
        conn.execute(
            "CREATE TABLE fair_price "
            "(timestamp REAL, symbol TEXT, model TEXT, "
            "bid_fair_price REAL, ask_fair_price REAL)"
        )
        conn.execute(
            "CREATE TABLE bbo_feed "
            "(timestamp REAL, run_id TEXT, symbol TEXT, bid_price REAL, "
            "ask_price REAL)"
        )
        conn.execute(
            "CREATE TABLE heartbeat "
            "(timestamp REAL, sender TEXT, level INTEGER, message TEXT)"
        )
        if heartbeat is not None:
            conn.execute(
                "INSERT INTO heartbeat VALUES (?, 'MarketMaking', 1, 'ok')",
                (heartbeat,),
            )
        conn.commit()
    finally:
        conn.close()


@pytest.fixture
def three_runs(tmp_path) -> str:
    """Every state a run can be read back in: one stopped cleanly, one the
    engine died in, and one it is still heartbeating through."""
    path = paths.recording(str(tmp_path / "engines"), SYMBOL)
    now = time.time()
    _recording(
        path,
        runs=[
            (STOPPED, 1758000000.0, 1758000600.0),
            # No recorded end, but a later run proves the engine is gone.
            (INTERRUPTED, 1758003600.0, None),
            (RUNNING, now, None),
        ],
        fills=[
            (STOPPED, "BUY", 60.0, 2.0),
            (STOPPED, "SELL", 65.0, 2.0),
            (INTERRUPTED, "BUY", 70.0, 1.0),
            (RUNNING, "BUY", 100.0, 1.0),
        ],
        heartbeat=now,
    )
    return path


@pytest.fixture
def only_a_running_run(tmp_path) -> str:
    """An engine on its first run, still going."""
    path = paths.recording(str(tmp_path / "engines"), SYMBOL)
    now = time.time()
    _recording(
        path,
        runs=[(RUNNING, now, None)],
        fills=[(RUNNING, "BUY", 100.0, 1.0)],
        heartbeat=now,
    )
    return path


def test_says_so_when_nothing_has_been_recorded(missing_db_path, tmp_path):
    at = _page(missing_db_path, str(tmp_path)).run()

    assert not at.exception
    assert [i.value for i in at.info] == [
        "No engine runs have been recorded yet."
    ]
    assert not at.selectbox
    assert not at.expander


def test_the_run_still_going_is_not_offered(three_runs, tmp_path):
    """This page draws once and does not refresh, so a run whose figures
    are still moving would be read here as though it were final. Watching
    that one is the Live page's job."""
    at = _page(three_runs, str(tmp_path / "engines")).run()

    assert not at.exception
    picker = at.selectbox[0]
    assert not any("abc123" in option for option in picker.options)
    # Both ways a run can be over are offered, newest first, worded the
    # way the Live page words them.
    assert picker.options == [
        "2025-09-16 06:20:00 UTC · c0ffee11 · Interrupted",
        "2025-09-16 05:20:00 UTC · def456 · Stopped",
    ]


def test_opens_on_the_newest_run_that_has_ended(three_runs, tmp_path):
    at = _page(three_runs, str(tmp_path / "engines")).run()

    assert not at.exception
    assert at.selectbox[0].value == INTERRUPTED
    assert [e.label.split(": ", 1)[-1] for e in at.expander] == [
        "Session Economics"
    ]
    # The interrupted run's one fill, not the running run's.
    assert {m.label: m.value for m in at.metric}["Notional"] == "$70.00"


def test_picking_another_run_measures_that_one_instead(three_runs, tmp_path):
    at = _page(three_runs, str(tmp_path / "engines")).run()

    at.selectbox[0].set_value(STOPPED).run()

    assert not at.exception
    metrics = {m.label: m.value for m in at.metric}
    # Two units bought at 60 and sold back at 65.
    assert metrics["Notional"] == "$250.00"
    assert metrics["Fills"] == "2"


def test_says_so_when_the_only_run_is_still_going(
    only_a_running_run, tmp_path
):
    at = _page(only_a_running_run, str(tmp_path / "engines")).run()

    assert not at.exception
    assert [i.value for i in at.info] == [
        "The engine's only run so far is still going. Watch it on the "
        "Live page; this page reads runs that have ended."
    ]
    assert not at.selectbox
    assert not at.expander
