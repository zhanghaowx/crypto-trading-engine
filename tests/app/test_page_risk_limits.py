import sqlite3

from streamlit.testing.v1 import AppTest


def _script():
    from jolteon.app.app_pages import risk_limits

    risk_limits.render()


def test_shows_warning_when_db_missing(missing_db_path):
    at = AppTest.from_function(_script)
    at.session_state["db_path"] = missing_db_path
    at.run()

    assert not at.exception
    assert at.warning
    assert not at.info


def test_shows_info_when_no_risk_limit_data_recorded(empty_db_path):
    at = AppTest.from_function(_script)
    at.session_state["db_path"] = empty_db_path
    at.run()

    assert not at.exception
    assert not at.warning
    assert at.info


def test_renders_a_card_per_name_and_symbol(populated_db_path):
    at = AppTest.from_function(_script)
    at.session_state["db_path"] = populated_db_path
    at.session_state["chart_window_minutes"] = 15
    at.run()

    assert not at.exception
    assert at.markdown[0].value == "**Inventory**"
    assert at.caption[0].value == "BTC-USD"
    # current=5.0, maximum=10.0 -> 50% utilization -> OK badge.
    assert "OK" in at.markdown[1].value


def test_badge_reflects_utilization_thresholds(tmp_path):
    db_path = str(tmp_path / "thresholds.sqlite")
    conn = sqlite3.connect(db_path)
    conn.execute(
        "CREATE TABLE risk_limit_snapshot "
        "(timestamp REAL, name TEXT, symbol TEXT, maximum REAL, "
        "current REAL)"
    )
    conn.executemany(
        "INSERT INTO risk_limit_snapshot VALUES (?, ?, ?, ?, ?)",
        [
            (1700000000, "ok", "BTC-USD", 10.0, 5.0),  # 50% -> OK
            (1700000000, "elevated", "BTC-USD", 10.0, 7.5),  # 75% -> Elevated
            (1700000000, "near_limit", "BTC-USD", 10.0, 9.5),  # 95% -> Near
        ],
    )
    conn.commit()
    conn.close()

    at = AppTest.from_function(_script)
    at.session_state["db_path"] = db_path
    at.session_state["chart_window_minutes"] = 15
    at.run()

    assert not at.exception
    badges = " ".join(m.value for m in at.markdown)
    assert "OK" in badges
    assert "Elevated" in badges
    assert "Near Limit" in badges
