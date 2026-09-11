from collections.abc import Mapping
from datetime import datetime
from typing import Any

import pandas as pd
import streamlit as st

from jolteon.app.analytics import (
    HORIZONS,
    avg_fair_price_movement,
    compute_edge,
    compute_markout,
    fill_quality_by_side,
    inventory_bucket_stats,
)
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


def _edge_column(fills: pd.DataFrame) -> pd.Series | None:
    needed = {"side", "fill_price", "fair_price_at_fill"}
    return compute_edge(fills) if needed.issubset(fills.columns) else None


def _markout_columns(fills: pd.DataFrame) -> dict[str, pd.Series | None]:
    """Markout at each horizon, keyed by its display label - None wherever
    the raw fair-price column that horizon needs isn't in the table."""
    columns: dict[str, pd.Series | None] = {}
    for horizon in HORIZONS:
        needed = {"side", "fill_price", f"fair_price_{horizon}"}
        columns[f"Markout +{horizon}"] = (
            compute_markout(fills, horizon)
            if needed.issubset(fills.columns)
            else None
        )
    return columns


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
            "Edge": _edge_column(ordered),
            "Quantity": quantity,
            "Value": _notional(price, quantity),
            "Fee": _optional(ordered, "fee"),
            "Inventory Before": _optional(ordered, "inventory_before"),
            "Inventory After": _optional(ordered, "inventory_after"),
            **_markout_columns(ordered),
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
    ("Edge", 1.0),
    ("Quantity", 1.1),
    ("Value", 1.0),
    ("Fee", 0.9),
    ("Inventory Before", 1.2),
    ("Inventory After", 1.2),
    ("Markout +100ms", 1.3),
    ("Markout +1s", 1.2),
    ("Markout +5s", 1.2),
    ("Markout +30s", 1.3),
]

# Side badges in the theme's semantic green/red (config.toml), so BUY and
# SELL rows are scannable at a glance in the fills list.
_SIDE_BADGE_COLORS: dict[str, BadgeColor] = {"BUY": "green", "SELL": "red"}

_FILL_ROW_CSS = """
[class*="st-key-row-fill-"] {
  border-bottom: 1px solid #E5E5E5;
  padding: 6px 0;
}
"""

_FILL_HEADER_CSS = """
[class*="st-key-fills-table-header"] {
  background-color: #FAFAFA;
  border-bottom: 1px solid #E5E5E5;
  padding: 8px 4px;
}
[class*="st-key-fills-table-header"] p {
  font-weight: 500;
  font-size: 0.8rem;
  color: #525252;
  margin: 0;
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


_SIGNED_USD_LABELS = {
    "Edge",
    "Markout +100ms",
    "Markout +1s",
    "Markout +5s",
    "Markout +30s",
}


def _render_signed_usd(value) -> None:
    """A markout/edge amount, colored the way Side badges are: green
    when it favors the market maker, red when it's adverse selection."""
    if pd.isna(value):
        # Horizons not yet reached still carry NULL in the DB.
        st.write("-")
        return
    color = "green" if value >= 0 else "red"
    sign = "+" if value >= 0 else "-"
    st.markdown(f":{color}[{sign}${abs(value):,.2f}]")


def _render_fill_cell(col, label: str, value) -> None:
    with col:
        if label == "Side":
            st.badge(value, color=_SIDE_BADGE_COLORS.get(value, "gray"))
        elif label == "Time":
            st.write(value.strftime("%H:%M:%S.%f")[:-3])
        elif label in _SIGNED_USD_LABELS:
            _render_signed_usd(value)
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
        with st.container(key="fills-table-header"):
            for col, label in zip(st.columns(weights), labels):
                col.write(label)

        for _, row in display.iterrows():
            with st.container(key=row_key("fill", _fill_identity(row))):
                for col, label in zip(st.columns(weights), labels):
                    _render_fill_cell(col, label, row[label])

        st.html(
            f"<style>{row_add_rule('fill')}{_FILL_ROW_CSS}"
            f"{_FILL_HEADER_CSS}</style>"
        )


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


_POSITIVE_COLOR = "#16A34A"
_NEGATIVE_COLOR = "#DC2626"


def _sign_color(value: float) -> str:
    """A PnL amount's color, the way quotes are colored elsewhere."""
    return _POSITIVE_COLOR if value >= 0 else _NEGATIVE_COLOR


def _hex_to_rgb(color: str) -> tuple[int, int, int]:
    color = color.lstrip("#")
    return int(color[0:2], 16), int(color[2:4], 16), int(color[4:6], 16)


_POSITIVE_RGB = _hex_to_rgb(_POSITIVE_COLOR)
_NEGATIVE_RGB = _hex_to_rgb(_NEGATIVE_COLOR)


def _fmt_usd(value: float) -> str:
    if pd.isna(value):
        return "–"
    sign = "+" if value >= 0 else "-"
    return f"{sign}${abs(value):,.2f}"


def _shade(value: float, scale: float) -> str:
    """A background tint for a signed USD cell, deeper the further
    `value` sits from zero relative to `scale` (the column's own largest
    magnitude) - so the standout numbers in a row of tightly-packed
    figures read through color, not through font size."""
    if pd.isna(value) or scale == 0:
        return ""
    intensity = min(abs(value) / scale, 1.0)
    r, g, b = _POSITIVE_RGB if value >= 0 else _NEGATIVE_RGB
    alpha = 0.10 + 0.35 * intensity
    return f"background-color: rgba({r}, {g}, {b}, {alpha:.2f})"


def _shade_column(column: pd.Series) -> list[str]:
    scale = column.abs().max()
    return [_shade(value, scale) for value in column]


_SIDE_TINTS = {
    "BUY": "background-color: rgba({}, {}, {}, 0.12)".format(*_POSITIVE_RGB),
    "SELL": "background-color: rgba({}, {}, {}, 0.12)".format(*_NEGATIVE_RGB),
}


def _shade_side(column: pd.Series) -> list[str]:
    return [_SIDE_TINTS.get(value, "") for value in column]


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
        )
    realized = realized_pnl(fills)
    with next(cols):
        animated_metric(
            "realized-pnl",
            "Realized PnL",
            realized,
            color=_sign_color(realized),
            border=True,
        )
    net_cash = by_symbol["net_cash"].sum()
    with next(cols):
        animated_metric(
            "net-cash-flow",
            "Net cash flow",
            net_cash,
            color=_sign_color(net_cash),
            border=True,
        )
    with next(cols):
        animated_metric(
            "inventory-value",
            "Inventory value",
            by_symbol["inventory_value"].sum(),
            border=True,
        )
    with next(cols):
        animated_metric(
            "fees-paid",
            "Fees paid",
            fills["fee"].sum(),
            border=True,
        )
    for symbol, row in by_symbol.iterrows():
        with next(cols):
            animated_metric(
                f"{symbol}-position",
                f"{symbol} position",
                row["position"],
                decimals=None,
                border=True,
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
                )


_HORIZON_PHRASES = {
    "100ms": "100 milliseconds",
    "1s": "1 second",
    "5s": "5 seconds",
    "30s": "30 seconds",
}

_MARKOUT_COLUMNS = [f"Markout +{horizon}" for horizon in HORIZONS]


def _markout_stats(stats: pd.DataFrame) -> dict[str, pd.Series]:
    return {
        f"Markout +{horizon}": stats[f"avg_markout_{horizon}"]
        for horizon in HORIZONS
    }


def _markout_column_config(context: str) -> dict[str, object]:
    return {
        f"Markout +{horizon}": st.column_config.NumberColumn(
            help="How much the price moved in our favor, on average, "
            f"{_HORIZON_PHRASES[horizon]} after {context}."
        )
        for horizon in HORIZONS
    }


def _shaded_table(
    table: pd.DataFrame,
    money_columns: list[str],
    column_config: Mapping[str, Any],
    *,
    shade_side: bool = False,
) -> None:
    styled = table.style.format({col: _fmt_usd for col in money_columns})
    styled = styled.apply(_shade_column, subset=money_columns, axis=0)
    if shade_side:
        styled = styled.apply(_shade_side, subset=["Side"], axis=0)
    st.dataframe(
        styled,
        hide_index=True,
        width="stretch",
        column_config=column_config,
    )


def _render_fair_price_movement(fills: pd.DataFrame) -> None:
    st.markdown("**Fair price movement**")
    movement = avg_fair_price_movement(fills)
    columns = [f"+{horizon}" for horizon in HORIZONS]
    table = pd.DataFrame([movement.values], columns=columns)
    column_config = {
        f"+{horizon}": st.column_config.NumberColumn(
            help="Average change in the fair price itself, "
            f"{_HORIZON_PHRASES[horizon]} after a fill - a positive "
            "number means it tends to keep rising, negative means it "
            "tends to fall back."
        )
        for horizon in HORIZONS
    }
    _shaded_table(table, columns, column_config)


def _render_fill_quality(fills: pd.DataFrame) -> None:
    """BUY vs SELL execution quality (section 6)."""
    needed = {"side", "fill_price", "fair_price_at_fill"}
    if not needed.issubset(fills.columns):
        return

    st.markdown("**Fill Quality**")
    by_side = fill_quality_by_side(fills).sort_index()
    table = pd.DataFrame(
        {
            "Side": by_side.index,
            "Fills": by_side["fill_count"].astype(int),
            "Average edge": by_side["avg_edge"],
            **_markout_stats(by_side),
        }
    )
    column_config = {
        "Average edge": st.column_config.NumberColumn(
            help="How far the fill price sat from fair value at the "
            "moment of execution, in our favor, averaged across fills "
            "on this side."
        ),
        **_markout_column_config("we filled"),
    }
    _shaded_table(
        table,
        ["Average edge", *_MARKOUT_COLUMNS],
        column_config,
        shade_side=True,
    )


def _render_inventory_buckets(fills: pd.DataFrame) -> None:
    """Whether fills made at extreme inventory levels look different from
    fills made near neutral (section 5)."""
    needed = {"inventory_before", "side", "fill_price", "fair_price_at_fill"}
    if not needed.issubset(fills.columns):
        return

    stats = inventory_bucket_stats(fills)
    if stats.empty:
        return

    st.markdown("**Inventory Buckets**")
    table = pd.DataFrame(
        {
            "Inventory": stats.index,
            "Fills": stats["fill_count"].astype(int),
            "BUY": stats["buy_count"].astype(int),
            "SELL": stats["sell_count"].astype(int),
            "Average edge": stats["avg_edge"],
            **_markout_stats(stats),
        }
    )
    column_config = {
        "Average edge": st.column_config.NumberColumn(
            help="How far the fill price sat from fair value at the "
            "moment of execution, in our favor, averaged across fills "
            "made while inventory was in this range."
        ),
        **_markout_column_config(
            "a fill made while inventory was in this range"
        ),
    }
    _shaded_table(table, ["Average edge", *_MARKOUT_COLUMNS], column_config)


def render_header_actions() -> None:
    """A download icon for the section title's own row (see
    `dashboard.py`'s `actions` slot on `_section`) - every raw fill as a
    CSV file, the fastest way to get this page's data out for analysis
    elsewhere. A no-op until there are fills to download."""
    fills = read_table(st.session_state.db_path, "decorated_order_fill")
    if fills.empty:
        return
    with st.container(horizontal=True, horizontal_alignment="right"):
        st.download_button(
            "",
            data=fills.to_csv(index=False),
            file_name="fills.csv",
            mime="text/csv",
            icon=":material/download:",
            help="Download every fill as CSV, for analysis elsewhere.",
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


def render_trade_quality() -> None:
    """Execution quality (section 6, 9) and inventory bucketing (section
    5) - their own card, separate from Orders & PnL's raw fills and cash
    totals."""
    if not warn_if_no_db():
        return

    fills = read_table(st.session_state.db_path, "decorated_order_fill")
    if fills.empty:
        st.info("No fills yet.")
        return

    _render_fill_quality(fills)
    st.divider()
    _render_inventory_buckets(fills)
    st.divider()
    if f"fair_price_{HORIZONS[0]}" in fills.columns:
        _render_fair_price_movement(fills)
