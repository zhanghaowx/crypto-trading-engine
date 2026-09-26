import time

from streamlit.testing.v1 import AppTest


def _script():
    from jolteon.dashboard.cards import health_summary

    health_summary.render()


def _page(engines) -> AppTest:
    at = AppTest.from_function(_script)
    at.session_state["root"] = engines.root
    return at


def _metrics(at) -> dict[str, str]:
    return {m.label: m.value for m in at.metric}


def test_nothing_is_summarised_before_an_engine_has_recorded(engines):
    """The tiles under this row already say so; a second warning would
    only repeat them."""
    at = _page(engines).run()

    assert not at.exception
    assert not at.metric
    assert not at.warning


def test_counts_every_engines_components_and_the_timeout(engines):
    engines.add(
        "BTC/USD",
        heartbeats=[
            (time.time(), "MD", 1, "Streaming"),
            (time.time(), "MarketMaking", 1, "Quoting"),
        ],
    )
    engines.add("ETH/USD", heartbeats=[(time.time(), "MD", 1, "Streaming")])

    at = _page(engines).run()

    assert not at.exception
    metrics = _metrics(at)
    assert metrics["Components reporting"] == "3"
    assert metrics["Components down"] == "0"
    assert metrics["Recorded errors"] == "0"
    assert metrics["Heartbeat timeout"] == "30 s"


def test_what_is_wrong_is_the_only_thing_colored(engines):
    """Zero of anything is the ordinary case and stays in plain ink; a
    component gone quiet or an error logged is what earns the color."""
    engines.add(
        "BTC/USD",
        heartbeats=[(1700000000, "MD", 1, "Streaming")],
        logs=[
            ("1700000000.0", "jolteon", "ERROR", "f.py", "1", "one"),
            ("1700000001.0", "jolteon", "CRITICAL", "f.py", "2", "two"),
        ],
    )

    at = _page(engines).run()

    assert not at.exception
    metrics = _metrics(at)
    assert metrics["Components down"] == ":red[1]"
    assert metrics["Recorded errors"] == ":red[2]"
