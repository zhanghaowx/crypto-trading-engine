import altair as alt
import streamlit as st

from jolteon.app.components import animated_metric, style_chart, warn_if_no_db
from jolteon.app.data import (
    as_datetime,
    read_latest_per_group,
    read_latest_row,
    read_table,
)

_QUOTE_HELP = (
    "Dashed lines on the chart mark the last quote sent per side. "
    "Cancellations aren't reflected here, so a side that has since "
    "stopped quoting (e.g. inventory cap hit) may still show a stale "
    "line here."
)


def price_chart(ticks) -> alt.Chart:
    """
    Line chart of mid price, scaled to the data's own range instead of
    always including zero - otherwise price moves that are tiny relative
    to the price level (e.g. BTC ticking by a few dollars) are invisible.
    """
    return (
        alt.Chart(ticks)
        .mark_line()
        .encode(
            x=alt.X("time:T", title=None),
            y=alt.Y("mid:Q", title="Mid Price", scale=alt.Scale(zero=False)),
        )
    )


_QUOTE_LINE_COLORS = {"BUY": "#4E9F1F", "SELL": "#E2574C"}


def quote_lines(quotes) -> alt.Chart:
    """
    Dashed reference lines marking the last known quote per side, layered
    on top of the price chart.
    """
    return (
        alt.Chart(quotes)
        .mark_rule(strokeDash=[6, 4], size=2)
        .encode(
            y="price:Q",
            color=alt.Color(
                "side:N",
                scale=alt.Scale(
                    domain=list(_QUOTE_LINE_COLORS),
                    range=list(_QUOTE_LINE_COLORS.values()),
                ),
                legend=alt.Legend(title="Quote"),
            ),
        )
    )


def _quote_metric(col, quotes, side: str, label: str) -> None:
    match = quotes[quotes["side"] == side]
    with col:
        if match.empty:
            st.metric(label, "—", help=_QUOTE_HELP)
        else:
            animated_metric(
                f"quote-{side}",
                label,
                float(match.iloc[0]["price"]),
                color=_QUOTE_LINE_COLORS[side],
                help=_QUOTE_HELP,
            )


def render() -> None:
    if not warn_if_no_db():
        return

    db_path = st.session_state.db_path
    bbo = read_latest_row(db_path, "ticker_feed")
    ticks = read_table(db_path, "ticker_feed")
    quotes = read_latest_per_group(db_path, "order", "side")

    if bbo is None:
        st.info("No market data recorded yet.")
        if not quotes.empty:
            quote_cols = st.columns(2)
            _quote_metric(quote_cols[0], quotes, "BUY", "Buy Quote")
            _quote_metric(quote_cols[1], quotes, "SELL", "Sell Quote")
    else:
        mid = (bbo["bid_price"] + bbo["ask_price"]) / 2
        cols = st.columns(4)
        with cols[0]:
            st.metric("Symbol", bbo.get("symbol", "-"))
        with cols[1]:
            animated_metric("bid", "Bid", float(bbo["bid_price"]))
        with cols[2]:
            animated_metric("ask", "Ask", float(bbo["ask_price"]))
        with cols[3]:
            animated_metric("mid", "Mid", float(mid))
        if not quotes.empty:
            _quote_metric(cols[1], quotes, "BUY", "Buy Quote")
            _quote_metric(cols[2], quotes, "SELL", "Sell Quote")

    if not ticks.empty:
        ticks = ticks.sort_values("timestamp")
        window_seconds = st.session_state.chart_window_minutes * 60
        cutoff = ticks["timestamp"].max() - window_seconds
        ticks = ticks[ticks["timestamp"] >= cutoff]
        ticks["time"] = as_datetime(ticks["timestamp"])
        ticks["mid"] = (ticks["bid_price"] + ticks["ask_price"]) / 2
        chart = (
            alt.layer(price_chart(ticks), quote_lines(quotes))
            if not quotes.empty
            else price_chart(ticks)
        )
        st.altair_chart(style_chart(chart), width="stretch")
