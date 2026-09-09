from datetime import datetime

import pandas as pd
import streamlit as st

from jolteon.app.components import style_table, warn_if_no_db
from jolteon.app.data import as_datetime, read_table

# Side badges in the theme's semantic green/red (config.toml), so BUY and
# SELL rows are scannable at a glance in the order and fill tables.
SIDE_OPTIONS = ["BUY", "SELL"]
SIDE_COLORS = ["#4E9F1F", "#E2574C"]

# The recorded tables grow without bound; only the tail is worth showing.
MAX_ROWS = 20

# Fill quantities are floats, so a position that has been fully closed out
# rarely lands exactly on zero.
POSITION_EPSILON = 1e-12


def _optional(df: pd.DataFrame, column: str) -> pd.Series | None:
    """A column if the recorded table has it, else None.

    SignalRecorder writes whatever fields the payload happened to carry, so
    an older database may be missing columns a newer payload has. A missing
    column drops out of the table instead of raising.
    """
    return df[column] if column in df.columns else None


def _local_time(seconds: pd.Series) -> pd.Series:
    """Epoch seconds rendered in the viewer's own timezone - the recorded
    columns are raw floats, which say nothing to a human reader."""
    local_tz = st.context.timezone or datetime.now().astimezone().tzinfo
    return as_datetime(seconds).dt.tz_convert(local_tz)


def _time_column(df: pd.DataFrame, preferred: str) -> str:
    """The payload's own time column if the table has it, else the time the
    recorder saw the event (every recorded table has `timestamp`)."""
    return preferred if preferred in df.columns else "timestamp"


def _recent(df: pd.DataFrame, time_column: str) -> pd.DataFrame:
    """The newest `MAX_ROWS` rows, newest first."""
    column = _time_column(df, time_column)
    return df.sort_values(column, ascending=False).head(MAX_ROWS)


def _readable(columns: dict[str, pd.Series | None]) -> pd.DataFrame:
    """A display frame with human-readable headers, skipping any column the
    recorded table didn't have."""
    return pd.DataFrame(
        {
            label: values
            for label, values in columns.items()
            if values is not None
        }
    )


def _notional(price: pd.Series | None, qty: pd.Series | None):
    return None if price is None or qty is None else price * qty


def orders_table(orders: pd.DataFrame) -> pd.DataFrame:
    """Recent orders, without the columns a human can't use: the recording
    `timestamp` (a near-duplicate of the creation time) stays out."""
    recent = _recent(orders, "creation_time")
    order_type = _optional(recent, "order_type")
    price = _optional(recent, "price")
    quantity = _optional(recent, "quantity")
    return _readable(
        {
            "Time": _local_time(
                recent.get("creation_time", recent.get("timestamp"))
            ),
            "Order": _optional(recent, "client_order_id"),
            "Side": _side_badges(recent),
            "Type": None if order_type is None else order_type.str.title(),
            "Symbol": _optional(recent, "symbol"),
            "Price": price,
            "Quantity": quantity,
            "Value": _notional(price, quantity),
        }
    )


def fills_table(fills: pd.DataFrame) -> pd.DataFrame:
    """Recent fills. The venue's maker/taker order ids are opaque UUIDs, so
    they're dropped in favour of the short trade and client order ids."""
    recent = _recent(fills, "transaction_time")
    price = _optional(recent, "price")
    quantity = _optional(recent, "quantity")
    trade_id = _optional(recent, "trade_id")
    return _readable(
        {
            "Time": _local_time(
                recent.get("transaction_time", recent.get("timestamp"))
            ),
            # As text, so the id reads as a label rather than a quantity.
            "Trade": None if trade_id is None else trade_id.astype(str),
            "Order": _optional(recent, "client_order_id"),
            "Side": _side_badges(recent),
            "Symbol": _optional(recent, "symbol"),
            "Price": price,
            "Quantity": quantity,
            "Value": _notional(price, quantity),
            "Fee": _optional(recent, "fee"),
        }
    )


def _side_badges(df: pd.DataFrame) -> pd.Series | None:
    """Sides wrapped as single-item lists, the shape MultiselectColumn needs
    to draw them as colored badges."""
    side = _optional(df, "side")
    return None if side is None else side.map(lambda value: [value])


def _column_config(time_help: str, order_help: str, **extra) -> dict:
    config = {
        "Time": st.column_config.DatetimeColumn(
            format="HH:mm:ss.SSS", help=time_help, width="small"
        ),
        "Order": st.column_config.TextColumn(help=order_help, width="small"),
        "Side": st.column_config.MultiselectColumn(
            options=SIDE_OPTIONS, color=SIDE_COLORS, width="small"
        ),
        "Price": st.column_config.NumberColumn(format="%,.2f"),
        "Quantity": st.column_config.NumberColumn(format="%.6f"),
        "Value": st.column_config.NumberColumn(
            format="%,.2f",
            help="What the trade is worth: price times quantity.",
        ),
    }
    config.update(extra)
    return config


def pnl_by_symbol(fills: pd.DataFrame, bbo: pd.DataFrame) -> pd.DataFrame:
    """Position, net cash flow and mark-to-market PnL per symbol.

    Net cash flow alone looks worse than reality while inventory is still
    held: the cash spent buying it shows up as an outflow with nothing
    offsetting it. Held inventory is marked at the latest mid price too, to
    match PositionManager.total_pnl in the engine.
    """
    signed_qty = fills["quantity"].where(
        fills["side"] == "BUY", -fills["quantity"]
    )
    cash_flow = (-fills["price"] * signed_qty) - fills["fee"]
    by_symbol = (
        pd.DataFrame(
            {
                "symbol": fills["symbol"],
                "position": signed_qty,
                "net_cash": cash_flow,
            }
        )
        .groupby("symbol")
        .sum()
    )

    if not bbo.empty:
        latest_mid = bbo.sort_values("timestamp").groupby("symbol").last()
        mark_price = (latest_mid["bid_price"] + latest_mid["ask_price"]) / 2
    else:
        mark_price = pd.Series(dtype=float)
    by_symbol["mark_price"] = by_symbol.index.map(mark_price)
    by_symbol["inventory_value"] = by_symbol["position"] * by_symbol[
        "mark_price"
    ].fillna(0)
    by_symbol["total_pnl"] = (
        by_symbol["net_cash"] + by_symbol["inventory_value"]
    )
    return by_symbol


def realized_pnl(fills: pd.DataFrame) -> float:
    """Profit on the round-trips that have actually closed, on an
    average-cost basis.

    Unlike net cash flow, acquiring inventory is not a loss here: a fill
    only contributes once it is traded back out again. Fees are charged as
    they are paid, so what is left over - total PnL minus this - is the
    unrealized gain sitting in open inventory.
    """
    total = 0.0
    ordered = fills.sort_values(_time_column(fills, "transaction_time"))
    for _, symbol_fills in ordered.groupby("symbol"):
        position, avg_cost = 0.0, 0.0
        for fill in symbol_fills.itertuples():
            signed = fill.quantity if fill.side == "BUY" else -fill.quantity
            total -= fill.fee

            opening = position == 0.0 or (position > 0) == (signed > 0)
            if opening:
                # Adding to the position: fold the fill into the average.
                size = abs(position) + abs(signed)
                avg_cost = (
                    abs(position) * avg_cost + abs(signed) * fill.price
                ) / size
                position += signed
                continue

            # Trading against the position realizes the difference between
            # the fill price and the average cost of what it closes out.
            closed = min(abs(signed), abs(position))
            direction = 1.0 if position > 0 else -1.0
            total += closed * (fill.price - avg_cost) * direction

            flipped = abs(signed) - closed > POSITION_EPSILON
            position += signed
            if flipped:
                # The remainder opens a new position the other way round.
                avg_cost = fill.price
            elif abs(position) <= POSITION_EPSILON:
                position, avg_cost = 0.0, 0.0
    return total


def _signed(value: float) -> str:
    """A PnL amount colored by sign, the way quotes are colored elsewhere."""
    color = "green" if value >= 0 else "red"
    return f":{color}[{value:,.2f}]"


def _render_pnl(fills: pd.DataFrame, bbo: pd.DataFrame) -> None:
    by_symbol = pnl_by_symbol(fills, bbo)

    with st.container(horizontal=True):
        st.metric(
            "Total PnL",
            _signed(by_symbol["total_pnl"].sum()),
            border=True,
            help="Everything made or lost so far, counting inventory "
            "still held at the current mid price.",
        )
        st.metric(
            "Realized PnL",
            _signed(realized_pnl(fills)),
            border=True,
            help="Profit on positions that have been closed out again, "
            "after fees. Inventory still held only counts once it is sold.",
        )
        st.metric(
            "Net cash flow",
            _signed(by_symbol["net_cash"].sum()),
            border=True,
            help="Cash taken in from sells minus cash paid out on buys, "
            "after fees. Buying inventory looks like a loss here until it "
            "is sold again.",
        )
        st.metric(
            "Inventory value",
            f"{by_symbol['inventory_value'].sum():,.2f}",
            border=True,
            help="What the inventory still held is worth at the current "
            "mid price.",
        )
        st.metric(
            "Fees paid",
            f"{fills['fee'].sum():,.2f}",
            border=True,
            help="Fees charged across all fills, already subtracted from "
            "realized PnL and net cash flow.",
        )
        for symbol, row in by_symbol.iterrows():
            st.metric(
                f"{symbol} position",
                f"{row['position']:g}",
                border=True,
                help="How much is held right now. A negative number means "
                "the position is short.",
            )
            mark = row["mark_price"]
            st.metric(
                f"{symbol} mark price",
                "-" if pd.isna(mark) else f"{mark:,.2f}",
                border=True,
                help="The current mid price, halfway between the best bid "
                "and the best ask.",
            )


def render() -> None:
    if not warn_if_no_db():
        return

    db_path = st.session_state.db_path
    orders = read_table(db_path, "order")
    fills = read_table(db_path, "order_fill")

    if fills.empty:
        st.info("No fills yet.")
    else:
        _render_pnl(fills, read_table(db_path, "ticker_feed"))

    st.divider()

    st.markdown("**Recent orders**")
    if orders.empty:
        st.info("No orders placed yet.")
    else:
        st.dataframe(
            style_table(orders_table(orders)),
            column_config=_column_config(
                time_help="When the order was sent, in your local time.",
                order_help="The id the strategy gave this order.",
                Type=st.column_config.TextColumn(
                    help="The kind of order that was sent, such as limit "
                    "or market.",
                    width="small",
                ),
            ),
            hide_index=True,
            width="stretch",
        )

    st.markdown("**Recent fills**")
    if fills.empty:
        st.info("No fills yet.")
    else:
        st.dataframe(
            style_table(fills_table(fills)),
            column_config=_column_config(
                time_help="When the trade was filled, in your local time.",
                order_help="The id of the order this trade filled.",
                Trade=st.column_config.TextColumn(
                    help="The id of this individual trade.", width="small"
                ),
                Fee=st.column_config.NumberColumn(format="%,.4f"),
            ),
            hide_index=True,
            width="stretch",
        )
