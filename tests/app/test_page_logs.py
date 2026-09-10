import sqlite3

from streamlit.testing.v1 import AppTest


def _script():
    from jolteon.app.app_pages import logs

    logs.render()


def _write_logs(
    db_path: str, *rows: tuple[str, str, str, str, str, str]
) -> None:
    conn = sqlite3.connect(db_path)
    conn.execute(
        "CREATE TABLE logs (created TEXT, name TEXT, levelname TEXT, "
        "filename TEXT, lineno TEXT, msg TEXT)"
    )
    conn.executemany("INSERT INTO logs VALUES (?, ?, ?, ?, ?, ?)", rows)
    conn.commit()
    conn.close()


def test_shows_warning_when_db_missing(missing_db_path):
    at = AppTest.from_function(_script)
    at.session_state["log_db_path"] = missing_db_path
    at.run()

    assert not at.exception
    assert at.warning
    assert not at.info


def test_shows_info_when_no_logs_recorded(empty_db_path):
    at = AppTest.from_function(_script)
    at.session_state["log_db_path"] = empty_db_path
    at.run()

    assert not at.exception
    assert not at.warning
    assert at.info[0].value == "No ERROR logs recorded yet."


def test_shows_info_when_only_non_error_logs_recorded(tmp_path):
    db_path = str(tmp_path / "logs.sqlite")
    _write_logs(
        db_path,
        ("1700000000.0", "jolteon", "INFO", "app.py", "10", "started"),
    )

    at = AppTest.from_function(_script)
    at.session_state["log_db_path"] = db_path
    at.run()

    assert not at.exception
    assert at.info[0].value == "No ERROR logs recorded yet."


def test_renders_only_error_rows_as_expandable_entries(tmp_path):
    db_path = str(tmp_path / "logs.sqlite")
    _write_logs(
        db_path,
        ("1700000000.0", "jolteon", "INFO", "app.py", "10", "started"),
        (
            "1700000001.0",
            "jolteon.market_data",
            "ERROR",
            "feed.py",
            "42",
            "connection dropped",
        ),
    )

    at = AppTest.from_function(_script)
    at.session_state["log_db_path"] = db_path
    at.run()

    assert not at.exception
    # An st.expander with an icon is exposed as `at.status`, not
    # `at.expander` - the info-level row never shows up as an entry.
    assert len(at.status) == 1
    entry = at.status[0]
    assert "connection dropped" in entry.label
    assert entry.caption[0].value == "jolteon.market_data · feed.py:42"


def test_strips_the_formatter_s_own_prefix_from_the_message(tmp_path):
    db_path = str(tmp_path / "logs.sqlite")
    _write_logs(
        db_path,
        (
            "1700000001.0",
            "root",
            "ERROR",
            "signal_recorder.py",
            "107",
            "[2026-09-09 20:55:20.477228][root][ERROR][MD]"
            "[signal_recorder.py:107] - "
            "[2026-09-09 20:55:20.477228][root][ERROR][MD]"
            "[signal_recorder.py:107] - "
            "Fail to persist signal cancel_order: "
            "Cannot convert <class 'str'> to dict!",
        ),
    )

    at = AppTest.from_function(_script)
    at.session_state["log_db_path"] = db_path
    at.run()

    assert not at.exception
    entry = at.status[0]
    assert entry.label.endswith(
        "Fail to persist signal cancel_order: "
        "Cannot convert <class 'str'> to dict!"
    )
