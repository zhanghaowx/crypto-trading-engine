"""
Live Streamlit dashboard for the Jolteon trading engine.

This is a read-only viewer: it never talks to the running engine directly.
Instead it polls the SQLite database that SignalRecorder (see
jolteon/core/event/signal_recorder.py) already writes every recorded signal
into, so it can run as a completely separate process from the engine itself.

Usage:
    streamlit run jolteon/app/dashboard.py -- --db /tmp/jolteon.sqlite

Note: live runs only flush to the database periodically (see
`enable_auto_save` in jolteon/app/kraken.py), so the dashboard lags behind
the engine by roughly that interval.
"""

import argparse
import sqlite3
import time
from pathlib import Path
from typing import Literal

import altair as alt
import pandas as pd
import streamlit as st

from jolteon.core.health_monitor.heartbeat import HeartbeatLevel

BadgeColor = Literal[
    "red",
    "orange",
    "yellow",
    "blue",
    "green",
    "violet",
    "gray",
    "grey",
    "primary",
]

HEARTBEAT_BADGES: dict[int, tuple[str, BadgeColor, str]] = {
    HeartbeatLevel.NORMAL.value: (
        "NORMAL",
        "green",
        ":material/check_circle:",
    ),
    HeartbeatLevel.WARN.value: ("WARN", "yellow", ":material/warning:"),
    HeartbeatLevel.ERROR.value: ("ERROR", "orange", ":material/error:"),
    HeartbeatLevel.CRITICAL.value: ("CRITICAL", "red", ":material/dangerous:"),
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--db", default="/tmp/jolteon.sqlite")
    # streamlit forwards its own args when not separated by "--"; ignore them.
    args, _ = parser.parse_known_args()
    return args


def init_settings() -> None:
    args = parse_args()
    st.session_state.setdefault("db_path", args.db)
    st.session_state.setdefault("auto_refresh", True)
    st.session_state.setdefault("refresh_seconds", 5)


def read_table(db_path: str, table: str) -> pd.DataFrame:
    if not Path(db_path).exists():
        return pd.DataFrame()
    try:
        with sqlite3.connect(db_path) as conn:
            return pd.read_sql(f'SELECT * FROM "{table}"', conn)
    except (sqlite3.OperationalError, pd.errors.DatabaseError):
        return pd.DataFrame()


def as_datetime(column: pd.Series) -> pd.Series:
    return pd.to_datetime(column, unit="s", utc=True)


def price_chart(candles: pd.DataFrame) -> alt.Chart:
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


def latest_quotes(orders: pd.DataFrame) -> pd.DataFrame:
    """The most recent order the strategy sent for each side, if any."""
    if orders.empty:
        return orders
    return orders.sort_values("timestamp").groupby("side").tail(1)


def quote_lines(quotes: pd.DataFrame) -> alt.Chart:
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


def card_grid(items, columns: int = 3):
    """
    Lay `items` out as a responsive grid of bordered cards, up to `columns`
    per row. Yields each item with its own bordered container already
    open, so the caller just renders content into it - handy for pages
    (risk limits, health) where the number of cards grows over time.
    """
    items = list(items)
    if not items:
        return
    cols_per_row = min(columns, len(items))
    for start in range(0, len(items), cols_per_row):
        row_items = items[start : start + cols_per_row]
        row_cols = st.columns(cols_per_row)
        for col, item in zip(row_cols, row_items):
            with col, st.container(border=True):
                yield item


def risk_limit_badge(utilization: float) -> tuple[str, BadgeColor, str]:
    if utilization >= 0.9:
        return "Near Limit", "red", ":material/error:"
    if utilization >= 0.7:
        return "Elevated", "orange", ":material/warning:"
    return "OK", "green", ":material/check_circle:"


def warn_if_no_db() -> bool:
    """Returns whether the configured database exists yet."""
    db_path = st.session_state.db_path
    if Path(db_path).exists():
        return True
    st.warning(
        f"No database found at `{db_path}` yet. "
        f"Waiting for the engine to start recording... "
        f"(check the Parameters tab if this looks wrong)"
    )
    return False


def page_market_data() -> None:
    st.title("Market Data")
    if not warn_if_no_db():
        return

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


def page_risk_limits() -> None:
    st.title("Risk Limits")
    if not warn_if_no_db():
        return

    risk = read_table(st.session_state.db_path, "risk_limit_snapshot")
    if risk.empty:
        st.info(
            "No risk limit data recorded yet "
            "(no strategy is live, or nothing has flushed to disk yet)."
        )
        return

    risk = risk.sort_values("timestamp")
    risk["time"] = as_datetime(risk["timestamp"])
    groups = list(risk.groupby(["name", "symbol"]))

    for (name, symbol), history in card_grid(groups, columns=3):
        latest = history.iloc[-1]
        maximum = latest["maximum"]
        utilization = (
            min(abs(latest["current"]) / maximum, 1.0) if maximum else 0.0
        )
        label, color, icon = risk_limit_badge(utilization)

        st.markdown(f"**{name.title()}**")
        st.caption(symbol)
        st.badge(label, color=color, icon=icon)
        st.progress(utilization)
        st.caption(
            f"{latest['current']:.4f} / ±{maximum:.4f} ({utilization:.0%})"
        )
        st.line_chart(history.set_index("time")[["current"]], height=120)


def page_orders_and_pnl() -> None:
    st.title("Orders & PnL")
    if not warn_if_no_db():
        return

    db_path = st.session_state.db_path
    orders = read_table(db_path, "order")
    fills = read_table(db_path, "order_fill")

    if fills.empty:
        st.info("No fills yet.")
    else:
        signed_qty = fills["quantity"].where(
            fills["side"] == "BUY", -fills["quantity"]
        )
        cash_flow = (-fills["price"] * signed_qty) - fills["fee"]
        by_symbol = (
            pd.DataFrame(
                {
                    "symbol": fills["symbol"],
                    "position": signed_qty,
                    "cash_pnl": cash_flow,
                }
            )
            .groupby("symbol")
            .sum()
        )

        # Cash PnL alone looks worse than reality while inventory is still
        # held: the cash spent buying it shows up as an outflow with
        # nothing offsetting it. Mark held inventory at the latest mid
        # price too, to match PositionManager.total_pnl in the engine.
        bbo = read_table(db_path, "ticker_feed")
        if not bbo.empty:
            latest_mid = bbo.sort_values("timestamp").groupby("symbol").last()
            mark_price = (
                latest_mid["bid_price"] + latest_mid["ask_price"]
            ) / 2
        else:
            mark_price = pd.Series(dtype=float)
        by_symbol["mark_price"] = by_symbol.index.map(mark_price)
        by_symbol["inventory_value"] = by_symbol["position"] * by_symbol[
            "mark_price"
        ].fillna(0)
        by_symbol["total_pnl"] = (
            by_symbol["cash_pnl"] + by_symbol["inventory_value"]
        )

        st.dataframe(
            by_symbol.rename(
                columns={
                    "position": "Position",
                    "cash_pnl": "Cash PnL",
                    "mark_price": "Mark Price",
                    "inventory_value": "Inventory Value",
                    "total_pnl": "Total PnL",
                }
            ),
            width="stretch",
        )

        cols = st.columns(2)
        cols[0].metric("Cash PnL", f"{by_symbol['cash_pnl'].sum():.2f}")
        cols[1].metric(
            "Total PnL (mark-to-market)",
            f"{by_symbol['total_pnl'].sum():.2f}",
        )
        st.caption(
            "Cash PnL is money in minus money out across all fills - it "
            "looks worse than reality while inventory is still held, "
            "since nothing offsets the cash spent buying it. Total PnL "
            "adds that inventory back at the latest mid price."
        )

    st.divider()

    col1, col2 = st.columns(2)
    with col1:
        st.caption("Recent orders")
        if orders.empty:
            st.info("No orders placed yet.")
        else:
            st.dataframe(
                orders.sort_values("timestamp", ascending=False).head(20),
                width="stretch",
            )
    with col2:
        st.caption("Recent fills")
        if fills.empty:
            st.info("No fills yet.")
        else:
            st.dataframe(
                fills.sort_values("timestamp", ascending=False).head(20),
                width="stretch",
            )


def page_health() -> None:
    st.title("Health")
    if not warn_if_no_db():
        return

    heartbeats = read_table(st.session_state.db_path, "heartbeat")
    if heartbeats.empty:
        st.info("No heartbeats recorded yet.")
        return

    latest = (
        heartbeats.sort_values("timestamp").groupby("sender").tail(1).copy()
    )
    latest["last_seen"] = as_datetime(latest["timestamp"])
    latest = latest.sort_values("sender")

    for row in card_grid(list(latest.itertuples()), columns=3):
        label, color, icon = HEARTBEAT_BADGES.get(
            row.level, ("UNKNOWN", "gray", ":material/help:")
        )
        st.markdown(f"**{row.sender}**")
        st.badge(label, color=color, icon=icon)
        if row.message:
            st.caption(row.message)
        st.caption(f"Last seen {row.last_seen:%H:%M:%S} UTC")


def page_parameters() -> None:
    st.title("Parameters")
    st.caption(
        "Settings for this dashboard viewer only — they do not "
        "affect the trading engine itself."
    )

    st.text_input("Database path", key="db_path")
    st.checkbox("Auto-refresh", key="auto_refresh")
    st.slider("Refresh every (s)", 1, 30, key="refresh_seconds")

    if not Path(st.session_state.db_path).exists():
        st.warning(f"No database found at `{st.session_state.db_path}` yet.")
    else:
        st.success(f"Reading from `{st.session_state.db_path}`.")


def main() -> None:
    st.set_page_config(page_title="Jolteon Live", layout="wide")
    init_settings()

    st.sidebar.title("Jolteon")
    pages = [
        st.Page(
            page_market_data,
            title="Market Data",
            icon=":material/candlestick_chart:",
            default=True,
        ),
        st.Page(
            page_risk_limits,
            title="Risk Limits",
            icon=":material/warning:",
        ),
        st.Page(
            page_orders_and_pnl,
            title="Orders & PnL",
            icon=":material/account_balance_wallet:",
        ),
        st.Page(
            page_health,
            title="Health",
            icon=":material/monitor_heart:",
        ),
        st.Page(
            page_parameters,
            title="Parameters",
            icon=":material/settings:",
        ),
    ]
    pg = st.navigation(pages)
    st.sidebar.caption(f"Checked at {pd.Timestamp.now(tz='UTC'):%H:%M:%S} UTC")

    pg.run()

    if st.session_state.auto_refresh:
        time.sleep(st.session_state.refresh_seconds)
        st.rerun()


main()
