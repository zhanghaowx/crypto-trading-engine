import sqlite3
from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

_DASHBOARD_PATH = str(
    Path(__file__).resolve().parents[2] / "jolteon" / "app" / "dashboard.py"
)


@pytest.fixture
def dashboard(missing_db_path) -> AppTest:
    """A ready-to-run AppTest for the dashboard entrypoint, with
    auto-refresh disabled (it would otherwise sleep and rerun forever)
    and a placeholder db_path callers can override before calling
    `.run()`."""
    at = AppTest.from_file(_DASHBOARD_PATH)
    at.session_state["auto_refresh"] = False
    at.session_state["db_path"] = missing_db_path
    return at


@pytest.fixture
def missing_db_path(tmp_path) -> str:
    """A database path that does not exist on disk."""
    return str(tmp_path / "missing.sqlite")


@pytest.fixture
def empty_db_path(tmp_path) -> str:
    """A database file that exists but has none of the expected tables."""
    db_path = str(tmp_path / "empty.sqlite")
    sqlite3.connect(db_path).close()
    return db_path


@pytest.fixture
def populated_db_path(tmp_path) -> str:
    """A database with one representative row in each table the dashboard
    pages read from."""
    db_path = str(tmp_path / "populated.sqlite")
    conn = sqlite3.connect(db_path)
    try:
        conn.execute(
            "CREATE TABLE heartbeat "
            "(timestamp REAL, sender TEXT, level INTEGER, message TEXT)"
        )
        conn.execute(
            "INSERT INTO heartbeat VALUES "
            "(1700000000, 'MarketMaking', 1, 'All good')"
        )

        conn.execute(
            "CREATE TABLE ticker_feed "
            "(timestamp REAL, symbol TEXT, bid_price REAL, ask_price REAL)"
        )
        conn.execute(
            "INSERT INTO ticker_feed VALUES "
            "(1700000000, 'BTC-USD', 100.0, 101.0)"
        )

        conn.execute(
            "CREATE TABLE calculated_candlestick_feed "
            "(start_time REAL, close REAL)"
        )
        conn.execute(
            "INSERT INTO calculated_candlestick_feed VALUES "
            "(1700000000, 100.5)"
        )

        conn.execute(
            'CREATE TABLE "order" '
            "(timestamp REAL, side TEXT, price REAL, symbol TEXT, "
            "client_order_id TEXT)"
        )
        conn.execute(
            'INSERT INTO "order" VALUES '
            "(1700000000, 'BUY', 99.5, 'BTC-USD', '1')"
        )

        conn.execute(
            "CREATE TABLE order_fill "
            "(timestamp REAL, side TEXT, price REAL, quantity REAL, "
            "fee REAL, symbol TEXT)"
        )
        conn.execute(
            "INSERT INTO order_fill VALUES "
            "(1700000000, 'BUY', 99.5, 1.0, 0.1, 'BTC-USD')"
        )

        conn.execute(
            "CREATE TABLE risk_limit_snapshot "
            "(timestamp REAL, name TEXT, symbol TEXT, maximum REAL, "
            "current REAL)"
        )
        conn.execute(
            "INSERT INTO risk_limit_snapshot VALUES "
            "(1700000000, 'inventory', 'BTC-USD', 10.0, 5.0)"
        )
        conn.commit()
    finally:
        conn.close()
    return db_path
