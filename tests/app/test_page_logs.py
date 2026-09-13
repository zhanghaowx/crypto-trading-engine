import time

from streamlit.testing.v1 import AppTest


def _script():
    from jolteon.app.app_pages import logs

    logs.render()


def _page(engines) -> AppTest:
    at = AppTest.from_function(_script)
    at.session_state["root"] = engines.root
    return at


def _error(
    created: str,
    msg: str = "connection dropped",
    level: str = "ERROR",
    name: str = "jolteon.engine.market_data",
    filename: str = "feed.py",
    lineno: str = "42",
):
    return (created, name, level, filename, lineno, msg)


def test_warns_when_no_engine_has_recorded_anything(engines):
    at = _page(engines).run()

    assert not at.exception
    assert engines.root in at.warning[0].value
    assert not at.info


def test_shows_info_when_no_logs_recorded(engines):
    engines.add("BTC/USD")

    at = _page(engines).run()

    assert not at.exception
    assert not at.warning
    assert at.info[0].value == "No ERROR logs recorded yet."


def test_shows_info_when_only_non_error_logs_recorded(engines):
    engines.add(
        "BTC/USD",
        logs=[_error("1700000000.0", "started", level="INFO")],
    )

    at = _page(engines).run()

    assert not at.exception
    assert at.info[0].value == "No ERROR logs recorded yet."


def test_renders_only_error_rows_as_expandable_entries(engines):
    engines.add(
        "BTC/USD",
        logs=[
            _error("1700000000.0", "started", level="INFO"),
            _error("1700000001.0"),
        ],
    )

    at = _page(engines).run()

    assert not at.exception
    # An st.expander with an icon is exposed as `at.status`, not
    # `at.expander` - the info-level row never shows up as an entry.
    assert len(at.status) == 1
    entry = at.status[0]
    assert "connection dropped" in entry.label
    assert (
        entry.caption[0].value
        == "BTC/USD · jolteon.engine.market_data · feed.py:42"
    )


def test_includes_critical_rows_alongside_error(engines):
    engines.add(
        "BTC/USD",
        logs=[
            _error("1700000000.0"),
            _error("1700000001.0", "out of memory", level="CRITICAL"),
        ],
    )

    at = _page(engines).run()

    assert not at.exception
    # CRITICAL used to be silently dropped: the old filter matched only
    # levelname == "ERROR", so a component that died with a CRITICAL log
    # line never showed up on this card at all.
    assert len(at.status) == 2
    labels = [entry.label for entry in at.status]
    assert any("connection dropped" in label for label in labels)
    assert any("out of memory" in label for label in labels)


def test_every_engine_reports_its_errors_here(engines):
    """
    An error is worth seeing whichever symbol the reader is watching, so
    this page reads every engine rather than the one on the Live page.
    """
    engines.add("BTC/USD", logs=[_error("1700000000.0", "book gap")])
    engines.add("ETH/USD", logs=[_error("1700000001.0", "order rejected")])

    at = _page(engines).run()

    assert not at.exception
    labels = [entry.label for entry in at.status]
    assert any("book gap" in label for label in labels)
    assert any("order rejected" in label for label in labels)


def test_an_entry_names_the_symbol_whose_engine_logged_it(engines):
    engines.add("ETH/USD", logs=[_error("1700000000.0")])

    at = _page(engines).run()

    assert at.status[0].label.startswith("`ETH/USD`")


def test_entries_from_every_engine_share_one_order(engines):
    """
    Newest first across the engines together, not one engine's log after
    another's - the reader is looking for what happened last.
    """
    engines.add("BTC/USD", logs=[_error("1700000000.0", "older")])
    engines.add("ETH/USD", logs=[_error("1700000002.0", "newest")])

    at = _page(engines).run()

    assert ["newest" in entry.label for entry in at.status] == [True, False]


def test_two_engines_logging_at_once_keep_their_own_entries(engines):
    """
    A log record is identified by when it was written, which is unique
    only within one engine's log. Keyed by that alone, one of two
    simultaneous errors would reuse the other's entry and never be drawn.
    """
    engines.add("BTC/USD", logs=[_error("1700000000.0", "book gap")])
    engines.add("ETH/USD", logs=[_error("1700000000.0", "order rejected")])

    at = _page(engines).run()

    assert len(at.status) == 2


def test_formats_a_just_recorded_entry_in_seconds(engines):
    engines.add("BTC/USD", logs=[_error(str(time.time() - 5))])

    at = _page(engines).run()

    assert not at.exception
    assert "seconds ago" in at.status[0].label


def test_strips_the_formatter_s_own_prefix_from_the_message(engines):
    engines.add(
        "BTC/USD",
        logs=[
            _error(
                "1700000001.0",
                "[2026-09-09 20:55:20.477228][root][ERROR][MD]"
                "[signal_recorder.py:107] - "
                "[2026-09-09 20:55:20.477228][root][ERROR][MD]"
                "[signal_recorder.py:107] - "
                "Fail to persist signal cancel_order: "
                "Cannot convert <class 'str'> to dict!",
                name="root",
                filename="signal_recorder.py",
                lineno="107",
            )
        ],
    )

    at = _page(engines).run()

    assert not at.exception
    assert at.status[0].label.endswith(
        "Fail to persist signal cancel_order: "
        "Cannot convert <class 'str'> to dict!"
    )
