from streamlit.testing.v1 import AppTest


def cards_script():
    import streamlit as st

    from jolteon.dashboard.ui.cards import Card, render_cards

    render_cards(
        [
            Card(
                "market-data",
                "Market Data",
                ":material/show_chart:",
                lambda: st.write("md"),
                details=lambda: st.write("every tick"),
            ),
            Card(
                "orders-pnl",
                "Orders & PnL",
                ":material/currency_bitcoin:",
                lambda: st.write("pnl"),
                actions=lambda: st.button("Download"),
            ),
        ]
    )


def detailed_card_script():
    import streamlit as st

    from jolteon.dashboard.ui.cards import Card, render_cards

    render_cards(
        [
            Card(
                "market-data",
                "Market Data",
                ":material/show_chart:",
                lambda: st.write("md"),
                details=lambda: st.write("every tick"),
            )
        ]
    )


def test_every_card_renders_under_its_own_title():
    at = AppTest.from_function(cards_script).run()

    assert not at.exception
    assert [e.label for e in at.expander] == [
        ":material/show_chart: Market Data",
        ":material/currency_bitcoin: Orders & PnL",
    ]
    assert [m.value for m in at.markdown if m.value in ("md", "pnl")] == [
        "md",
        "pnl",
    ]


def test_a_cards_own_action_renders_beside_its_title():
    at = AppTest.from_function(cards_script).run()

    assert [b.label for b in at.button if b.label] == ["Download"]


def test_every_card_carries_its_own_chrome():
    at = AppTest.from_function(cards_script).run()

    keys = [b.key for b in at.button]
    for title in ("card-market-data", "card-orders-pnl"):
        assert f"{title}-hide" in keys
    # Only the card with something more to show carries the "more" icon.
    assert "card-market-data-details" in keys
    assert "card-orders-pnl-details" not in keys


def test_collapsing_is_the_expanders_own_doing():
    """
    A card folds in the browser, which is what keeps expanding one off
    the server entirely - no rerun, no re-read of the recording, no
    chart redrawn.

    There is no collapse button of ours, and the expander reports no
    open/closed state back: with `on_change="ignore"` a reader's toggle
    never reaches Python at all, which is why the card's content is
    always rendered rather than left out while it is closed.
    """
    at = AppTest.from_function(cards_script).run()

    assert not [b for b in at.button if (b.key or "").endswith("-collapse")]
    assert all(e.proto.expanded for e in at.expander)
    assert not hasattr(at.expander[0], "open")


def test_the_details_icon_opens_the_card_in_a_modal():
    at = AppTest.from_function(cards_script).run()

    assert not at.get("dialog")

    at.button(key="card-market-data-details").click().run()

    assert not at.exception
    assert at.get("dialog")
    # What the modal shows is the card's details, and the card's own
    # content steps aside while it is open.
    assert "every tick" in [m.value for m in at.markdown]
    assert "md" not in [m.value for m in at.markdown]


def test_the_modal_stays_open_across_a_refresh():
    """The pages cards render on rerun on a timer. A modal opened straight
    from the button's return value would close again on the first refresh
    after it was opened."""
    at = AppTest.from_function(cards_script).run()

    at.button(key="card-market-data-details").click().run()
    at.run()

    assert not at.exception
    assert at.get("dialog")


def test_a_card_with_details_shows_those_instead_of_its_content():
    at = AppTest.from_function(detailed_card_script).run()

    at.button(key="card-market-data-details").click().run()

    assert not at.exception
    values = [m.value for m in at.markdown]
    assert "every tick" in values
    assert "md" not in values


def test_the_close_icon_hides_a_card_and_offers_it_back():
    at = AppTest.from_function(cards_script).run()

    at.button(key="card-market-data-hide").click().run()

    assert not at.exception
    assert [e.label for e in at.expander] == [
        ":material/currency_bitcoin: Orders & PnL"
    ]
    assert at.button(key="card-unhide").label == "Show Market Data"

    at.button(key="card-unhide").click().run()

    assert len(at.expander) == 2


def test_a_hidden_card_stays_hidden_across_a_refresh():
    at = AppTest.from_function(cards_script).run()

    at.button(key="card-market-data-hide").click().run()
    at.run()

    assert not at.exception
    assert [e.label for e in at.expander] == [
        ":material/currency_bitcoin: Orders & PnL"
    ]


def test_nothing_is_offered_back_while_every_card_is_showing():
    at = AppTest.from_function(cards_script).run()

    assert not at.exception
    assert "card-unhide" not in [b.key for b in at.button]


def test_hiding_a_card_closes_the_modal_it_had_open():
    """Nothing draws a hidden card, so a modal left open on one could
    never be dismissed - its card is no longer there to render it."""
    at = AppTest.from_function(cards_script).run()

    at.button(key="card-market-data-details").click().run()
    at.button(key="card-market-data-hide").click().run()

    assert not at.exception
    assert not at.get("dialog")


def accented_cards_script():
    import streamlit as st

    from jolteon.dashboard.ui.cards import Card, render_cards

    render_cards(
        [
            Card(
                "market-data",
                "Market Data",
                ":material/show_chart:",
                lambda: st.write("md"),
                accent="blue",
            ),
            Card(
                "risk-limits",
                "Risk Limits",
                ":material/earthquake:",
                lambda: st.write("risk"),
                accent=lambda: st.session_state.get("risk_accent"),
            ),
        ]
    )


def keyed_card_script():
    import streamlit as st

    from jolteon.dashboard.ui.cards import Card, render_cards

    def refresh() -> None:
        st.button("Refresh", key="market-data-refresh")

    render_cards(
        [
            Card(
                "market-data",
                "Market Data",
                ":material/show_chart:",
                refresh,
                details=refresh,
            )
        ]
    )


def test_a_card_whose_details_key_what_its_content_does_still_opens():
    """Regression test: a card's content steps aside while its details
    are open, so details built from the same renderers - keying the same
    widgets - are not asked for those keys twice in one run, which
    Streamlit refuses."""
    at = AppTest.from_function(keyed_card_script).run()

    at.button(key="card-market-data-details").click().run()

    assert not at.exception
    assert at.get("dialog")
    assert len([b for b in at.button if b.key == "market-data-refresh"]) == 1


def half_cards_script():
    import streamlit as st

    from jolteon.dashboard.ui.cards import Card, render_cards

    render_cards(
        [
            Card(
                "order-book",
                "Order Book",
                ":material/bar_chart:",
                lambda: st.write("book"),
                width="half",
            ),
            Card(
                "risk-limits",
                "Risk Limits",
                ":material/earthquake:",
                lambda: st.write("risk"),
                width="half",
            ),
            Card(
                "orders-pnl",
                "Orders & PnL",
                ":material/paid:",
                lambda: st.write("pnl"),
            ),
        ]
    )


def test_a_card_with_nothing_more_to_show_carries_no_more_icon():
    at = AppTest.from_function(half_cards_script).run()

    assert not at.exception
    assert not [b for b in at.button if (b.key or "").endswith("-details")]


def test_a_cards_accent_reaches_the_page():
    at = AppTest.from_function(accented_cards_script).run()

    assert not at.exception
    rules = [h.body for h in at.get("html")]
    assert any(
        ".st-key-card-market-data {" in rule and "#3E8FD0" in rule
        for rule in rules
    )


def test_an_accent_given_as_a_function_follows_what_it_reports_on():
    at = AppTest.from_function(accented_cards_script)
    at.session_state["risk_accent"] = "green"
    at.run()

    assert "#16A34A" in " ".join(h.body for h in at.get("html"))

    at.session_state["risk_accent"] = "red"
    at.run()

    assert "#DC2626" in " ".join(h.body for h in at.get("html"))


def test_a_card_without_an_accent_emits_no_rule_for_one():
    at = AppTest.from_function(accented_cards_script).run()

    assert not at.exception
    assert not any(
        ".st-key-card-risk-limits {" in h.body for h in at.get("html")
    )


def renamed_card_script():
    import streamlit as st

    from jolteon.dashboard.ui.cards import Card, render_cards

    render_cards(
        [
            Card(
                "market-data",
                st.session_state.get("title", "Market Data"),
                ":material/show_chart:",
                lambda: st.write("md"),
            )
        ]
    )


def test_a_card_renamed_keeps_the_identity_its_state_is_held_under():
    """A title is what the card is called on the page. Hiding it, and
    every other choice a reader makes about a card, is held under the
    card's own id, so rewording the title does not lose them."""
    at = AppTest.from_function(renamed_card_script).run()

    at.button(key="card-market-data-hide").click().run()
    assert not at.expander

    at.session_state["title"] = "Market Prices"
    at.run()

    assert not at.exception
    assert not at.expander
    assert at.button(key="card-unhide").label == "Show Market Prices"


def isolated_cards_script():
    """Two cards, with what Streamlit is handed for each one captured
    rather than run, so a test can run one card's fragment on its own -
    which is all a card's own timer does when it fires."""
    from unittest import mock

    import streamlit as st

    from jolteon.dashboard.ui.cards import Card, render_cards

    ran = st.session_state.setdefault("ran", [])
    fragments = st.session_state.setdefault("fragments", {})
    st.session_state["passes"] = st.session_state.get("passes", 0) + 1

    def note(name):
        return lambda: ran.append(name)

    def capture(func, *, run_every=None, key=None):
        fragments[key] = (func, run_every)
        return lambda: None

    cards = [
        Card(
            "order-book",
            "Order Book",
            ":material/bar_chart:",
            note("order-book body"),
            actions=note("order-book actions"),
            accent=note("order-book accent"),
        ),
        Card(
            "risk-limits",
            "Risk Limits",
            ":material/earthquake:",
            note("risk-limits body"),
            actions=note("risk-limits actions"),
            accent=note("risk-limits accent"),
            refresh_interval=60,
        ),
    ]
    with mock.patch.object(st, "fragment", capture):
        render_cards(cards)

    # Popped, not read: a fragment that asks for the page to run again
    # would otherwise be run again by that pass too, and so on forever.
    if target := st.session_state.pop("refresh", None):
        fragments[target][0]()


def _isolated(**session_state) -> AppTest:
    at = AppTest.from_function(isolated_cards_script)
    at.session_state["auto_refresh"] = True
    at.session_state["refresh_seconds"] = 5
    for key, value in session_state.items():
        at.session_state[key] = value
    return at


def test_every_card_is_handed_to_streamlit_as_a_fragment_of_its_own():
    at = _isolated().run()

    assert not at.exception
    assert sorted(at.session_state["fragments"]) == [
        "order-book",
        "risk-limits",
    ]


def test_refreshing_one_card_runs_that_card_and_nothing_else():
    """The whole point of a fragment per card: when Order Book's timer
    fires, Risk Limits does not read the recording again, redraw a gauge
    or rebuild its own chrome."""
    at = _isolated().run()
    at.session_state["ran"].clear()
    at.session_state["refresh"] = "order-book"
    at.run()

    assert not at.exception
    assert at.session_state["ran"] == [
        "order-book accent",
        "order-book body",
        "order-book actions",
    ]


def test_hiding_a_card_from_inside_it_asks_the_page_to_run_again():
    """A card hides itself from inside its own fragment, which redraws
    nothing but itself - so the card would still be sitting there, and
    its neighbour would still be waiting for a partner that had gone."""
    at = _isolated().run()
    at.session_state["ran"].clear()
    at.session_state["_card_hidden"] = {"card-order-book"}
    at.session_state["refresh"] = "order-book"
    passes = at.session_state["passes"]
    at.run()

    assert not at.exception
    assert at.session_state["passes"] == passes + 2
    assert at.session_state["ran"] == []


def test_a_card_refreshes_on_the_dashboard_interval_by_default():
    at = _isolated().run()

    assert at.session_state["fragments"]["order-book"][1] == 5


def test_a_card_may_ask_for_an_interval_of_its_own():
    at = _isolated().run()

    assert at.session_state["fragments"]["risk-limits"][1] == 60


def test_no_card_refreshes_while_the_reader_has_refreshing_switched_off():
    at = _isolated(auto_refresh=False).run()

    intervals = [every for _, every in at.session_state["fragments"].values()]
    assert intervals == [None, None]


def test_a_card_that_declines_to_refresh_gets_no_timer():
    from jolteon.dashboard.ui.cards import Card, refresh_every

    assert (
        refresh_every(Card("a", "A", "", lambda: None, refresh=False)) is None
    )


def test_manual_refresh_can_be_omitted():
    def script():
        import streamlit as st

        from jolteon.dashboard.ui.cards import Card, render_cards

        render_cards(
            [Card("a", "A", "", lambda: st.write("A"), manual_refresh=False)]
        )

    at = AppTest.from_function(script).run()
    assert not at.exception
    assert "card-a-refresh" not in [button.key for button in at.button]
