import sqlite3
import time

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
            "jolteon.engine.market_data",
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
    assert entry.caption[0].value == "jolteon.engine.market_data · feed.py:42"


def test_includes_critical_rows_alongside_error(tmp_path):
    db_path = str(tmp_path / "logs.sqlite")
    _write_logs(
        db_path,
        (
            "1700000000.0",
            "jolteon",
            "ERROR",
            "feed.py",
            "42",
            "connection dropped",
        ),
        (
            "1700000001.0",
            "jolteon",
            "CRITICAL",
            "engine.py",
            "7",
            "out of memory",
        ),
    )

    at = AppTest.from_function(_script)
    at.session_state["log_db_path"] = db_path
    at.run()

    assert not at.exception
    # CRITICAL used to be silently dropped: the old filter matched only
    # levelname == "ERROR", so a component that died with a CRITICAL log
    # line never showed up on this card at all.
    assert len(at.status) == 2
    labels = [entry.label for entry in at.status]
    assert any("connection dropped" in label for label in labels)
    assert any("out of memory" in label for label in labels)


def test_formats_a_just_recorded_entry_in_seconds(tmp_path):
    db_path = str(tmp_path / "logs.sqlite")
    _write_logs(
        db_path,
        (
            str(time.time() - 5),
            "jolteon",
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
    assert "seconds ago" in at.status[0].label


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
