from datetime import datetime

import pandas as pd
import streamlit as st

from jolteon.app.components import (
    BadgeColor,
    animated_metric,
    paginate,
    row_add_rule,
    row_key,
    warn_if_no_db,
)
from jolteon.app.data import as_datetime, read_latest_per_group, read_table

# The recorded tables grow without bound; fills are paginated rather than
# read in full onto the page.
PAGE_SIZE = 10

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


def _newest_first(df: pd.DataFrame, time_column: str) -> pd.DataFrame:
    """Every row of `df`, newest first."""
    column = _time_column(df, time_column)
    return df.sort_values(column, ascending=False)


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


def fills_table(fills: pd.DataFrame) -> pd.DataFrame:
    """Every fill, newest first. The venue's maker/taker order ids are
    opaque UUIDs, so they're dropped in favour of the short trade and
    client order ids."""
    ordered = _newest_first(fills, "transaction_timestamp")
    price = _optional(ordered, "fill_price")
    quantity = _optional(ordered, "fill_qty")
    trade_id = _optional(ordered, "trade_id")
    return _readable(
        {
            "Time": _local_time(
                ordered.get("transaction_timestamp", ordered.get("timestamp"))
            ),
            # As text, so the id reads as a label rather than a quantity.
            "Trade": None if trade_id is None else trade_id.astype(str),
            "Order": _optional(ordered, "client_order_id"),
            "Side": _optional(ordered, "side"),
            "Symbol": _optional(ordered, "symbol"),
            "Price": price,
            "Fair Price": _optional(ordered, "fair_price_at_fill"),
            "Quantity": quantity,
            "Value": _notional(price, quantity),
            "Fee": _optional(ordered, "fee"),
            "Inventory Before": _optional(ordered, "inventory_before"),
            "Inventory After": _optional(ordered, "inventory_after"),
            "Fair Price +100ms": _optional(ordered, "fair_price_100ms"),
            "Fair Price +1s": _optional(ordered, "fair_price_1s"),
            "Fair Price +5s": _optional(ordered, "fair_price_5s"),
            "Fair Price +30s": _optional(ordered, "fair_price_30s"),
        }
    )


# (label, relative column width) - the widths roughly mirror the "small"
# columns (Time/Trade/Order/Side) the table's old column_config used.
_FILL_COLUMNS: list[tuple[str, float]] = [
    ("Time", 1.3),
    ("Trade", 0.9),
    ("Order", 0.9),
    ("Side", 0.8),
    ("Symbol", 1.0),
    ("Price", 1.0),
    ("Fair Price", 1.0),
    ("Quantity", 1.1),
    ("Value", 1.0),
    ("Fee", 0.9),
    ("Inventory Before", 1.2),
    ("Inventory After", 1.2),
    ("Fair Price +100ms", 1.3),
    ("Fair Price +1s", 1.2),
    ("Fair Price +5s", 1.2),
    ("Fair Price +30s", 1.3),
]

# Side badges in the theme's semantic green/red (config.toml), so BUY and
# SELL rows are scannable at a glance in the fills list.
_SIDE_BADGE_COLORS: dict[str, BadgeColor] = {"BUY": "green", "SELL": "red"}

_FILL_ROW_CSS = """
[class*="st-key-row-fill-"] {
  border-bottom: 1px solid #D7D7D3;
  padding: 6px 0;
}
"""


def _fill_identity(row: pd.Series) -> str:
    """A fill's own stable identity - not its position in the recent
    list, which shifts as newer fills arrive and push it down - so an
    unchanged row keeps its key, and its animation, across reruns."""
    trade = row.get("Trade")
    if trade:
        return str(trade)
    return (
        f"{row.get('Time')}-{row.get('Symbol')}-"
        f"{row.get('Price')}-{row.get('Quantity')}"
    )


_FAIR_PRICE_LABELS = {
    "Fair Price",
    "Fair Price +100ms",
    "Fair Price +1s",
    "Fair Price +5s",
    "Fair Price +30s",
}


def _render_fill_cell(col, label: str, value) -> None:
    with col:
        if label == "Side":
            st.badge(value, color=_SIDE_BADGE_COLORS.get(value, "gray"))
        elif label == "Time":
            st.write(value.strftime("%H:%M:%S.%f")[:-3])
        elif label in _FAIR_PRICE_LABELS:
            # Horizons not yet reached still carry NULL in the DB.
            st.write("-" if pd.isna(value) else f"{value:,.2f}")
        elif label in ("Price", "Value"):
            st.write(f"{value:,.2f}")
        elif label in ("Quantity", "Inventory Before", "Inventory After"):
            st.write(f"{value:.6f}")
        elif label == "Fee":
            st.write(f"{value:,.4f}")
        else:
            st.write(value)


def render_fills_list(display: pd.DataFrame) -> None:
    """
    Recent fills as a list of rows a human can read at a glance, each in
    its own container keyed by the fill's own identity - not `st.dataframe`
    (a canvas-drawn grid, not real per-row DOM), which can't play a
    per-row entrance animation when a new fill arrives.
    """
    present = [
        (label, weight)
        for label, weight in _FILL_COLUMNS
        if label in display.columns
    ]
    labels = [label for label, _ in present]
    weights = [weight for _, weight in present]

    # A placeholder's contents are replaced wholesale each rerun, rather
    # than diffed row-by-row against whatever a previous, longer page left
    # behind - a plain sequence of containers left stale rows on screen
    # when paging onto a shorter page (the last page of a table isn't
    # always full).
    with st.empty(), st.container():
        for col, label in zip(st.columns(weights), labels):
            col.markdown(f"**{label}**")

        for _, row in display.iterrows():
            with st.container(key=row_key("fill", _fill_identity(row))):
                for col, label in zip(st.columns(weights), labels):
                    _render_fill_cell(col, label, row[label])

        st.html(f"<style>{row_add_rule('fill')}{_FILL_ROW_CSS}</style>")


def pnl_by_symbol(
    fills: pd.DataFrame, latest_mid: pd.DataFrame
) -> pd.DataFrame:
    """Position, net cash flow and mark-to-market PnL per symbol.

    Net cash flow alone looks worse than reality while inventory is still
    held: the cash spent buying it shows up as an outflow with nothing
    offsetting it. Held inventory is marked at the latest mid price too, to
    match PositionManager.total_pnl in the engine. `latest_mid` is the last
    `ticker_feed` row per symbol (see `read_latest_per_group`), not the
    whole table - a mark price only ever needs the current one.
    """
    signed_qty = fills["fill_qty"].where(
        fills["side"] == "BUY", -fills["fill_qty"]
    )
    cash_flow = (-fills["fill_price"] * signed_qty) - fills["fee"]
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

    if not latest_mid.empty:
        mark_price = pd.Series(
            ((latest_mid["bid_price"] + latest_mid["ask_price"]) / 2).values,
            index=latest_mid["symbol"],
        )
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
    ordered = fills.sort_values(_time_column(fills, "transaction_timestamp"))
    for _, symbol_fills in ordered.groupby("symbol"):
        position, avg_cost = 0.0, 0.0
        for fill in symbol_fills.itertuples():
            signed = fill.fill_qty if fill.side == "BUY" else -fill.fill_qty
            total -= fill.fee

            opening = position == 0.0 or (position > 0) == (signed > 0)
            if opening:
                # Adding to the position: fold the fill into the average.
                size = abs(position) + abs(signed)
                avg_cost = (
                    abs(position) * avg_cost + abs(signed) * fill.fill_price
                ) / size
                position += signed
                continue

            # Trading against the position realizes the difference between
            # the fill price and the average cost of what it closes out.
            closed = min(abs(signed), abs(position))
            direction = 1.0 if position > 0 else -1.0
            total += closed * (fill.fill_price - avg_cost) * direction

            flipped = abs(signed) - closed > POSITION_EPSILON
            position += signed
            if flipped:
                # The remainder opens a new position the other way round.
                avg_cost = fill.fill_price
            elif abs(position) <= POSITION_EPSILON:
                position, avg_cost = 0.0, 0.0
    return total


_POSITIVE_COLOR = "#4E9F1F"
_NEGATIVE_COLOR = "#E2574C"


def _sign_color(value: float) -> str:
    """A PnL amount's color, the way quotes are colored elsewhere."""
    return _POSITIVE_COLOR if value >= 0 else _NEGATIVE_COLOR


def _render_pnl(fills: pd.DataFrame, latest_mid: pd.DataFrame) -> None:
    by_symbol = pnl_by_symbol(fills, latest_mid)

    # `animated_metric` is a custom component, and unlike `st.metric` it
    # fills whatever width it's given rather than shrinking to its content
    # - so it needs a fixed-width column of its own, the same way the
    # Market Data metrics get one, rather than a plain flex row.
    cols = iter(st.columns(5 + 2 * len(by_symbol)))

    total_pnl = by_symbol["total_pnl"].sum()
    with next(cols):
        animated_metric(
            "total-pnl",
            "Total PnL",
            total_pnl,
            color=_sign_color(total_pnl),
            border=True,
            help="Everything made or lost so far, counting inventory "
            "still held at the current mid price.",
        )
    realized = realized_pnl(fills)
    with next(cols):
        animated_metric(
            "realized-pnl",
            "Realized PnL",
            realized,
            color=_sign_color(realized),
            border=True,
            help="Profit on positions that have been closed out again, "
            "after fees. Inventory still held only counts once it is sold.",
        )
    net_cash = by_symbol["net_cash"].sum()
    with next(cols):
        animated_metric(
            "net-cash-flow",
            "Net cash flow",
            net_cash,
            color=_sign_color(net_cash),
            border=True,
            help="Cash taken in from sells minus cash paid out on buys, "
            "after fees. Buying inventory looks like a loss here until it "
            "is sold again.",
        )
    with next(cols):
        animated_metric(
            "inventory-value",
            "Inventory value",
            by_symbol["inventory_value"].sum(),
            border=True,
            help="What the inventory still held is worth at the current "
            "mid price.",
        )
    with next(cols):
        animated_metric(
            "fees-paid",
            "Fees paid",
            fills["fee"].sum(),
            border=True,
            help="Fees charged across all fills, already subtracted from "
            "realized PnL and net cash flow.",
        )
    for symbol, row in by_symbol.iterrows():
        with next(cols):
            animated_metric(
                f"{symbol}-position",
                f"{symbol} position",
                row["position"],
                decimals=None,
                border=True,
                help="How much is held right now. A negative number "
                "means the position is short.",
            )
        mark = row["mark_price"]
        mark_help = (
            "The current mid price, halfway between the best bid "
            "and the best ask."
        )
        with next(cols):
            if pd.isna(mark):
                st.metric(
                    f"{symbol} mark price",
                    "-",
                    border=True,
                    help=mark_help,
                )
            else:
                animated_metric(
                    f"{symbol}-mark-price",
                    f"{symbol} mark price",
                    float(mark),
                    border=True,
                    help=mark_help,
                )


def render() -> None:
    if not warn_if_no_db():
        return

    db_path = st.session_state.db_path
    fills = read_table(db_path, "decorated_order_fill")

    if fills.empty:
        st.info("No fills yet.")
    else:
        latest_mid = read_latest_per_group(db_path, "ticker_feed", "symbol")
        _render_pnl(fills, latest_mid)

    st.divider()

    st.markdown("**Recent fills**")
    if fills.empty:
        st.info("No fills yet.")
    else:
        display, show_pagination = paginate(
            fills_table(fills), key="recent-fills", page_size=PAGE_SIZE
        )
        render_fills_list(display)
        show_pagination()
