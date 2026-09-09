import sqlite3

# risk_limits.py is a Streamlit page script that runs top-level code (it
# calls warn_if_no_db() at import time), so importing it directly outside
# a running app would execute the whole page. Exercise risk_limit_badge
# through the actual page instead, via the rendered badges below.


def test_shows_warning_when_db_missing(dashboard):
    at = dashboard.switch_page("app_pages/risk_limits.py").run()

    assert not at.exception
    assert at.warning
    assert not at.info


def test_shows_info_when_no_risk_limit_data_recorded(dashboard, empty_db_path):
    dashboard.session_state["db_path"] = empty_db_path
    at = dashboard.switch_page("app_pages/risk_limits.py").run()

    assert not at.exception
    assert not at.warning
    assert at.info


def test_renders_a_card_per_name_and_symbol(dashboard, populated_db_path):
    dashboard.session_state["db_path"] = populated_db_path
    at = dashboard.switch_page("app_pages/risk_limits.py").run()

    assert not at.exception
    assert at.markdown[0].value == "**Inventory**"
    assert at.caption[0].value == "BTC-USD"
    # current=5.0, maximum=10.0 -> 50% utilization -> OK badge.
    assert "OK" in at.markdown[1].value


def test_badge_reflects_utilization_thresholds(dashboard, tmp_path):
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

    dashboard.session_state["db_path"] = db_path
    at = dashboard.switch_page("app_pages/risk_limits.py").run()

    assert not at.exception
    badges = " ".join(m.value for m in at.markdown)
    assert "OK" in badges
    assert "Elevated" in badges
    assert "Near Limit" in badges
