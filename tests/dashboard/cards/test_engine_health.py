import re
import time

from streamlit.testing.v1 import AppTest

from jolteon.dashboard.cards import engine_health


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
    assert at.caption[0].value == "No heartbeats recorded yet."


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


INTERVAL = engine_health.HEARTBEAT_INTERVAL_SECONDS
BUCKETS = engine_health.HISTORY_BUCKETS


def _beating(intervals, sender: str = "MarketMaking"):
    """One heartbeat in each of the intervals named, counted back from the
    one ending now, a moment after each interval started - so the card's
    own slightly later clock still finds each in the interval it was
    sent in. Recorded oldest first, as an engine records them: the
    service takes the last row written for a sender as its latest."""
    return [
        _seen(intervals_ago * INTERVAL, sender)
        for intervals_ago in sorted(intervals, reverse=True)
    ]


def _histories(at) -> list[tuple[str, list[str]]]:
    """Every heartbeat history drawn, in tile order: its label and the
    kind of each bar, oldest first."""
    found = []
    for element in at.get("html"):
        for row in re.findall(
            r'<div class="jolteon-beats"[^>]*aria-label="([^"]*)">(.*?)</div>',
            element.body,
        ):
            label, bars = row
            found.append((label, re.findall(r"jolteon-beat-(\w+)", bars)))
    return found


def test_a_sender_heard_from_every_interval_reports_every_bar(engines):
    engines.add("BTC/USD", heartbeats=_beating(range(BUCKETS)))

    at = _page(engines).run()

    assert not at.exception
    assert "NORMAL" in _badges(at)
    [(label, bars)] = _histories(at)
    assert label == (
        f"Heartbeat history, last 5 minutes: {BUCKETS} of {BUCKETS} "
        "intervals reported"
    )
    assert bars == ["seen"] * BUCKETS


def test_a_missed_interval_is_hollow_where_it_was_missed(engines):
    """A component that has been flapping keeps a NORMAL badge, since its
    latest heartbeat is recent; the gaps show in the history instead, and
    the label says how many there were."""
    skipped = 5
    engines.add(
        "BTC/USD",
        heartbeats=_beating(n for n in range(BUCKETS) if n != skipped),
    )

    at = _page(engines).run()

    assert not at.exception
    assert "NORMAL" in _badges(at)
    [(label, bars)] = _histories(at)
    assert f"{BUCKETS - 1} of {BUCKETS} intervals reported" in label
    assert bars[BUCKETS - 1 - skipped] == "missed"
    assert bars.count("seen") == BUCKETS - 1


def test_the_silence_since_a_component_went_down_is_marked_as_such(
    engines,
):
    """Down for four intervals, having also missed one earlier: the
    trailing silence is the fault and takes the negative colour, the
    earlier gap stays an ordinary hollow bar."""
    quiet_for, flapped = 4, 10
    engines.add(
        "BTC/USD",
        heartbeats=_beating(
            n for n in range(quiet_for, BUCKETS) if n != flapped
        ),
    )

    at = _page(engines).run()

    assert not at.exception
    assert "DOWN" in _badges(at)
    [(label, bars)] = _histories(at)
    assert (
        f"{BUCKETS - quiet_for - 1} of {BUCKETS} intervals reported" in label
    )
    assert bars[-quiet_for:] == ["down"] * quiet_for
    assert bars[BUCKETS - 1 - flapped] == "missed"
    assert bars[: BUCKETS - quiet_for].count("down") == 0


def test_a_component_quiet_longer_than_the_history_is_down_throughout(
    engines,
):
    engines.add(
        "BTC/USD", heartbeats=[(1700000000, "MarketMaking", 1, "All good")]
    )

    at = _page(engines).run()

    assert not at.exception
    [(label, bars)] = _histories(at)
    assert f"0 of {BUCKETS} intervals reported" in label
    assert bars == ["down"] * BUCKETS


def test_every_component_gets_a_history_of_its_own(engines):
    engines.add(
        "BTC/USD",
        heartbeats=_beating(range(BUCKETS)) + _beating(range(1), sender="MD"),
    )

    at = _page(engines).run()

    assert not at.exception
    # Tiles are drawn in sender order, so MD's history comes first.
    [(market_data, _), (market_making, _)] = _histories(at)
    assert f"1 of {BUCKETS} intervals reported" in market_data
    assert f"{BUCKETS} of {BUCKETS} intervals reported" in market_making


def test_the_history_brings_its_own_stylesheet_in_tokens(engines):
    """The bars arrive with the rule that draws them, so a tile reaching
    the browser before a page-level stylesheet would still be drawn; and
    the rule names palette roles, never a colour by hand."""
    engines.add("BTC/USD", heartbeats=_beating(range(BUCKETS)))

    at = _page(engines).run()

    [sheet] = [
        element.body.split("</style>", 1)[0]
        for element in at.get("html")
        if "jolteon-beats" in element.body
    ]
    assert "var(--heartbeat-ok)" in sheet
    assert "var(--negative)" in sheet
    assert "var(--line)" in sheet
    assert not re.search(r"#[0-9a-fA-F]{3,8}\b", sheet)
