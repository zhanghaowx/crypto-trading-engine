import sqlite3

import pandas as pd

from jolteon.dashboard.data.fair_prices import read_fair_prices_for_fills


def test_reads_only_fair_prices_needed_for_visible_fill_markouts(tmp_path):
    db_path = str(tmp_path / "prices.sqlite")
    conn = sqlite3.connect(db_path)
    try:
        conn.execute(
            "CREATE TABLE fair_price ("
            "timestamp REAL, symbol TEXT, model TEXT, "
            "bid_fair_price REAL, ask_fair_price REAL)"
        )
        conn.executemany(
            "INSERT INTO fair_price VALUES (?, ?, ?, ?, ?)",
            [
                (1.0, "BTC/USD", "AdjustedFairPriceModel", 99.0, 101.0),
                (9.5, "BTC/USD", "AdjustedFairPriceModel", 100.0, 102.0),
                (10.0, "BTC/USD", "MidPriceFairPriceModel", 500.0, 502.0),
                (11.0, "ETH/USD", "AdjustedFairPriceModel", 50.0, 52.0),
                (40.5, "BTC/USD", "AdjustedFairPriceModel", 103.0, 105.0),
                (50.0, "BTC/USD", "AdjustedFairPriceModel", 104.0, 106.0),
            ],
        )
        conn.commit()
    finally:
        conn.close()

    fills = pd.DataFrame(
        [
            {
                "timestamp": 10.0,
                "symbol": "BTC/USD",
                "fair_price_model": "AdjustedFairPriceModel",
            }
        ]
    )
    rows = read_fair_prices_for_fills(
        db_path,
        fills,
        max_horizon_seconds=30.0,
        max_lag_seconds=1.0,
    )

    assert list(rows["timestamp"]) == [9.5, 40.5]
    assert set(rows["model"]) == {"AdjustedFairPriceModel"}
    assert set(rows["symbol"]) == {"BTC/USD"}


def test_fair_prices_are_not_read_without_a_fill_to_read_them_for(tmp_path):
    db_path = str(tmp_path / "fair.sqlite")
    conn = sqlite3.connect(db_path)
    try:
        conn.execute(
            "CREATE TABLE fair_price (timestamp REAL, symbol TEXT, "
            "model TEXT, bid_fair_price REAL, ask_fair_price REAL)"
        )
        conn.commit()
    finally:
        conn.close()

    unusable = pd.DataFrame(
        [{"timestamp": None, "symbol": None, "fair_price_model": None}]
    )

    assert read_fair_prices_for_fills(
        db_path, unusable, max_horizon_seconds=30.0, max_lag_seconds=1.0
    ).empty


def test_fair_prices_from_a_recording_without_the_table_are_nothing(tmp_path):
    """A recording made before fair prices were recorded should leave the
    markout columns empty rather than take the page down."""
    db_path = str(tmp_path / "no_fair_price.sqlite")
    conn = sqlite3.connect(db_path)
    try:
        conn.execute("CREATE TABLE other (x REAL)")
        conn.commit()
    finally:
        conn.close()

    fills = pd.DataFrame(
        [
            {
                "timestamp": 10.0,
                "symbol": "BTC/USD",
                "fair_price_model": "MidPriceFairPriceModel",
            }
        ]
    )

    assert read_fair_prices_for_fills(
        db_path, fills, max_horizon_seconds=30.0, max_lag_seconds=1.0
    ).empty


def test_fair_prices_are_not_read_for_fills_that_name_no_model(tmp_path):
    db_path = str(tmp_path / "prices.sqlite")

    assert read_fair_prices_for_fills(
        db_path,
        pd.DataFrame(),
        max_horizon_seconds=30.0,
        max_lag_seconds=1.0,
    ).empty
    assert read_fair_prices_for_fills(
        db_path,
        pd.DataFrame([{"timestamp": 10.0, "symbol": "BTC/USD"}]),
        max_horizon_seconds=30.0,
        max_lag_seconds=1.0,
    ).empty
