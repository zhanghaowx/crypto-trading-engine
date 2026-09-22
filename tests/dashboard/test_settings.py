import shutil
import sys

from streamlit.testing.v1 import AppTest

from jolteon.dashboard.data.engines import engine_databases
from jolteon.dashboard.settings import RUN, SYMBOL, parse_args
from jolteon.engine.core.storage import paths
from tests.dashboard.conftest import recording, scoped_run


def script():
    from jolteon.dashboard.settings import init_settings

    init_settings()


def script_with_custom_parameter_store():
    import sys

    from jolteon.dashboard.settings import init_settings

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


def test_starts_on_the_first_symbol_it_finds(tmp_path):
    recording(tmp_path, "ETH/USD")
    btc = recording(tmp_path, "BTC/USD")

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

    eth = recording(tmp_path, "ETH/USD")
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
    eth = recording(tmp_path, "ETH/USD")
    recording(tmp_path, "BTC/USD")

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
    eth = recording(tmp_path, "ETH/USD")
    recording(tmp_path, "BTC/USD")

    at = AppTest.from_function(script)
    at.session_state["root"] = str(tmp_path)
    at.query_params[SYMBOL] = "ETH/USD"
    at.run()

    assert not at.exception
    assert at.session_state["db_path"] == eth


def test_falls_back_when_the_url_names_a_symbol_nothing_trades(tmp_path):
    btc = recording(tmp_path, "BTC/USD")

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
    recording(tmp_path, "ETH/USD")
    btc = recording(tmp_path, "BTC/USD")

    at = AppTest.from_function(script)
    at.session_state["root"] = str(tmp_path)
    at.session_state[SYMBOL] = "ETH/USD"
    at.run()

    shutil.rmtree(paths.symbol_directory(str(tmp_path), "ETH/USD"))
    engine_databases.clear()
    at.run()

    assert not at.exception
    assert at.session_state["db_path"] == btc


def test_the_run_a_page_is_scoped_to_is_the_one_it_was_given():
    at = AppTest.from_function(_run_id_script)
    at.run()
    assert at.markdown[0].value == "none"

    at.session_state[RUN] = scoped_run("run-b")
    at.run()

    assert not at.exception
    assert at.markdown[0].value == "run-b"


def _run_id_script():
    import streamlit as st

    from jolteon.dashboard.settings import current_run_id

    st.write(current_run_id() or "none")
