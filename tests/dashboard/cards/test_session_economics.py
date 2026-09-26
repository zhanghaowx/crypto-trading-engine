import sqlite3
from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

from jolteon.dashboard.ui.primitives import MISSING

RUN = "20260920T120000Z-abc123"
OTHER_RUN = "20260920T110000Z-def456"
MODEL = "AdjustedFairPriceModel"
SYMBOL = "BTC-USD"


def _script():
    """The summary row and the card's own body, over the run the page
    picked, in the order the page draws them."""
    import streamlit as st

    from jolteon.dashboard.cards import session_economics

    model = session_economics.load(
        st.session_state.db_path, st.session_state.analysis_run_id
    )
    session_economics.render_summary(model)
    session_economics.render(model)


def _summary_script():
    import streamlit as st

    from jolteon.dashboard.cards import session_economics

    session_economics.render_summary(
        session_economics.load(
            st.session_state.db_path, st.session_state.analysis_run_id
        )
    )


def _details_script():
    """What the card's details modal shows: the same run, by side."""
    import streamlit as st

    from jolteon.dashboard.cards import session_economics

    session_economics.render_details(
        session_economics.load(
            st.session_state.db_path, st.session_state.analysis_run_id
        )
    )


def _recording(tmp_path, fills, marks=(), name="recording.sqlite") -> str:
    """A recording holding `fills` - each `(run_id, side, price, fee, qty,
    fair_at_fill, fair_at_1s)` - and the last book each run saw."""
    db_path = str(Path(tmp_path) / name)
    conn = sqlite3.connect(db_path)
    try:
        conn.execute(
            "CREATE TABLE decorated_order_fill "
            "(timestamp REAL, run_id TEXT, side TEXT, fill_price REAL, "
            "fee REAL, fill_qty REAL, inventory_before REAL, symbol TEXT, "
            "fair_price_model TEXT)"
        )
        conn.execute(
            "CREATE TABLE fair_price "
            "(timestamp REAL, symbol TEXT, model TEXT, "
            "bid_fair_price REAL, ask_fair_price REAL)"
        )
        conn.execute(
            "CREATE TABLE bbo_feed "
            "(timestamp REAL, run_id TEXT, symbol TEXT, bid_price REAL, "
            "ask_price REAL)"
        )
        for index, (run_id, side, price, fee, qty, fair, at_1s) in enumerate(
            fills
        ):
            # Spaced so no fill's observations can reach the next fill's.
            at = index * 100.0
            conn.execute(
                "INSERT INTO decorated_order_fill VALUES "
                "(?, ?, ?, ?, ?, ?, 0.0, ?, ?)",
                (at, run_id, side, price, fee, qty, SYMBOL, MODEL),
            )
            if fair is None:
                continue
            conn.executemany(
                "INSERT INTO fair_price VALUES (?, ?, ?, ?, ?)",
                [
                    (at, SYMBOL, MODEL, fair - 1.0, fair + 1.0),
                    (at + 1.0, SYMBOL, MODEL, at_1s - 1.0, at_1s + 1.0),
                ],
            )
        conn.executemany(
            "INSERT INTO bbo_feed VALUES (?, ?, ?, ?, ?)",
            [(1000.0, run_id, SYMBOL, bid, ask) for run_id, bid, ask in marks],
        )
        conn.commit()
    finally:
        conn.close()
    return db_path


@pytest.fixture
def flat_run(tmp_path) -> str:
    """A run that bought a unit and sold it back, so nothing is held."""
    return _recording(
        tmp_path,
        [
            (RUN, "BUY", 100.0, 0.1, 1.0, 101.0, 103.0),
            (RUN, "SELL", 110.0, 0.2, 1.0, 108.0, 105.0),
        ],
        marks=[(RUN, 109.0, 111.0)],
    )


def _run(path, run_id=RUN, script=_script):
    at = AppTest.from_function(script)
    at.session_state["db_path"] = path
    at.session_state["analysis_run_id"] = run_id
    return at.run()


def _metrics(at) -> dict[str, str]:
    return {m.label: m.value for m in at.metric}


def test_reports_the_run_in_quote_currency(flat_run, table_lookup):
    at = _run(flat_run)

    assert not at.exception
    metrics = _metrics(at)
    # Bought a unit at 100 and sold it at 110, paying 0.30 in fees.
    assert metrics["Marked PnL"] == ":green[+$9.70]"
    assert metrics["Notional"] == "$210.00"
    assert metrics["Fees"] == "$0.30"
    assert metrics["Fills"] == "2"

    rows = table_lookup(at, 0, "Horizon")
    # Edge at the fill: +1 on the buy, +2 on the sell, less 0.30 in fees.
    assert rows["At fill"]["Gross"] == "+$3.00"
    assert rows["At fill"]["Net"] == "+$2.70"
    # A second later: +3 on the buy, +5 on the sell.
    assert rows["+1s"]["Gross"] == "+$8.00"
    assert rows["+1s"]["Net"] == "+$7.70"
    # The market moved 5.00 our way over that second, on top of the edge.
    assert rows["+1s"]["Adverse selection"] == "+$5.00"


def test_reads_bps_against_the_notional_actually_measured(
    flat_run, table_lookup
):
    at = _run(flat_run)

    rows = table_lookup(at, 0, "Horizon")
    # 3.00 of edge on 210.00 of notional is 142.86 basis points.
    assert rows["At fill"]["Gross bps"] == "+142.86"
    assert rows["At fill"]["Net bps"] == "+128.57"
    assert rows["At fill"]["Measured"] == "100%"


def test_bps_columns_read_as_numbers_beside_the_dollars(flat_run, tables):
    """Basis points are already formatted, and are not in the dollars the
    table's own formatter speaks - but they are still numbers, and read
    wrongly left-aligned against the columns they sit next to."""
    at = _run(flat_run)

    body = at.get("html")[0].body
    assert '<td class="jolteon-num" style="">+142.86</td>' in body
    # Horizon is the only column read as a label.
    assert body.count('<th class="jolteon-num"') == 7


def test_says_nothing_of_a_run_with_no_fills(tmp_path):
    db_path = _recording(tmp_path, [])
    at = _run(db_path)

    assert not at.exception
    # Said once, by the card; the summary row above it draws nothing.
    assert [c.value for c in at.caption] == ["No fills in this run."]
    assert not at.metric


def test_the_summary_row_leaves_a_run_with_no_fills_to_the_card(tmp_path):
    db_path = _recording(tmp_path, [])
    at = _run(db_path, script=_summary_script)

    assert not at.exception
    assert not at.caption
    assert not at.metric


def test_will_not_mark_inventory_it_has_no_price_for(tmp_path):
    """A run still holding inventory with no recorded book to mark it
    against has no total to report - a net cash flow on its own reads as
    a loss the run did not make."""
    db_path = _recording(
        tmp_path, [(RUN, "BUY", 100.0, 0.1, 1.0, 101.0, 103.0)]
    )
    at = _run(db_path)

    assert not at.exception
    assert _metrics(at)["Marked PnL"] == MISSING


def test_marks_held_inventory_at_the_latest_mid(tmp_path):
    db_path = _recording(
        tmp_path,
        [(RUN, "BUY", 100.0, 0.1, 1.0, 101.0, 103.0)],
        marks=[(RUN, 104.0, 106.0)],
    )
    at = _run(db_path)

    # Paid 100.10 for a unit now worth 105.00.
    assert _metrics(at)["Marked PnL"] == ":green[+$4.90]"


def test_details_break_the_run_out_by_side(tmp_path, table_lookup):
    db_path = _recording(
        tmp_path,
        [
            (RUN, "BUY", 100.0, 0.0, 1.0, 101.0, 103.0),
            (RUN, "BUY", 100.0, 0.0, 1.0, 102.0, 103.0),
            (RUN, "SELL", 110.0, 0.0, 1.0, 108.0, 105.0),
        ],
        marks=[(RUN, 109.0, 111.0)],
    )
    at = _run(db_path, script=_details_script)

    assert not at.exception
    headings = [m.value for m in at.markdown]
    assert "**BUY · 2 fills · $200.00 notional**" in headings
    assert "**SELL · 1 fill · $110.00 notional**" in headings

    # Edges of +1 and +2 on the buys, and +2 on the one sell.
    assert table_lookup(at, 0, "Horizon")["At fill"]["Gross"] == "+$3.00"
    assert table_lookup(at, 1, "Horizon")["At fill"]["Gross"] == "+$2.00"


def test_details_say_nothing_of_a_run_with_no_fills(tmp_path):
    db_path = _recording(tmp_path, [])
    at = _run(db_path, script=_details_script)

    assert [c.value for c in at.caption] == ["No fills in this run."]


def test_a_run_measures_only_its_own_fills(tmp_path, tables):
    db_path = _recording(
        tmp_path,
        [
            (OTHER_RUN, "BUY", 50.0, 1.0, 2.0, 60.0, 70.0),
            (RUN, "BUY", 100.0, 0.1, 1.0, 101.0, 103.0),
        ],
        marks=[(RUN, 104.0, 106.0)],
    )
    at = _run(db_path, run_id=RUN)

    assert _metrics(at)["Notional"] == "$100.00"
    assert _metrics(at)["Fills"] == "1"


def test_details_leave_out_a_side_the_run_never_traded(tmp_path, tables):
    db_path = _recording(
        tmp_path,
        [(RUN, "BUY", 100.0, 0.1, 1.0, 101.0, 103.0)],
        marks=[(RUN, 104.0, 106.0)],
    )
    at = _run(db_path, script=_details_script)

    assert not at.exception
    assert [m.value for m in at.markdown] == [
        "**BUY · 1 fill · $100.00 notional**"
    ]
    assert len(tables(at)) == 1


def test_a_loss_is_signed_before_the_currency(tmp_path):
    """`$-10.30` reads as a strange currency; the sign belongs in front."""
    db_path = _recording(
        tmp_path,
        [
            (RUN, "BUY", 110.0, 0.1, 1.0, 109.0, 108.0),
            (RUN, "SELL", 100.0, 0.2, 1.0, 101.0, 102.0),
        ],
        marks=[(RUN, 99.0, 101.0)],
    )
    at = _run(db_path)

    assert _metrics(at)["Marked PnL"] == ":red[-$10.30]"


def test_says_how_much_of_the_run_a_row_rests_on(tmp_path, table_lookup):
    """A fill with no fair price near enough to measure it against is left
    out of every figure on the row, so the row has to say how much of the
    run it is actually speaking for."""
    db_path = _recording(
        tmp_path,
        [
            (RUN, "BUY", 100.0, 0.0, 1.0, 101.0, 103.0),
            # Nine times the notional, and nothing recorded to measure it.
            (RUN, "SELL", 900.0, 0.0, 1.0, None, None),
        ],
        marks=[(RUN, 899.0, 901.0)],
    )
    at = _run(db_path)

    assert _metrics(at)["Notional"] == "$1,000.00"
    rows = table_lookup(at, 0, "Horizon")
    # 100.00 of the run's 1,000.00 of notional could be measured at all.
    assert rows["At fill"]["Measured"] == "10%"
    assert rows["At fill"]["Gross"] == "+$1.00"
    # Read against the whole run that edge would look ten times smaller.
    assert rows["At fill"]["Gross bps"] == "+100.00"


def test_a_rows_fees_are_the_fees_of_the_fills_it_measured(
    tmp_path, table_lookup
):
    """The card's Fees figure is the whole run's. A row that could measure
    only some of the run has to carry its own, or gross less fees would
    not come to the net beside it."""
    db_path = _recording(
        tmp_path,
        [
            (RUN, "BUY", 100.0, 0.10, 1.0, 101.0, 103.0),
            # Nothing recorded to measure this one against, fee and all.
            (RUN, "SELL", 900.0, 0.50, 1.0, None, None),
        ],
        marks=[(RUN, 899.0, 901.0)],
    )
    at = _run(db_path)

    assert _metrics(at)["Fees"] == "$0.60"
    rows = table_lookup(at, 0, "Horizon")
    assert rows["At fill"]["Measured"] == "10%"
    assert rows["At fill"]["Fees"] == "$0.10"
    # +$1.00 of edge, less the $0.10 that edge actually paid for.
    assert rows["At fill"]["Gross"] == "+$1.00"
    assert rows["At fill"]["Net"] == "+$0.90"
