import sys

from streamlit.testing.v1 import AppTest

from jolteon.app.settings import parse_args


def script():
    from jolteon.app.settings import init_settings

    init_settings()


def test_parse_args_defaults_db_path(monkeypatch):
    monkeypatch.setattr(sys, "argv", ["prog"])

    args = parse_args()

    assert args.db == "/tmp/jolteon.sqlite"


def test_parse_args_reads_custom_db_path(monkeypatch):
    monkeypatch.setattr(sys, "argv", ["prog", "--db", "/custom/path.sqlite"])

    args = parse_args()

    assert args.db == "/custom/path.sqlite"


def test_init_settings_sets_session_state_defaults():
    at = AppTest.from_function(script).run()

    assert not at.exception
    assert at.session_state["db_path"] == "/tmp/jolteon.sqlite"
    assert at.session_state["auto_refresh"] is True
    assert at.session_state["refresh_seconds"] == 5


def test_init_settings_does_not_override_existing_session_state():
    at = AppTest.from_function(script)
    at.session_state["db_path"] = "/already/set.sqlite"
    at.session_state["auto_refresh"] = False
    at.run()

    assert not at.exception
    assert at.session_state["db_path"] == "/already/set.sqlite"
    assert at.session_state["auto_refresh"] is False
