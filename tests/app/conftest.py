import sqlite3
import time
from html.parser import HTMLParser
from pathlib import Path

import pytest
import streamlit as st
from streamlit.testing.v1 import AppTest

from jolteon.engine.core.storage import paths

_DASHBOARD_PATH = str(
    Path(__file__).resolve().parents[2] / "jolteon" / "app" / "dashboard.py"
)


class _TableReader(HTMLParser):
    """Reads the tables `jolteon.app.table` renders back out of an app's
    HTML, so a test can assert on what a reader would actually see.

    The tables are plain HTML rather than `st.dataframe`, which AppTest
    exposes directly - so they arrive as one `html` element each and have
    to be parsed. `pandas.read_html` would need lxml, which this project
    does not depend on.
    """

    def __init__(self) -> None:
        super().__init__()
        self.tables: list[dict] = []
        self._cell: list[str] | None = None
        self._row: list[str] = []
        self._styles: list[str] = []
        self._in_help = False

    def handle_starttag(self, tag, attrs):
        attributes = dict(attrs)
        if tag == "table":
            self.tables.append({"columns": [], "rows": [], "styles": []})
        elif tag == "span" and "jolteon-help" in attributes.get("class", ""):
            # The help marker's "?" is chrome, not part of the label.
            self._in_help = True
            self.tables[-1].setdefault("help", {})
        elif tag in ("td", "th"):
            self._cell = []
            self._styles.append(attributes.get("style", ""))
        elif tag == "tr":
            self._row, self._styles = [], []

    def handle_endtag(self, tag):
        if tag == "span":
            self._in_help = False
        elif tag in ("td", "th") and self._cell is not None:
            self._row.append("".join(self._cell).strip())
            self._cell = None
        elif tag == "tr" and self._row:
            table = self.tables[-1]
            if not table["columns"]:
                table["columns"] = self._row
            else:
                table["rows"].append(self._row)
                table["styles"].append(self._styles)
            self._row = []

    def handle_data(self, data):
        if self._cell is not None and not self._in_help:
            self._cell.append(data)


def _read_tables(html: str) -> list[dict]:
    reader = _TableReader()
    reader.feed(html)
    return [t for t in reader.tables if t["columns"]]


@pytest.fixture
def tables():
    """Every table an app rendered, in order, as
    `{"columns", "rows", "styles"}` - and a lookup by a keyed column."""

    def read(at) -> list[dict]:
        found: list[dict] = []
        for element in at.get("html"):
            found.extend(_read_tables(element.body))
        return found

    return read


@pytest.fixture
def table_lookup(tables):
    """One table's rows keyed by the value in `key_column`, each row a
    dict of column name to the text a reader sees."""

    def lookup(at, index: int, key_column: str) -> dict[str, dict[str, str]]:
        table = tables(at)[index]
        columns = table["columns"]
        position = columns.index(key_column)
        return {
            row[position]: dict(zip(columns, row)) for row in table["rows"]
        }

    return lookup


@pytest.fixture(autouse=True)
def fresh_scan():
    """
    `engine_databases` is cached for `SCAN_SECONDS`, and that cache is
    process-global rather than per-session, so a test that writes a
    recording would otherwise be answered with whatever the previous
    test's directory held.
    """
    st.cache_data.clear()
    yield
    st.cache_data.clear()


@pytest.fixture
def dashboard(tmp_path, missing_db_path) -> AppTest:
    """A ready-to-run AppTest for the dashboard entrypoint, with
    auto-refresh disabled (it would otherwise sleep and rerun forever)
    and a root callers can repoint before calling `.run()`. The databases
    every page reads follow from that root, so they are not set here."""
    at = AppTest.from_file(_DASHBOARD_PATH)
    at.session_state["auto_refresh"] = False
    # Kept inside the test's own directory: left at its default this
    # would discover whatever engines the machine really has running.
    at.session_state["root"] = str(tmp_path / "no-engine")
    at.session_state["params_db_path"] = missing_db_path
    return at


@pytest.fixture
def params_db_path(tmp_path) -> str:
    """A parameter store path the Engine tab can push into."""
    return str(tmp_path / "params.sqlite")


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
def live_db_path(tmp_path) -> str:
    """A database whose only heartbeat was written just now, so the health
    page sees the sender as alive rather than timed out."""
    db_path = str(tmp_path / "live.sqlite")
    conn = sqlite3.connect(db_path)
    try:
        conn.execute(
            "CREATE TABLE heartbeat "
            "(timestamp REAL, sender TEXT, level INTEGER, message TEXT)"
        )
        conn.execute(
            "INSERT INTO heartbeat VALUES (?, 'MarketMaking', 1, 'All good')",
            (time.time(),),
        )
        conn.commit()
    finally:
        conn.close()
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
            "CREATE TABLE bbo_feed "
            "(timestamp REAL, symbol TEXT, bid_price REAL, ask_price REAL)"
        )
        conn.execute(
            "INSERT INTO bbo_feed VALUES (1700000000, 'BTC-USD', 100.0, 101.0)"
        )

        conn.execute(
            'CREATE TABLE "order" '
            "(timestamp REAL, creation_time REAL, side TEXT, price REAL, "
            "quantity REAL, symbol TEXT, client_order_id TEXT, "
            "order_type TEXT)"
        )
        conn.execute(
            'INSERT INTO "order" VALUES '
            "(1700000000, 1700000000, 'BUY', 99.5, 1.0, 'BTC-USD', '1', "
            "'limit')"
        )

        conn.execute(
            "CREATE TABLE decorated_order_fill "
            "(timestamp REAL, transaction_timestamp REAL, side TEXT, "
            "fill_price REAL, fill_qty REAL, fee REAL, symbol TEXT, "
            "exchange_execution_id TEXT PRIMARY KEY, fair_price_at_fill REAL, "
            "inventory_before REAL, inventory_after REAL, "
            "fair_price_100ms REAL, fair_price_1s REAL, fair_price_5s REAL, "
            "fair_price_30s REAL)"
        )
        conn.execute(
            "INSERT INTO decorated_order_fill VALUES "
            "(1700000000, 1700000000, 'BUY', 99.5, 1.0, 0.1, 'BTC-USD', 2, "
            "100.0, 0.0, 1.0, NULL, NULL, NULL, NULL)"
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

        conn.execute(
            "CREATE TABLE fair_price_adjustment "
            "(timestamp REAL, symbol TEXT, base_fair_price REAL, "
            '"adjustments.momentum" REAL, total_adjustment REAL, '
            "clamped INTEGER)"
        )
        conn.execute(
            "INSERT INTO fair_price_adjustment VALUES "
            "(1700000000, 'BTC-USD', 100.0, 0.5, 0.5, 0)"
        )

        conn.execute(
            "CREATE TABLE fair_price "
            "(timestamp REAL, symbol TEXT, model TEXT, bid_fair_price REAL, "
            "ask_fair_price REAL)"
        )
        conn.execute(
            "INSERT INTO fair_price VALUES "
            "(1700000000.1, 'BTC-USD', 'MidPriceFairPriceModel', 100.3, "
            "100.7), "
            "(1700000001, 'BTC-USD', 'MidPriceFairPriceModel', 100.5, 101.5)"
        )
        conn.commit()
    finally:
        conn.close()
    return db_path


class _Engines:
    """Engines as they leave themselves on disk: a directory per symbol,
    holding that engine's recording and its own log database."""

    def __init__(self, root: str) -> None:
        self.root = root

    def add(self, symbol: str, *, heartbeats=(), logs=()) -> str:
        recording = paths.recording(self.root, symbol)
        Path(recording).parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(recording)
        try:
            conn.execute(
                "CREATE TABLE bbo_feed "
                "(timestamp REAL, symbol TEXT, bid_price REAL, ask_price REAL)"
            )
            conn.execute(
                "INSERT INTO bbo_feed VALUES (1700000000, ?, 100.0, 101.0)",
                (symbol,),
            )
            conn.execute(
                "CREATE TABLE heartbeat "
                "(timestamp REAL, sender TEXT, level INTEGER, message TEXT)"
            )
            conn.executemany(
                "INSERT INTO heartbeat VALUES (?, ?, ?, ?)", heartbeats
            )
            conn.commit()
        finally:
            conn.close()

        conn = sqlite3.connect(paths.log_database(self.root, symbol))
        try:
            conn.execute(
                "CREATE TABLE logs (created TEXT, name TEXT, levelname TEXT, "
                "filename TEXT, lineno TEXT, msg TEXT)"
            )
            conn.executemany(
                "INSERT INTO logs VALUES (?, ?, ?, ?, ?, ?)", logs
            )
            conn.commit()
        finally:
            conn.close()
        return recording


@pytest.fixture
def engines(tmp_path) -> _Engines:
    """A root to start engines under, one symbol at a time."""
    return _Engines(str(tmp_path / "engines"))


@pytest.fixture
def recordings(tmp_path):
    """Two engines' recordings, as two engines running two symbols would
    leave behind: one file each, named for the symbol it traded."""

    def write(symbol: str) -> str:
        path = paths.recording(str(tmp_path), symbol)
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(path)
        try:
            conn.execute(
                "CREATE TABLE bbo_feed "
                "(timestamp REAL, symbol TEXT, bid_price REAL, ask_price REAL)"
            )
            conn.execute(
                "INSERT INTO bbo_feed VALUES (1700000000, ?, 100.0, 101.0)",
                (symbol,),
            )
            conn.commit()
        finally:
            conn.close()
        # An engine's log database sits in its own symbol's directory.
        sqlite3.connect(paths.log_database(str(tmp_path), symbol)).close()
        return path

    return {symbol: write(symbol) for symbol in ("BTC/USD", "ETH/USD")}
