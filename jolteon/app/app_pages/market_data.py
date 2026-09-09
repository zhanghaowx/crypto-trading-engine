import altair as alt
import streamlit as st

from jolteon.app.components import warn_if_no_db
from jolteon.app.data import as_datetime, latest_quotes, read_table


def price_chart(candles) -> alt.Chart:
    """
    Line chart of close price, scaled to the data's own range instead of
    always including zero - otherwise price moves that are tiny relative
    to the price level (e.g. BTC ticking by a few dollars) are invisible.
    """
    return (
        alt.Chart(candles)
        .mark_line()
        .encode(
            x=alt.X("time:T", title=None),
            y=alt.Y("close:Q", title="Close", scale=alt.Scale(zero=False)),
        )
    )


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
                    domain=["BUY", "SELL"], range=["#2ca02c", "#d62728"]
                ),
                legend=alt.Legend(title="Quote"),
            ),
        )
    )


st.title("Market Data")
if not warn_if_no_db():
    st.stop()

db_path = st.session_state.db_path
bbo = read_table(db_path, "ticker_feed")
candles = read_table(db_path, "calculated_candlestick_feed")
quotes = latest_quotes(read_table(db_path, "order"))

if bbo.empty:
    st.info("No market data recorded yet.")
else:
    latest = bbo.sort_values("timestamp").iloc[-1]
    mid = (latest["bid_price"] + latest["ask_price"]) / 2
    cols = st.columns(4)
    cols[0].metric("Symbol", latest.get("symbol", "-"))
    cols[1].metric("Bid", f"{latest['bid_price']:.2f}")
    cols[2].metric("Ask", f"{latest['ask_price']:.2f}")
    cols[3].metric("Mid", f"{mid:.2f}")

if not quotes.empty:
    quote_cols = st.columns(2)
    for col, side, label in (
        (quote_cols[0], "BUY", "Buy Quote"),
        (quote_cols[1], "SELL", "Sell Quote"),
    ):
        match = quotes[quotes["side"] == side]
        col.metric(
            label,
            f"{match.iloc[0]['price']:.2f}" if not match.empty else "—",
        )

if not candles.empty:
    candles = candles.drop_duplicates(
        subset="start_time", keep="last"
    ).sort_values("start_time")
    candles["time"] = as_datetime(candles["start_time"])
    chart = (
        alt.layer(price_chart(candles), quote_lines(quotes))
        if not quotes.empty
        else price_chart(candles)
    )
    st.altair_chart(chart, width="stretch")
    if not quotes.empty:
        st.caption(
            "Dashed lines mark the last quote sent per side. "
            "Cancellations aren't recorded, so a side that has since "
            "stopped quoting (e.g. inventory cap hit) may still show "
            "a stale line here."
        )
