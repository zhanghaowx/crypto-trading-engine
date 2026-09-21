import sqlite3
from pathlib import Path

import pandas as pd
import pytest

from jolteon.app import aggregates

MODEL = "AdjustedFairPriceModel"

_FILL_COLUMNS = (
    "timestamp REAL, side TEXT, fill_price REAL, fee REAL, fill_qty REAL, "
    "inventory_before REAL, symbol TEXT, fair_price_model TEXT"
)
_FAIR_COLUMNS = (
    "timestamp REAL, symbol TEXT, model TEXT, "
    "bid_fair_price REAL, ask_fair_price REAL"
)

# Fills are spaced far enough apart that one fill's observations can never
# be joined to the fill before or after it, whatever the horizon.
_FILL_SPACING = 100.0


def _fill(
    side, price, fair, fee, qty, inventory, at_1s=None, symbol="BTC-USD"
):
    """One fill and the fair-price observations it should join to: `fair`
    at the moment it happened, and `at_1s` a second later."""
    return (side, price, fair, fee, qty, inventory, symbol, at_1s)


def _observations(timestamp, symbol, fair, at_1s):
    yield (timestamp, symbol, MODEL, fair - 1.0, fair + 1.0)
    if at_1s is not None:
        yield (timestamp + 1.0, symbol, MODEL, at_1s - 1.0, at_1s + 1.0)


def _recording(tmp_path, fills, name="fills.sqlite") -> str:
    db_path = str(Path(tmp_path) / name)
    fill_rows, fair_rows = [], []
    for index, (
        side,
        price,
        fair,
        fee,
        qty,
        inventory,
        symbol,
        at_1s,
    ) in enumerate(fills):
        timestamp = index * _FILL_SPACING
        fill_rows.append(
            (timestamp, side, price, fee, qty, inventory, symbol, MODEL)
        )
        fair_rows.extend(_observations(timestamp, symbol, fair, at_1s))

    conn = sqlite3.connect(db_path)
    try:
        conn.execute(f"CREATE TABLE decorated_order_fill ({_FILL_COLUMNS})")
        conn.executemany(
            "INSERT INTO decorated_order_fill VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            fill_rows,
        )
        conn.execute(f"CREATE TABLE fair_price ({_FAIR_COLUMNS})")
        conn.executemany(
            "INSERT INTO fair_price VALUES (?, ?, ?, ?, ?)", fair_rows
        )
        conn.commit()
    finally:
        conn.close()
    return db_path


def test_fill_quality_splits_buy_from_sell(tmp_path):
    db_path = _recording(
        tmp_path,
        [
            _fill("BUY", 100.0, 101.0, 0.1, 1.0, 0.0, at_1s=103.0),
            _fill("BUY", 100.0, 99.0, 0.2, 1.0, 0.0, at_1s=97.0),
            _fill("SELL", 110.0, 108.0, 0.05, 1.0, 0.0, at_1s=105.0),
        ],
    )

    by_side = aggregates.fill_quality_by_side(db_path)

    assert by_side.loc["BUY", "fill_count"] == 2
    assert by_side.loc["BUY", "avg_edge"] == pytest.approx(0.0)
    assert by_side.loc["BUY", "avg_fee"] == pytest.approx(0.15)
    assert by_side.loc["BUY", "avg_markout_1s"] == pytest.approx(0.0)
    assert by_side.loc["BUY", "avg_net_markout_1s"] == pytest.approx(-0.15)

    assert by_side.loc["SELL", "fill_count"] == 1
    assert by_side.loc["SELL", "avg_edge"] == pytest.approx(2.0)
    assert by_side.loc["SELL", "avg_markout_1s"] == pytest.approx(5.0)
    assert by_side.loc["SELL", "avg_net_markout_1s"] == pytest.approx(4.95)


def test_a_horizon_that_has_not_resolved_is_missing_not_zero(tmp_path):
    """A markout only arrives once its horizon has passed. Counting the
    fills still waiting as zero would drag every average towards it."""
    db_path = _recording(
        tmp_path, [_fill("BUY", 100.0, 100.0, 0.1, 1.0, 0.0, at_1s=None)]
    )

    by_side = aggregates.fill_quality_by_side(db_path)

    assert pd.isna(by_side.loc["BUY", "avg_markout_1s"])


def test_inventory_buckets_are_read_short_through_long(tmp_path):
    db_path = _recording(
        tmp_path,
        [
            _fill("BUY", 100.0, 100.0, 0.1, 1.0, -0.6, at_1s=103.0),
            _fill("SELL", 100.0, 100.0, 0.2, 1.0, 0.0, at_1s=98.0),
            _fill("BUY", 100.0, 100.0, 0.1, 1.0, 0.9, at_1s=100.0),
        ],
    )

    buckets = aggregates.inventory_buckets(db_path)

    assert list(buckets.index) == [
        "Strongly short",
        "Near neutral",
        "Strongly long",
    ]
    assert buckets.loc["Strongly short", "fill_count"] == 1
    assert buckets.loc["Strongly short", "buy_count"] == 1
    assert buckets.loc["Strongly short", "sell_count"] == 0
    assert buckets.loc["Strongly short", "avg_markout_1s"] == pytest.approx(
        3.0
    )
    assert buckets.loc["Strongly short", "net_cash_flow"] == pytest.approx(
        -100.1
    )
    assert buckets.loc["Near neutral", "net_cash_flow"] == pytest.approx(99.8)


def test_a_fill_without_the_position_held_before_it_joins_no_bucket(tmp_path):
    """A bucket says how we traded while holding that much, so a fill
    recorded without that belongs to none of them - rather than falling
    through every bound into the extreme one."""
    db_path = _recording(
        tmp_path, [_fill("BUY", 100.0, 100.0, 0.1, 1.0, None)]
    )

    assert aggregates.inventory_buckets(db_path).empty


def test_position_and_cash_sum_over_every_fill(tmp_path):
    db_path = _recording(
        tmp_path,
        [
            _fill("BUY", 100.0, 100.0, 0.1, 2.0, 0.0),
            _fill("SELL", 110.0, 110.0, 0.2, 1.0, 0.0),
            _fill("BUY", 50.0, 50.0, 0.05, 1.0, 0.0, symbol="ETH-USD"),
        ],
    )

    totals = aggregates.position_and_cash(db_path)

    assert totals.loc["BTC-USD", "position"] == pytest.approx(1.0)
    # -200 paid, +110 received, 0.30 of fees.
    assert totals.loc["BTC-USD", "net_cash"] == pytest.approx(-90.3)
    assert totals.loc["ETH-USD", "position"] == pytest.approx(1.0)
    assert totals.loc["ETH-USD", "net_cash"] == pytest.approx(-50.05)


def test_fees_and_presence_are_asked_of_the_recording(tmp_path):
    db_path = _recording(
        tmp_path,
        [
            _fill("BUY", 100.0, 100.0, 0.1, 1.0, 0.0),
            _fill("SELL", 100.0, 100.0, 0.25, 1.0, 0.0),
        ],
    )

    assert aggregates.any_fills(db_path)
    assert aggregates.total_fees(db_path) == pytest.approx(0.35)


def test_fair_price_movement_is_side_independent(tmp_path):
    db_path = _recording(
        tmp_path,
        [
            _fill("BUY", 100.0, 101.0, 0.1, 1.0, 0.0, at_1s=103.0),
            _fill("SELL", 100.0, 99.0, 0.1, 1.0, 0.0, at_1s=97.0),
        ],
    )

    moved = aggregates.avg_fair_price_movement(db_path)

    # +2 and -2 either side of the fair price it was filled at.
    assert moved["1s"] == pytest.approx(0.0)
    assert pd.isna(moved["30s"])


def test_a_recording_with_no_fills_answers_with_nothing(tmp_path):
    db_path = _recording(tmp_path, [])

    assert not aggregates.any_fills(db_path)
    assert aggregates.total_fees(db_path) == 0.0
    assert aggregates.fill_quality_by_side(db_path).empty
    assert aggregates.inventory_buckets(db_path).empty
    assert aggregates.position_and_cash(db_path).empty
    assert aggregates.avg_fair_price_movement(db_path).isna().all()


def test_a_recording_without_the_columns_answers_with_nothing(tmp_path):
    """An older recording may not have the columns a newer payload
    writes, and a card that cannot be drawn should draw nothing rather
    than take the page down."""
    db_path = str(Path(tmp_path) / "old.sqlite")
    conn = sqlite3.connect(db_path)
    try:
        conn.execute("CREATE TABLE decorated_order_fill (side TEXT)")
        conn.execute("INSERT INTO decorated_order_fill VALUES ('BUY')")
        conn.commit()
    finally:
        conn.close()

    assert aggregates.fill_quality_by_side(db_path).empty
    assert aggregates.inventory_buckets(db_path).empty
    assert aggregates.position_and_cash(db_path).empty
    assert aggregates.total_fees(db_path) == 0.0


def test_a_recording_that_is_not_there_answers_with_nothing(tmp_path):
    missing = str(Path(tmp_path) / "absent.sqlite")

    assert not aggregates.any_fills(missing)
    assert aggregates.fill_quality_by_side(missing).empty
    assert aggregates.total_fees(missing) == 0.0


def test_fill_quality_derives_prices_from_recorded_fair_price_series(tmp_path):
    db_path = str(Path(tmp_path) / "derived.sqlite")
    conn = sqlite3.connect(db_path)
    try:
        conn.execute(
            "CREATE TABLE decorated_order_fill ("
            "timestamp REAL, side TEXT, fill_price REAL, "
            "fee REAL, fill_qty REAL, inventory_before REAL, symbol TEXT, "
            "fair_price_model TEXT)"
        )
        conn.execute(
            "INSERT INTO decorated_order_fill VALUES "
            "(10.0, 'BUY', 100.0, 0.1, 1.0, 0.0, 'BTC/USD', "
            "'AdjustedFairPriceModel')"
        )
        conn.execute(
            "CREATE TABLE fair_price ("
            "timestamp REAL, symbol TEXT, model TEXT, "
            "bid_fair_price REAL, ask_fair_price REAL)"
        )
        conn.executemany(
            "INSERT INTO fair_price VALUES (?, 'BTC/USD', "
            "'AdjustedFairPriceModel', ?, ?)",
            [
                (9.9, 100.0, 102.0),  # mid 101 at fill
                (11.01, 102.0, 104.0),  # mid 103 at +1s
            ],
        )
        conn.commit()
    finally:
        conn.close()

    by_side = aggregates.fill_quality_by_side(db_path)

    assert by_side.loc["BUY", "fill_count"] == 1
    assert by_side.loc["BUY", "avg_edge"] == pytest.approx(1.0)
    assert by_side.loc["BUY", "avg_markout_1s"] == pytest.approx(3.0)
    assert by_side.loc["BUY", "avg_net_markout_1s"] == pytest.approx(2.9)


def test_derived_markout_does_not_bridge_a_long_fair_price_gap(tmp_path):
    db_path = str(Path(tmp_path) / "gap.sqlite")
    conn = sqlite3.connect(db_path)
    try:
        conn.execute(
            "CREATE TABLE decorated_order_fill ("
            "timestamp REAL, side TEXT, fill_price REAL, "
            "fee REAL, fill_qty REAL, symbol TEXT, fair_price_model TEXT)"
        )
        conn.execute(
            "INSERT INTO decorated_order_fill VALUES "
            "(10.0, 'BUY', 100.0, 0.0, 1.0, 'BTC/USD', "
            "'AdjustedFairPriceModel')"
        )
        conn.execute(
            "CREATE TABLE fair_price ("
            "timestamp REAL, symbol TEXT, model TEXT, "
            "bid_fair_price REAL, ask_fair_price REAL)"
        )
        conn.executemany(
            "INSERT INTO fair_price VALUES (?, 'BTC/USD', "
            "'AdjustedFairPriceModel', ?, ?)",
            [
                (9.9, 100.0, 102.0),
                (15.0, 109.0, 111.0),
            ],
        )
        conn.commit()
    finally:
        conn.close()

    by_side = aggregates.fill_quality_by_side(db_path)

    assert by_side.loc["BUY", "avg_edge"] == pytest.approx(1.0)
    assert pd.isna(by_side.loc["BUY", "avg_markout_1s"])


def _run_recording(tmp_path, fills) -> str:
    """`_recording`, with each fill naming the run that made it."""
    db_path = str(Path(tmp_path) / "runs.sqlite")
    fill_rows, fair_rows = [], []
    for index, (run_id, side, price, fair, fee, qty, at_1s) in enumerate(
        fills
    ):
        timestamp = index * _FILL_SPACING
        fill_rows.append(
            (timestamp, side, price, fee, qty, 0.0, "BTC-USD", MODEL, run_id)
        )
        fair_rows.extend(_observations(timestamp, "BTC-USD", fair, at_1s))

    conn = sqlite3.connect(db_path)
    try:
        conn.execute(
            f"CREATE TABLE decorated_order_fill ({_FILL_COLUMNS}, run_id TEXT)"
        )
        conn.executemany(
            "INSERT INTO decorated_order_fill "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            fill_rows,
        )
        conn.execute(f"CREATE TABLE fair_price ({_FAIR_COLUMNS})")
        conn.executemany(
            "INSERT INTO fair_price VALUES (?, ?, ?, ?, ?)", fair_rows
        )
        conn.commit()
    finally:
        conn.close()
    return db_path


def test_run_scoped_aggregates_exclude_previous_engine_runs(tmp_path):
    db_path = _run_recording(
        tmp_path,
        [
            ("run-a", "BUY", 100.0, 101.0, 5.0, 2.0, 103.0),
            ("run-b", "SELL", 110.0, 108.0, 0.25, 1.0, 105.0),
        ],
    )

    totals = aggregates.position_and_cash(db_path, "run-b")
    quality = aggregates.fill_quality_by_side(db_path, "run-b")

    assert totals.loc["BTC-USD", "position"] == pytest.approx(-1.0)
    assert aggregates.total_fees(db_path, "run-b") == pytest.approx(0.25)
    assert quality["fill_count"].sum() == 1
    assert quality.index.tolist() == ["SELL"]
    assert aggregates.any_fills(db_path, "run-b")
    assert not aggregates.any_fills(db_path, "missing-run")


def test_run_scoped_markouts_measure_only_the_named_run(tmp_path):
    db_path = _run_recording(
        tmp_path,
        [
            ("run-a", "BUY", 100.0, 101.0, 0.0, 1.0, 120.0),
            ("run-b", "BUY", 100.0, 101.0, 0.0, 1.0, 103.0),
        ],
    )

    quality = aggregates.fill_quality_by_side(db_path, "run-b")
    movement = aggregates.avg_fair_price_movement(db_path, "run-b")
    buckets = aggregates.inventory_buckets(db_path, run_id="run-b")

    # run-a's fill moved 19 in its favour; averaging both would show it.
    assert quality.loc["BUY", "avg_markout_1s"] == pytest.approx(3.0)
    assert movement["1s"] == pytest.approx(2.0)
    assert buckets["fill_count"].sum() == 1
