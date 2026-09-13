import sqlite3
import sys

from streamlit.testing.v1 import AppTest

from jolteon.app.data import engine_databases
from jolteon.app.settings import parse_args


def script():
    from jolteon.app.settings import init_settings

    init_settings()


def test_parse_args_defaults_db_path(monkeypatch):
    monkeypatch.setattr(sys, "argv", ["prog"])

    args = parse_args()

    assert args.db == "/tmp/jolteon-*.sqlite"
    assert args.log_db == ""


def test_parse_args_reads_custom_db_path(monkeypatch):
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "prog",
            "--db",
            "/custom/path.sqlite",
            "--log-db",
            "/custom/log.sqlite",
        ],
    )

    args = parse_args()

    assert args.db == "/custom/path.sqlite"
    assert args.log_db == "/custom/log.sqlite"


def test_init_settings_sets_session_state_defaults():
    at = AppTest.from_function(script).run()

    assert not at.exception
    assert at.session_state["db_glob"] == "/tmp/jolteon-*.sqlite"
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


def _recording(tmp_path, symbol: str) -> str:
    """An engine recording with one tick in it, named as the engine
    names its own."""
    path = tmp_path / f"jolteon-{symbol.replace('/', '-')}.sqlite"
    conn = sqlite3.connect(path)
    try:
        conn.execute("CREATE TABLE ticker_feed (timestamp REAL, symbol TEXT)")
        conn.execute(
            "INSERT INTO ticker_feed VALUES (1700000000, ?)", (symbol,)
        )
        conn.commit()
    finally:
        conn.close()
    return str(path)


def test_finds_every_engine_recording_and_names_it_by_its_symbol(tmp_path):
    _recording(tmp_path, "ETH/USD")
    _recording(tmp_path, "BTC/USD")

    found = engine_databases(str(tmp_path / "jolteon-*.sqlite"))

    assert ["BTC/USD", "ETH/USD"] == [e.symbol for e in found]


def test_a_recording_with_no_ticks_is_named_after_its_file(tmp_path):
    """
    An engine that has only just started has recorded nothing to take a
    symbol from, and still has to be nameable.
    """
    path = tmp_path / "jolteon-SOL-USD.sqlite"
    sqlite3.connect(path).close()

    found = engine_databases(str(path))

    assert ["jolteon-SOL-USD"] == [e.symbol for e in found]


def test_an_engines_logs_sit_beside_its_recording(tmp_path):
    path = _recording(tmp_path, "ETH/USD")
    found = engine_databases(path)

    assert found[0].log_path == path.replace(".sqlite", ".log.sqlite")


def test_starts_on_the_first_engine_it_finds(tmp_path):
    _recording(tmp_path, "ETH/USD")
    btc = _recording(tmp_path, "BTC/USD")

    at = AppTest.from_function(script)
    at.session_state["db_glob"] = str(tmp_path / "jolteon-*.sqlite")
    at.run()

    assert not at.exception
    assert at.session_state["db_path"] == btc
    assert at.session_state["log_db_path"].endswith("BTC-USD.log.sqlite")


def test_finds_an_engine_that_started_after_the_dashboard(tmp_path):
    """
    A dashboard opened first must not stay pinned to a database that did
    not exist when it looked.
    """
    at = AppTest.from_function(script)
    at.session_state["db_glob"] = str(tmp_path / "jolteon-*.sqlite")
    at.run()
    assert at.session_state["db_path"] == str(tmp_path / "jolteon-*.sqlite")

    eth = _recording(tmp_path, "ETH/USD")
    at.run()

    assert at.session_state["db_path"] == eth


def test_keeps_the_engine_the_reader_chose(tmp_path):
    eth = _recording(tmp_path, "ETH/USD")
    _recording(tmp_path, "BTC/USD")

    def choose():
        import streamlit as st

        from jolteon.app.data import engine_databases
        from jolteon.app.settings import init_settings, use_engine

        init_settings()
        chosen = [
            e
            for e in engine_databases(st.session_state.db_glob)
            if e.symbol == "ETH/USD"
        ]
        if chosen and st.session_state.get("_choose"):
            use_engine(chosen[0])
        st.session_state["_choose"] = True

    at = AppTest.from_function(choose)
    at.session_state["db_glob"] = str(tmp_path / "jolteon-*.sqlite")
    at.session_state["_choose"] = True
    at.run()
    assert at.session_state["db_path"] == eth

    at.run()

    assert at.session_state["db_path"] == eth
