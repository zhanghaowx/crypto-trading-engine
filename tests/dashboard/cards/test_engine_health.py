import time

from streamlit.testing.v1 import AppTest


def _seen(seconds_ago: float = 0, sender: str = "MarketMaking"):
    """One heartbeat, sent `seconds_ago` and not since."""
    return (time.time() - seconds_ago, sender, 1, "All good")


def _script():
    from jolteon.dashboard.cards import engine_health

    engine_health.render()


def _page(engines) -> AppTest:
    at = AppTest.from_function(_script)
    at.session_state["root"] = engines.root
    return at


def _badges(at) -> str:
    return " ".join(m.value for m in at.markdown if "-badge[" in m.value)


def test_warns_when_no_engine_has_recorded_anything(engines):
    at = _page(engines).run()

    assert not at.exception
    assert engines.root in at.warning[0].value


def test_says_so_while_an_engine_has_not_heartbeat_yet(engines):
    """
    An engine that has only just started has nothing to show, and saying
    so is what keeps it from reading as one that never started.
    """
    engines.add("BTC/USD")

    at = _page(engines).run()

    assert not at.exception
    assert at.info[0].value == "No heartbeats recorded yet."


def test_renders_a_badge_per_sender(engines):
    engines.add("BTC/USD", heartbeats=[_seen()])

    at = _page(engines).run()

    assert not at.exception
    assert at.markdown[0].value == "**MarketMaking**"
    assert "NORMAL" in _badges(at)
    assert at.caption[0].value.startswith("All good · Last seen ")


def test_one_engine_alone_is_not_labelled_with_its_symbol(engines):
    """With nothing to tell apart, the symbol is noise above the tiles."""
    engines.add("BTC/USD", heartbeats=[_seen()])

    at = _page(engines).run()

    assert "**BTC/USD**" not in [m.value for m in at.markdown]


def test_every_engine_is_watched_at_once(engines):
    engines.add("BTC/USD", heartbeats=[_seen()])
    engines.add("ETH/USD", heartbeats=[_seen(sender="MD")])

    at = _page(engines).run()

    assert not at.exception
    headings = [m.value for m in at.markdown]
    assert "**Kraken · BTC/USD**" in headings
    assert "**Kraken · ETH/USD**" in headings
    assert "**MarketMaking**" in headings
    assert "**MD**" in headings


def test_two_engines_components_do_not_share_a_tile(engines):
    """
    Senders are named for the job they do, so every engine has a
    `MarketMaking`. Keyed by sender alone, the second engine's tile would
    reuse the first's and only one of the two would ever be drawn.
    """
    engines.add("BTC/USD", heartbeats=[_seen()])
    engines.add("ETH/USD", heartbeats=[_seen()])

    at = _page(engines).run()

    assert not at.exception
    assert len([m for m in at.markdown if m.value == "**MarketMaking**"]) == 2


def test_describes_a_short_silence_in_seconds(engines):
    """Down for 45 seconds: too short to round to a minute, so the age
    should be reported in seconds rather than "0 minutes"."""
    engines.add("BTC/USD", heartbeats=[_seen(45)])

    at = _page(engines).run()

    assert not at.exception
    assert "DOWN" in _badges(at)
    assert "No heartbeat for" in at.caption[0].value
    assert "seconds" in at.caption[0].value
    assert "minutes" not in at.caption[0].value


def test_reports_a_silent_sender_as_down(engines):
    """The recorded level is NORMAL, but the heartbeat is years old: a
    component that dies leaves its last cheerful row behind, so silence has
    to outrank what that row says."""
    engines.add(
        "BTC/USD", heartbeats=[(1700000000, "MarketMaking", 1, "All good")]
    )

    at = _page(engines).run()

    assert not at.exception
    assert "DOWN" in _badges(at)
    assert "No heartbeat for" in at.caption[0].value
