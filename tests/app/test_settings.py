import sqlite3
import sys

from streamlit.testing.v1 import AppTest

from jolteon import paths
from jolteon.app.data import engine_databases
from jolteon.app.settings import parse_args


def script():
    from jolteon.app.settings import init_settings

    init_settings()


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


def test_init_settings_does_not_override_existing_session_state():
    at = AppTest.from_function(script)
    at.session_state["db_path"] = "/already/set.sqlite"
    at.session_state["auto_refresh"] = False
    at.run()

    assert not at.exception
    assert at.session_state["db_path"] == "/already/set.sqlite"
    assert at.session_state["auto_refresh"] is False


def _recording(root, symbol: str) -> str:
    """One engine's recording, laid out where an engine would lay it."""
    path = paths.recording(str(root), symbol)
    paths.prepare(path)
    conn = sqlite3.connect(path)
    try:
        conn.execute("CREATE TABLE ticker_feed (timestamp REAL, symbol TEXT)")
        conn.execute(
            "INSERT INTO ticker_feed VALUES (1700000000, ?)", (symbol,)
        )
        conn.commit()
    finally:
        conn.close()
    return path


def test_finds_every_symbol_that_has_been_traded(tmp_path):
    _recording(tmp_path, "ETH/USD")
    _recording(tmp_path, "BTC/USD")

    found = engine_databases(str(tmp_path))

    assert ["BTC/USD", "ETH/USD"] == [e.symbol for e in found]


def test_a_symbol_directory_holds_its_own_recording_and_log(tmp_path):
    path = _recording(tmp_path, "ETH/USD")

    found = engine_databases(str(tmp_path))

    assert found[0].path == path
    assert found[0].path.endswith("ETH-USD/live.sqlite")
    assert found[0].log_path.endswith("ETH-USD/live.log.sqlite")


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
    sqlite3.connect(paths.parameter_store(str(tmp_path))).close()

    found = engine_databases(str(tmp_path))

    assert ["ETH/USD"] == [e.symbol for e in found]


def test_starts_on_the_first_symbol_it_finds(tmp_path):
    _recording(tmp_path, "ETH/USD")
    btc = _recording(tmp_path, "BTC/USD")

    at = AppTest.from_function(script)
    at.session_state["root"] = str(tmp_path)
    at.run()

    assert not at.exception
    assert at.session_state["db_path"] == btc
    assert at.session_state["log_db_path"].endswith("BTC-USD/live.log.sqlite")


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
    at.run()

    assert at.session_state["db_path"] == eth


def test_the_tuning_store_sits_at_the_root(tmp_path):
    at = AppTest.from_function(script)
    at.session_state["root"] = str(tmp_path)
    at.run()

    assert at.session_state["params_db_path"] == str(
        tmp_path / "parameters.sqlite"
    )


def test_keeps_the_symbol_the_reader_chose(tmp_path):
    eth = _recording(tmp_path, "ETH/USD")
    _recording(tmp_path, "BTC/USD")

    def choose():
        import streamlit as st

        from jolteon.app.data import engine_databases
        from jolteon.app.settings import init_settings, use_engine

        init_settings()
        chosen = [
            e
            for e in engine_databases(st.session_state.root)
            if e.symbol == "ETH/USD"
        ]
        if chosen and st.session_state.get("_choose"):
            use_engine(chosen[0])
        st.session_state["_choose"] = True

    at = AppTest.from_function(choose)
    at.session_state["root"] = str(tmp_path)
    at.session_state["_choose"] = True
    at.run()
    assert at.session_state["db_path"] == eth

    at.run()

    assert at.session_state["db_path"] == eth
