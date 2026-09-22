from streamlit.testing.v1 import AppTest


def card_grid_script():
    import streamlit as st

    from jolteon.dashboard.ui.cards import card_grid

    for item in card_grid(["a", "b", "c"], key="demo-cards", columns=2):
        st.write(item)


def card_grid_empty_script():
    import streamlit as st

    from jolteon.dashboard.ui.cards import card_grid

    st.write(list(card_grid([], key="demo-cards", columns=2)))


def test_card_grid_renders_every_item_in_a_bordered_container():
    at = AppTest.from_function(card_grid_script).run()

    assert not at.exception
    assert [m.value for m in at.markdown] == ["a", "b", "c"]


def test_card_grid_yields_nothing_for_an_empty_list():
    at = AppTest.from_function(card_grid_empty_script).run()

    assert not at.exception
    assert at.json[0].value == "[]"


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


def test_two_half_cards_share_a_row_and_a_full_one_keeps_its_own():
    at = AppTest.from_function(half_cards_script).run()

    assert not at.exception
    # One row of two columns for the pair; the full card is not in it.
    assert len(at.columns) == 2
    assert [e.label for e in at.columns[0].expander] == [
        ":material/bar_chart: Order Book"
    ]
    assert [e.label for e in at.columns[1].expander] == [
        ":material/earthquake: Risk Limits"
    ]
    assert len(at.expander) == 3


def test_hiding_one_of_a_pair_promotes_the_next_card_beside_its_partner():
    """The pairing is done over the cards still showing, so closing one
    does not leave the row half empty with the next card below it."""
    at = AppTest.from_function(half_cards_script).run()

    at.button(key="card-order-book-hide").click().run()

    assert not at.exception
    # Risk Limits now has no half partner, so it takes a row alone.
    assert not at.columns
    assert [e.label for e in at.expander] == [
        ":material/earthquake: Risk Limits",
        ":material/paid: Orders & PnL",
    ]


def lone_half_card_script():
    import streamlit as st

    from jolteon.dashboard.ui.cards import Card, render_cards

    render_cards(
        [
            Card(
                "orders-pnl",
                "Orders & PnL",
                ":material/paid:",
                lambda: st.write("pnl"),
            ),
            Card(
                "risk-limits",
                "Risk Limits",
                ":material/earthquake:",
                lambda: st.write("risk"),
                width="half",
            ),
        ]
    )


def test_a_half_card_with_no_partner_left_still_gets_drawn():
    at = AppTest.from_function(lone_half_card_script).run()

    assert not at.exception
    assert [e.label for e in at.expander] == [
        ":material/paid: Orders & PnL",
        ":material/earthquake: Risk Limits",
    ]
    assert "risk" in [m.value for m in at.markdown]


def repeated_id_script():
    import streamlit as st

    from jolteon.dashboard.ui.cards import Card, render_cards

    render_cards(
        [
            Card("book", "Order Book", ":material/bar_chart:", lambda: None),
            Card("book", "Depth", ":material/bar_chart:", lambda: st.write()),
        ]
    )


def test_two_cards_may_not_answer_to_the_same_id():
    """Sharing an id means sharing a container key and a hidden flag, so
    hiding one would hide the other and Streamlit would refuse the second
    card's widgets as duplicates of the first's."""
    at = AppTest.from_function(repeated_id_script).run()

    assert at.exception
    assert "book" in at.exception[0].message
