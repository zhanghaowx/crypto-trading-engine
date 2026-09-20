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
    at.run()

    assert not at.exception
    badges = " ".join(m.value for m in at.markdown)
    assert "OK" in badges
    assert "Elevated" in badges
    assert "Near Limit" in badges


def _accent_script():
    import streamlit as st

    from jolteon.app.app_pages import risk_limits

    st.write(str(risk_limits.accent()))


def _utilization_db(tmp_path, *currents: float) -> str:
    db_path = str(tmp_path / f"accent-{'-'.join(map(str, currents))}.sqlite")
    conn = sqlite3.connect(db_path)
    try:
        conn.execute(
            "CREATE TABLE risk_limit_snapshot "
            "(timestamp REAL, name TEXT, symbol TEXT, maximum REAL, "
            "current REAL)"
        )
        conn.executemany(
            "INSERT INTO risk_limit_snapshot VALUES (?, ?, 'BTC-USD', ?, ?)",
            [
                (1700000000, f"limit{index}", 10.0, current)
                for index, current in enumerate(currents)
            ],
        )
        conn.commit()
    finally:
        conn.close()
    return db_path


def _no_maximum_db(tmp_path) -> str:
    db_path = str(tmp_path / "no-maximum.sqlite")
    conn = sqlite3.connect(db_path)
    try:
        conn.execute(
            "CREATE TABLE risk_limit_snapshot "
            "(timestamp REAL, name TEXT, symbol TEXT, maximum REAL, "
            "current REAL)"
        )
        conn.execute(
            "INSERT INTO risk_limit_snapshot VALUES "
            "(1700000000, 'unbounded', 'BTC-USD', 0.0, 5.0)"
        )
        conn.commit()
    finally:
        conn.close()
    return db_path


def test_accent_is_absent_before_any_limit_is_recorded(empty_db_path):
    at = AppTest.from_function(_accent_script)
    at.session_state["db_path"] = empty_db_path
    at.run()

    assert not at.exception
    assert at.markdown[0].value == "None"


def test_accent_follows_the_limit_closest_to_being_breached(tmp_path):
    at = AppTest.from_function(_accent_script)
    at.session_state["db_path"] = _utilization_db(tmp_path, 1.0, 9.5)
    at.run()

    assert not at.exception
    assert at.markdown[0].value == "red"


def test_accent_is_green_while_every_limit_is_comfortable(tmp_path):
    at = AppTest.from_function(_accent_script)
    at.session_state["db_path"] = _utilization_db(tmp_path, 1.0, 5.0)
    at.run()

    assert not at.exception
    assert at.markdown[0].value == "green"


def test_accent_ignores_a_limit_with_no_maximum_to_use_up(tmp_path):
    at = AppTest.from_function(_accent_script)
    # A maximum of zero is a limit nothing can be used up against, and
    # dividing by it would be a crash rather than a red edge.
    at.session_state["db_path"] = _no_maximum_db(tmp_path)
    at.run()

    assert not at.exception
    assert at.markdown[0].value == "green"


def test_the_bar_fills_to_the_utilisation_and_marks_the_bands():
    from jolteon.app.app_pages.risk_limits import utilisation_bar

    bar = utilisation_bar(0.74, "orange")

    assert "width:74.0%" in bar
    assert "background:#E8873C" in bar
    # A tick at each threshold the badge changes band at.
    assert bar.count("jolteon-limit-tick") == 2
    assert "left:70%" in bar and "left:90%" in bar


def test_the_bar_never_overflows_its_track():
    """A measure past its own limit still fills the track exactly once."""
    from jolteon.app.app_pages.risk_limits import utilisation_bar

    assert "width:100.0%" in utilisation_bar(1.8, "red")
    assert "width:0.0%" in utilisation_bar(-0.2, "green")


def test_a_limits_name_and_measure_read_as_words_and_short_numbers():
    from jolteon.app.app_pages.risk_limits import _fmt_bound, _limit_title

    assert _limit_title("order_frequency") == "Order Frequency"
    # A recorded measure carries more decimals than a reader needs.
    assert _fmt_bound(7.4457204) == "7.45"
    assert _fmt_bound(10.0) == "10"
    assert _fmt_bound(12345.6) == "12,346"
