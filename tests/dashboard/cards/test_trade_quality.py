import sqlite3

from streamlit.testing.v1 import AppTest

MODEL = "MidPriceFairPriceModel"

# Fills are spaced far enough apart that one fill's observations can never
# be joined to the fill before or after it, whatever the horizon.
_FILL_SPACING = 100.0


def _script():
    from jolteon.dashboard.cards import trade_quality

    trade_quality.render()


def test_says_there_is_nothing_to_judge_before_the_first_fill(empty_db_path):
    at = AppTest.from_function(_script)
    at.session_state["db_path"] = empty_db_path
    at.run()

    assert not at.exception
    assert [i.value for i in at.info] == ["No fills yet."]


def test_warns_when_the_recording_is_not_there(missing_db_path):
    at = AppTest.from_function(_script)
    at.session_state["db_path"] = missing_db_path
    at.run()

    assert not at.exception
    assert at.warning


def test_a_fill_with_no_fair_prices_recorded_yields_no_tables(tmp_path):
    """A fill on its own says nothing about execution quality: every
    table here averages a fill against the fair price beside it, and
    there is none recorded to average against."""
    db_path = str(tmp_path / "no-fair-prices.sqlite")
    conn = sqlite3.connect(db_path)
    try:
        conn.execute(
            "CREATE TABLE decorated_order_fill "
            "(timestamp REAL, side TEXT, fill_price REAL, fill_qty REAL, "
            "fee REAL, symbol TEXT, fair_price_model TEXT)"
        )
        conn.execute(
            "INSERT INTO decorated_order_fill VALUES "
            "(1700000000, 'BUY', 99.5, 1.0, 0.1, 'BTC-USD', ?)",
            (MODEL,),
        )
        conn.commit()
    finally:
        conn.close()

    at = AppTest.from_function(_script)
    at.session_state["db_path"] = db_path
    at.run()

    assert not at.exception
    assert not at.info
    assert [m.value for m in at.markdown] == []


def _markout_recording(db_path, fills):
    """A recording of `fills` and the fair-price series they join to.

    Each fill is (side, fill_price, fee, inventory_before, inventory_after,
    fair_at_fill, fair_at_100ms): one observation at the fill itself and
    one a hundred milliseconds later, so only the shortest horizon
    resolves.
    """
    conn = sqlite3.connect(db_path)
    try:
        conn.execute(
            "CREATE TABLE decorated_order_fill "
            "(timestamp REAL, transaction_timestamp REAL, side TEXT, "
            "fill_price REAL, fill_qty REAL, fee REAL, symbol TEXT, "
            "exchange_execution_id TEXT PRIMARY KEY, "
            "inventory_before REAL, inventory_after REAL, "
            "fair_price_model TEXT)"
        )
        conn.execute(
            "CREATE TABLE fair_price "
            "(timestamp REAL, symbol TEXT, model TEXT, "
            "bid_fair_price REAL, ask_fair_price REAL)"
        )
        for index, fill in enumerate(fills):
            (
                side,
                price,
                fee,
                inventory_before,
                inventory_after,
                fair_at_fill,
                fair_at_100ms,
            ) = fill
            timestamp = 1700000000 + index * _FILL_SPACING
            conn.execute(
                "INSERT INTO decorated_order_fill VALUES "
                "(?,?,?,?,?,?,?,?,?,?,?)",
                (
                    timestamp,
                    timestamp,
                    side,
                    price,
                    1.0,
                    fee,
                    "BTC-USD",
                    index + 1,
                    inventory_before,
                    inventory_after,
                    MODEL,
                ),
            )
            conn.executemany(
                "INSERT INTO fair_price VALUES (?, 'BTC-USD', ?, ?, ?)",
                [
                    (timestamp, MODEL, fair_at_fill - 1.0, fair_at_fill + 1.0),
                    (
                        timestamp + 0.1,
                        MODEL,
                        fair_at_100ms - 1.0,
                        fair_at_100ms + 1.0,
                    ),
                ],
            )
        conn.commit()
    finally:
        conn.close()


def test_renders_fill_quality_by_side_and_fair_price_movement(
    tmp_path, tables, table_lookup
):
    db_path = str(tmp_path / "fill_quality.sqlite")
    _markout_recording(
        db_path,
        [
            # BUY favorable then adverse, averaging to a $0 edge and markout.
            ("BUY", 100.0, 0.1, 0.0, 1.0, 101.0, 102.0),
            ("BUY", 100.0, 0.2, 1.0, 2.0, 99.0, 98.0),
            # SELL, favorable on both edge and markout.
            ("SELL", 110.0, 0.05, 2.0, 1.0, 108.0, 105.0),
        ],
    )

    at = AppTest.from_function(_script)
    at.session_state["db_path"] = db_path
    at.run()

    assert not at.exception
    markdown_values = [m.value for m in at.markdown]
    assert "**Fill Quality**" in markdown_values
    assert "**Fair price movement**" in markdown_values

    fill_quality = table_lookup(at, 0, "Side")
    assert fill_quality["BUY"]["Fills"] == "2"
    assert fill_quality["BUY"]["Average edge"] == "+$0.00"
    assert fill_quality["BUY"]["Markout +100ms"] == "+$0.00"
    assert fill_quality["SELL"]["Fills"] == "1"
    assert fill_quality["SELL"]["Average edge"] == "+$2.00"
    assert fill_quality["SELL"]["Markout +100ms"] == "+$5.00"
    # No fill has a 1s/5s/30s fair price backfilled yet.
    assert fill_quality["BUY"]["Markout +1s"] == "–"

    # Fair price movement is side-independent: (102-101) + (98-99) +
    # (105-108) averaged across all three fills = -1. It's the third
    # table on the page - fill quality, then inventory buckets (this
    # schema has inventory_before too), then this one.
    movement = tables(at)[2]
    row = dict(zip(movement["columns"], movement["rows"][0]))
    assert row["+100ms"] == "-$1.00"
    assert row["+1s"] == "–"


def test_renders_inventory_buckets(tmp_path, table_lookup):
    db_path = str(tmp_path / "inventory_buckets.sqlite")
    _markout_recording(
        db_path,
        [
            # Strongly short: one BUY.
            ("BUY", 100.0, 0.1, -0.6, -0.5, 100.0, 103.0),
            # Near neutral: one SELL.
            ("SELL", 100.0, 0.2, 0.0, -1.0, 100.0, 98.0),
        ],
    )

    at = AppTest.from_function(_script)
    at.session_state["db_path"] = db_path
    at.run()

    assert not at.exception
    markdown_values = [m.value for m in at.markdown]
    assert "**Inventory Buckets**" in markdown_values

    # Fill quality (BUY/SELL, one each) is the first table on the page;
    # inventory buckets is the second.
    buckets = table_lookup(at, 1, "Inventory")
    assert "Strongly short" in buckets
    assert "Near neutral" in buckets
    assert "Strongly long" not in buckets

    assert buckets["Strongly short"]["Fills"] == "1"
    assert buckets["Strongly short"]["BUY"] == "1"
    assert buckets["Strongly short"]["SELL"] == "0"
    assert buckets["Strongly short"]["Markout +100ms"] == "+$3.00"
    assert buckets["Near neutral"]["Fills"] == "1"
    assert buckets["Near neutral"]["Markout +100ms"] == "+$2.00"


def test_a_fill_without_the_position_held_before_it_joins_no_bucket(tmp_path):
    """A bucket says how we traded while holding that much, so a fill
    recorded without the position held before it belongs to none of them
    - rather than falling through every bound into the extreme one."""
    from jolteon.dashboard import aggregates

    db_path = str(tmp_path / "unset.sqlite")
    conn = sqlite3.connect(db_path)
    try:
        conn.execute(
            "CREATE TABLE decorated_order_fill "
            "(side TEXT, fill_price REAL, fair_price_at_fill REAL, "
            "fill_qty REAL, fee REAL, inventory_before REAL, "
            "fair_price_100ms REAL, fair_price_1s REAL, "
            "fair_price_5s REAL, fair_price_30s REAL)"
        )
        conn.execute(
            "INSERT INTO decorated_order_fill VALUES "
            "('BUY', 100.0, 100.0, 1.0, 0.1, NULL, NULL, NULL, NULL, NULL)"
        )
        conn.commit()
    finally:
        conn.close()

    assert aggregates.inventory_buckets(db_path).empty
