import shutil
import sqlite3
import sys
from pathlib import Path

from streamlit.testing.v1 import AppTest

from jolteon.app import data
from jolteon.app.data import engine_databases
from jolteon.app.settings import SYMBOL, parse_args
from jolteon.engine.core.storage import paths


def script():
    from jolteon.app.settings import init_settings

    init_settings()


def script_with_custom_parameter_store():
    import sys

    from jolteon.app.settings import init_settings

    original = sys.argv
    try:
        sys.argv = ["dashboard", "--params-db", "/custom/parameters.sqlite"]
        init_settings()
    finally:
        sys.argv = original


def test_parse_args_defaults_db_path(monkeypatch):
    monkeypatch.setattr(sys, "argv", ["prog"])

    args = parse_args()

    assert args.root == "/tmp/jolteon"
    assert args.log_db == ""


def test_parse_args_reads_custom_db_path(monkeypatch):
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "prog",
            "--root",
            "/custom/root",
            "--log-db",
            "/custom/log.sqlite",
        ],
    )

    args = parse_args()

    assert args.root == "/custom/root"
    assert args.log_db == "/custom/log.sqlite"


def test_init_settings_sets_session_state_defaults():
    at = AppTest.from_function(script).run()

    assert not at.exception
    assert at.session_state["root"] == "/tmp/jolteon"
    assert at.session_state["auto_refresh"] is True
    assert at.session_state["refresh_seconds"] == 5
    assert at.session_state["chart_window_minutes"] == 15


def test_init_settings_does_not_override_a_readers_own_settings():
    at = AppTest.from_function(script)
    at.session_state["auto_refresh"] = False
    at.session_state["refresh_seconds"] = 30
    at.run()

    assert not at.exception
    assert at.session_state["auto_refresh"] is False
    assert at.session_state["refresh_seconds"] == 30


def test_init_settings_uses_an_explicit_parameter_store():
    at = AppTest.from_function(script_with_custom_parameter_store).run()

    assert not at.exception
    assert at.session_state["params_db_path"] == "/custom/parameters.sqlite"


def _recording(root, symbol: str) -> str:
    """One engine's recording, laid out where an engine would lay it."""
    path = paths.recording(str(root), symbol)
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    try:
        conn.execute("CREATE TABLE bbo_feed (timestamp REAL, symbol TEXT)")
        conn.execute("INSERT INTO bbo_feed VALUES (1700000000, ?)", (symbol,))
        conn.commit()
    finally:
        conn.close()
    return path


def _exchange_recording(root, exchange: str, symbol: str) -> str:
    path = paths.recording(str(root), exchange, symbol)
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    try:
        conn.execute("CREATE TABLE bbo_feed (timestamp REAL, symbol TEXT)")
        conn.execute("INSERT INTO bbo_feed VALUES (1700000000, ?)", (symbol,))
        conn.commit()
    finally:
        conn.close()
    return path


def test_same_symbol_on_two_exchanges_has_two_dashboard_identities(tmp_path):
    kraken = _exchange_recording(tmp_path, "Kraken", "BTC/USD")
    binance = _exchange_recording(tmp_path, "Binance.US", "BTC/USD")

    found = engine_databases(str(tmp_path))

    assert [(engine.key, engine.path) for engine in found] == [
        ("binance-us:BTC/USD", binance),
        ("kraken:BTC/USD", kraken),
    ]


def test_finds_every_symbol_that_has_been_traded(tmp_path):
    _recording(tmp_path, "ETH/USD")
    _recording(tmp_path, "BTC/USD")

    found = engine_databases(str(tmp_path))

    assert ["BTC/USD", "ETH/USD"] == [e.symbol for e in found]


def test_a_symbol_directory_holds_its_own_recording_and_log(tmp_path):
    path = _recording(tmp_path, "ETH/USD")

    found = engine_databases(str(tmp_path))

    assert found[0].path == path
    assert found[0].path == paths.recording(str(tmp_path), "ETH/USD")
    assert found[0].log_path == paths.log_database(str(tmp_path), "ETH/USD")


def test_a_symbol_with_no_ticks_is_named_after_its_directory(tmp_path):
    """
    An engine that has only just started has recorded nothing to take a
    symbol from, and still has to be nameable.
    """
    paths.symbol_directory(str(tmp_path), "SOL/USD").mkdir(parents=True)

    found = engine_databases(str(tmp_path))

    assert ["SOL/USD"] == [e.symbol for e in found]


def test_the_tuning_store_is_not_a_symbol(tmp_path):
    """
    One store serves every engine, so it sits at the root beside the
    symbols rather than inside any one of them.
    """
    _recording(tmp_path, "ETH/USD")
    parameter_store = paths.parameter_store(str(tmp_path))
    Path(parameter_store).parent.mkdir(parents=True, exist_ok=True)
    sqlite3.connect(parameter_store).close()

    found = engine_databases(str(tmp_path))

    assert ["ETH/USD"] == [e.symbol for e in found]


def test_the_root_is_scanned_once_for_every_reader_of_it(
    tmp_path, monkeypatch
):
    """
    Every page asks which engines are running, and naming one means
    opening its recording to read the symbol back. Asked afresh each
    time, a page with several such readers reopens every engine's file on
    every rerun.
    """
    _recording(tmp_path, "ETH/USD")
    _recording(tmp_path, "BTC/USD")
    opened = []
    real = data.read_latest_row
    monkeypatch.setattr(
        data,
        "read_latest_row",
        lambda db_path, table: opened.append(db_path) or real(db_path, table),
    )

    engine_databases(str(tmp_path))
    engine_databases(str(tmp_path))

    assert len(opened) == 2


def test_starts_on_the_first_symbol_it_finds(tmp_path):
    _recording(tmp_path, "ETH/USD")
    btc = _recording(tmp_path, "BTC/USD")

    at = AppTest.from_function(script)
    at.session_state["root"] = str(tmp_path)
    at.run()

    assert not at.exception
    assert at.session_state["db_path"] == btc
    assert at.session_state["log_db_path"] == paths.log_database(
        str(tmp_path), "BTC/USD"
    )


def test_finds_a_symbol_that_started_after_the_dashboard(tmp_path):
    """
    A dashboard opened first must not stay pinned to a database that did
    not exist when it looked.
    """
    at = AppTest.from_function(script)
    at.session_state["root"] = str(tmp_path)
    at.run()
    assert at.session_state["db_path"] == ""

    eth = _recording(tmp_path, "ETH/USD")
    # What a real dashboard waits out: the root is scanned at most once
    # every `SCAN_SECONDS`, and this engine started inside that window.
    engine_databases.clear()
    at.run()

    assert at.session_state["db_path"] == eth


def test_the_tuning_store_sits_at_the_root(tmp_path):
    at = AppTest.from_function(script)
    at.session_state["root"] = str(tmp_path)
    at.run()

    assert at.session_state["params_db_path"] == str(
        tmp_path / "kraken" / "parameters.sqlite"
    )


def test_keeps_the_symbol_the_reader_chose(tmp_path):
    eth = _recording(tmp_path, "ETH/USD")
    _recording(tmp_path, "BTC/USD")

    at = AppTest.from_function(script)
    at.session_state["root"] = str(tmp_path)
    at.session_state[SYMBOL] = "ETH/USD"
    at.run()

    assert not at.exception
    assert at.session_state["db_path"] == eth
    assert at.session_state["log_db_path"] == paths.log_database(
        str(tmp_path), "ETH/USD"
    )


def test_reads_the_symbol_a_link_names(tmp_path):
    """
    A link to one symbol has to open on it, and the page that draws the
    picker has not registered its value yet when this runs.
    """
    eth = _recording(tmp_path, "ETH/USD")
    _recording(tmp_path, "BTC/USD")

    at = AppTest.from_function(script)
    at.session_state["root"] = str(tmp_path)
    at.query_params[SYMBOL] = "ETH/USD"
    at.run()

    assert not at.exception
    assert at.session_state["db_path"] == eth


def test_falls_back_when_the_url_names_a_symbol_nothing_trades(tmp_path):
    btc = _recording(tmp_path, "BTC/USD")

    at = AppTest.from_function(script)
    at.session_state["root"] = str(tmp_path)
    at.query_params[SYMBOL] = "SOL/USD"
    at.run()

    assert not at.exception
    assert at.session_state["db_path"] == btc


def test_lets_go_of_an_engine_that_has_stopped(tmp_path):
    """
    Engines start and stop while a dashboard is open. Pinned to the
    symbol it was told about, the page would go on pointing at a file
    that is no longer there and warn in every section forever.
    """
    _recording(tmp_path, "ETH/USD")
    btc = _recording(tmp_path, "BTC/USD")

    at = AppTest.from_function(script)
    at.session_state["root"] = str(tmp_path)
    at.session_state[SYMBOL] = "ETH/USD"
    at.run()

    shutil.rmtree(paths.symbol_directory(str(tmp_path), "ETH/USD"))
    engine_databases.clear()
    at.run()

    assert not at.exception
    assert at.session_state["db_path"] == btc
