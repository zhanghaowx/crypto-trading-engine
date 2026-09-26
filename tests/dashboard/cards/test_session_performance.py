import sqlite3

from streamlit.testing.v1 import AppTest


def _script():
    from jolteon.dashboard.cards import session_performance

    session_performance.render()


def _recording(tmp_path, *, fills=(), mids=(), name="recording.sqlite") -> str:
    """A recording holding `fills` - each `(timestamp, side, price, qty,
    fee)` - and `mids` - each `(timestamp, bid, ask)`."""
    db_path = str(tmp_path / name)
    conn = sqlite3.connect(db_path)
    try:
        conn.execute(
            "CREATE TABLE decorated_order_fill "
            "(transaction_timestamp REAL, side TEXT, fill_price REAL, "
            "fill_qty REAL, fee REAL, symbol TEXT)"
        )
        conn.executemany(
            "INSERT INTO decorated_order_fill VALUES (?, ?, ?, ?, ?, "
            "'BTC-USD')",
            fills,
        )
        conn.execute(
            "CREATE TABLE bbo_feed "
            "(timestamp REAL, symbol TEXT, bid_price REAL, ask_price REAL)"
        )
        conn.executemany(
            "INSERT INTO bbo_feed VALUES (?, 'BTC-USD', ?, ?)", mids
        )
        conn.commit()
    finally:
        conn.close()
    return db_path


def test_shows_warning_when_db_missing(missing_db_path):
    at = AppTest.from_function(_script)
    at.session_state["db_path"] = missing_db_path
    at.run()

    assert not at.exception
    assert at.warning
    assert not at.info


def test_shows_empty_state_when_no_mid_prices_recorded(empty_db_path):
    at = AppTest.from_function(_script)
    at.session_state["db_path"] = empty_db_path
    at.run()

    assert not at.exception
    assert not at.warning
    assert [i.value for i in at.info] == [
        "No fair prices recorded yet to chart marked PnL against."
    ]


def test_renders_a_chart_of_marked_pnl_over_time(tmp_path):
    db_path = _recording(
        tmp_path,
        fills=[(1700000000, "BUY", 100.0, 1.0, 0.0)],
        mids=[
            (1700000000 - 5, 95.0, 95.0),
            (1700000000 + 5, 105.0, 105.0),
        ],
    )

    at = AppTest.from_function(_script)
    at.session_state["db_path"] = db_path
    at.run()

    assert not at.exception
    charts = at.get("vega_lite_chart")
    assert len(charts) == 1
    assert '"value": "green"' in charts[0].proto.spec
    assert any("Marked PnL" in caption.value for caption in at.caption)


def test_the_range_control_narrows_the_series_shown(tmp_path):
    now = 1700000000.0
    db_path = _recording(
        tmp_path,
        fills=[(now - 3600, "BUY", 100.0, 1.0, 0.0)],
        mids=[
            (now - 3600, 100.0, 100.0),
            (now - 1200, 110.0, 110.0),
            (now, 120.0, 120.0),
        ],
    )

    at = AppTest.from_function(_script)
    at.session_state["db_path"] = db_path
    at.run()

    assert not at.exception
    at.segmented_control(key="session-performance-range").set_value(
        "15m"
    ).run()

    assert not at.exception
    charts = at.get("vega_lite_chart")
    assert len(charts) == 1
