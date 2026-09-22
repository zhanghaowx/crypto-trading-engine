from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

import pandas as pd
import streamlit as st

from jolteon.analysis.markouts import (
    DEFAULT_MAX_FAIR_PRICE_LAG_SECONDS,
    HORIZONS,
    compute_fill_edge,
    compute_markout,
    derive_fill_markouts,
    horizon_seconds,
)
from jolteon.analysis.pnl import (
    Realized,
    fold_fills,
    pnl_by_symbol,
    signed_cash_flow,
)
from jolteon.dashboard import aggregates, table
from jolteon.dashboard.card import Accent
from jolteon.dashboard.components import (
    NEGATIVE_RGB,
    POSITIVE_RGB,
    BadgeColor,
    fmt_usd,
    metric,
    paginate,
    row_key,
    sign_color,
    warn_if_no_db,
)
from jolteon.dashboard.data.fair_prices import read_fair_prices_for_fills
from jolteon.dashboard.data.runs import read_run_table
from jolteon.dashboard.data.sqlite import (
    as_datetime,
    max_rowid,
    read_after,
    read_latest_per_group,
)
from jolteon.dashboard.settings import current_run_id

# The recorded tables grow without bound; fills are paginated rather than
# read in full onto the page.
PAGE_SIZE = 10

FILLS = "decorated_order_fill"

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


def _cash_flow_column(fills: pd.DataFrame) -> pd.Series | None:
    needed = {"side", "fill_price", "fill_qty"}
    return signed_cash_flow(fills) if needed.issubset(fills.columns) else None


def _edge_column(fills: pd.DataFrame) -> pd.Series | None:
    needed = {"side", "fill_price", "fair_price_at_fill", "fill_qty", "fee"}
    return compute_fill_edge(fills) if needed.issubset(fills.columns) else None


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


def _derive_visible_markouts(
    db_path: str, fills: pd.DataFrame
) -> pd.DataFrame:
    """Enrich only the visible fill page with timestamp-derived markouts.

    The card shows one page at a time, so the fair-price series is read
    for the window those fills span rather than for the whole session.
    """
    fair_prices = read_fair_prices_for_fills(
        db_path,
        fills,
        max_horizon_seconds=max(
            horizon_seconds(horizon) for horizon in HORIZONS
        ),
        max_lag_seconds=DEFAULT_MAX_FAIR_PRICE_LAG_SECONDS,
    )
    return derive_fill_markouts(fills, fair_prices)


def fills_table(fills: pd.DataFrame) -> pd.DataFrame:
    """Every fill, newest first. The venue's maker/taker order ids are
    opaque UUIDs, so they're dropped in favour of the short trade and
    client order ids."""
    ordered = _newest_first(fills, "transaction_timestamp")
    price = _optional(ordered, "fill_price")
    quantity = _optional(ordered, "fill_qty")
    execution_id = _optional(ordered, "exchange_execution_id")
    return _readable(
        {
            "Time": _local_time(
                ordered.get("transaction_timestamp", ordered.get("timestamp"))
            ),
            # As text, so the id reads as a label rather than a quantity.
            "Trade": None
            if execution_id is None
            else execution_id.astype(str),
            "Order": _optional(ordered, "client_order_id"),
            "Side": _optional(ordered, "side"),
            "Symbol": _optional(ordered, "symbol"),
            "Price": price,
            "Edge": _edge_column(ordered),
            "Quantity": quantity,
            "Cash Flow": _cash_flow_column(ordered),
            "Fee": _optional(ordered, "fee"),
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
    ("Cash Flow", 1.1),
    ("Fee", 0.9),
    ("Markout +100ms", 1.3),
    ("Markout +1s", 1.2),
    ("Markout +5s", 1.2),
    ("Markout +30s", 1.3),
]

# Side badges in the theme's semantic green/red (config.toml), so BUY and
# SELL rows are scannable at a glance in the fills list.
_SIDE_BADGE_COLORS: dict[str, BadgeColor] = {"BUY": "green", "SELL": "red"}

_FILLS_TABLE_CSS = (
    Path(__file__).resolve().parents[1] / "static" / "fills_table.css"
).read_text()


def _fill_identity(row: pd.Series) -> str:
    """A fill's own stable identity - not its position in the recent
    list, which shifts as newer fills arrive and push it down - so a row
    already on screen keeps its key, and its DOM node, across reruns."""
    trade = row.get("Trade")
    if trade:
        return str(trade)
    return (
        f"{row.get('Time')}-{row.get('Symbol')}-"
        f"{row.get('Price')}-{row.get('Quantity')}"
    )


_SIGNED_USD_LABELS = {
    "Edge",
    "Cash Flow",
    "Markout +100ms",
    "Markout +1s",
    "Markout +5s",
    "Markout +30s",
}


def _render_signed_usd(value) -> None:
    """A signed dollar amount in the theme's semantic green/red."""
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
        elif label == "Price":
            st.write(f"{value:,.2f}")
        elif label == "Quantity":
            st.write(f"{value:.6f}")
        elif label == "Fee":
            st.write(f"{value:,.4f}")
        else:
            st.write(value)


def render_fills_list(display: pd.DataFrame) -> None:
    """
    Recent fills as a list of rows a human can read at a glance, each in
    its own container keyed by the fill's own identity - not
    `st.dataframe`, a canvas-drawn grid whose cells cannot carry a badge
    or be coloured by the sign of what is in them.
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

        st.html(f"<style>{_FILLS_TABLE_CSS}</style>")


_REALIZED = "_realized_pnl_carried"


def realized_pnl_now(db_path: str, run_id: str | None = None) -> float:
    """
    Profit on the round trips closed over the whole recording.

    Carried between refreshes: only the fills recorded since the last one
    are folded in. Walking the session each time was the most expensive
    thing this page did, and holding the session to walk it was what made
    the figure wrong once the table outgrew what the dashboard keeps.

    The carry is dropped when the recording it was built from is gone -
    another engine's, or one whose row ids have started over.
    """
    carried = st.session_state.get(_REALIZED)
    if carried is not None:
        was, was_run, state, at = carried
        if (
            was != db_path
            or was_run != run_id
            or max_rowid(db_path, FILLS) < at
        ):
            carried = None
    if carried is None:
        state, at = Realized(), 0

    fresh, now_at = read_after(db_path, FILLS, at, run_id=run_id)
    if not fresh.empty:
        state = fold_fills(state, fresh)
    st.session_state[_REALIZED] = (db_path, run_id, state, now_at)
    return state.total


_SIDE_TINTS = {
    "BUY": "background-color: rgba({}, {}, {}, 0.12)".format(*POSITIVE_RGB),
    "SELL": "background-color: rgba({}, {}, {}, 0.12)".format(*NEGATIVE_RGB),
}


def _render_pnl(model: "OrdersModel") -> None:
    by_symbol = model.pnl

    cols = iter(st.columns(5 + len(by_symbol)))

    total_pnl = by_symbol["total_pnl"].sum()
    with next(cols):
        metric(
            "Total PnL",
            total_pnl,
            color=sign_color(total_pnl),
            border=True,
        )
    realized = model.realized
    with next(cols):
        metric(
            "Realized PnL",
            realized,
            color=sign_color(realized),
            border=True,
        )
    net_cash = by_symbol["net_cash"].sum()
    with next(cols):
        metric(
            "Net cash flow",
            net_cash,
            color=sign_color(net_cash),
            border=True,
        )
    with next(cols):
        metric(
            "Inventory value",
            by_symbol["inventory_value"].sum(),
            border=True,
        )
    with next(cols):
        metric(
            "Fees paid",
            model.fees,
            border=True,
        )
    for symbol, row in by_symbol.iterrows():
        with next(cols):
            metric(
                f"{symbol} position",
                row["position"],
                decimals=None,
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


def _markout_help(context: str) -> dict[str, str]:
    return {
        f"Markout +{horizon}": (
            "How much the price moved in our favor, on average, "
            f"{_HORIZON_PHRASES[horizon]} after {context}."
        )
        for horizon in HORIZONS
    }


def _shaded_table(
    rows: pd.DataFrame,
    money_columns: list[str],
    column_help: Mapping[str, str],
    *,
    shade_side: bool = False,
) -> None:
    table.render(
        rows,
        shaded_columns=money_columns,
        format_fn=fmt_usd,
        column_help=column_help,
        row_style=(
            (lambda row: _SIDE_TINTS.get(row["Side"], ""))
            if shade_side
            else None
        ),
    )


def _render_fair_price_movement(
    db_path: str, run_id: str | None = None
) -> None:
    movement = aggregates.avg_fair_price_movement(db_path, run_id)
    if movement.empty:
        return

    st.markdown("**Fair price movement**")
    columns = [f"+{horizon}" for horizon in HORIZONS]
    rows = pd.DataFrame([movement.values], columns=columns)
    column_help = {
        f"+{horizon}": (
            "Average change in the fair price itself, "
            f"{_HORIZON_PHRASES[horizon]} after a fill - a positive "
            "number means it tends to keep rising, negative means it "
            "tends to fall back."
        )
        for horizon in HORIZONS
    }
    _shaded_table(rows, columns, column_help)


def _render_fill_quality(db_path: str, run_id: str | None = None) -> None:
    """BUY vs SELL execution quality (section 6)."""
    by_side = aggregates.fill_quality_by_side(db_path, run_id)
    if by_side.empty:
        return

    st.markdown("**Fill Quality**")
    rows = pd.DataFrame(
        {
            "Side": by_side.index,
            "Fills": by_side["fill_count"].astype(int),
            "Average edge": by_side["avg_edge"],
            **_markout_stats(by_side),
        }
    )
    column_help = {
        "Average edge": (
            "How far the fill price sat from fair value at the "
            "moment of execution, in our favor, averaged across fills "
            "on this side."
        ),
        **_markout_help("we filled"),
    }
    _shaded_table(
        rows,
        ["Average edge", *_MARKOUT_COLUMNS],
        column_help,
        shade_side=True,
    )


def _render_inventory_buckets(db_path: str, run_id: str | None = None) -> None:
    """Whether fills made at extreme inventory levels look different from
    fills made near neutral (section 5)."""
    stats = aggregates.inventory_buckets(db_path, run_id=run_id)
    if stats.empty:
        return

    st.markdown("**Inventory Buckets**")
    rows = pd.DataFrame(
        {
            "Inventory": stats.index,
            "Fills": stats["fill_count"].astype(int),
            "BUY": stats["buy_count"].astype(int),
            "SELL": stats["sell_count"].astype(int),
            "Average edge": stats["avg_edge"],
            **_markout_stats(stats),
        }
    )
    column_help = {
        "Average edge": (
            "How far the fill price sat from fair value at the "
            "moment of execution, in our favor, averaged across fills "
            "made while inventory was in this range."
        ),
        **_markout_help("a fill made while inventory was in this range"),
    }
    _shaded_table(rows, ["Average edge", *_MARKOUT_COLUMNS], column_help)


@dataclass(frozen=True)
class OrdersModel:
    """One refresh's fills and PnL, shared by the card's renderers."""

    fills: pd.DataFrame
    pnl: pd.DataFrame
    realized: float = 0.0
    fees: float = 0.0


def load() -> OrdersModel:
    db_path = st.session_state.db_path
    run_id = current_run_id()
    fills = read_run_table(db_path, FILLS, run_id)
    if fills.empty:
        return OrdersModel(fills, pd.DataFrame())
    latest_mid = read_latest_per_group(
        db_path, "bbo_feed", "symbol", run_id=run_id
    )
    return OrdersModel(
        fills,
        pnl_by_symbol(
            aggregates.position_and_cash(db_path, run_id), latest_mid
        ),
        realized_pnl_now(db_path, run_id),
        aggregates.total_fees(db_path, run_id),
    )


def accent(model: "OrdersModel | None" = None) -> Accent:
    """The card's edge color: green while the day is up, red while it is
    down, and nothing at all before the first fill."""
    model = load() if model is None else model
    if model.fills.empty:
        return None
    return "green" if model.realized >= 0 else "red"


def render_header_actions(model: "OrdersModel | None" = None) -> None:
    """A download icon for the card title's own row - every raw fill as
    a CSV file, the fastest way to get this page's data out for analysis
    elsewhere. A no-op until there are fills to download."""
    model = load() if model is None else model
    fills = model.fills
    if fills.empty:
        return
    st.download_button(
        "",
        data=fills.to_csv(index=False),
        file_name="fills.csv",
        mime="text/csv",
        icon=":material/download:",
        type="tertiary",
        help="Download every fill as CSV, for analysis elsewhere.",
    )


def render(model: "OrdersModel | None" = None) -> None:
    if not warn_if_no_db():
        return

    model = load() if model is None else model
    fills = model.fills

    if fills.empty:
        st.info("No fills yet.")
    else:
        _render_pnl(model)

    st.divider()

    st.markdown("**Recent fills**")
    if fills.empty:
        st.info("No fills yet.")
    else:
        # Paged before the display columns are worked out, not after:
        # every one of them - the edge, the cash flow, a markout per
        # horizon - was being computed for a whole session's fills to
        # show the ten on screen.
        page, show_pagination = paginate(
            _newest_first(fills, "transaction_timestamp"),
            key="recent-fills",
            page_size=PAGE_SIZE,
        )
        page = _derive_visible_markouts(st.session_state.db_path, page)
        render_fills_list(fills_table(page))
        show_pagination()


def render_trade_quality() -> None:
    """Execution quality (section 6, 9) and inventory bucketing (section
    5) - their own card, separate from Orders & PnL's raw fills and cash
    totals."""
    if not warn_if_no_db():
        return

    # Every table on this card is one row per side or per bucket however
    # many fills there are, so the recording works them out itself -
    # nothing here holds a session's fills to average them.
    db_path = st.session_state.db_path
    run_id = current_run_id()
    if not aggregates.any_fills(db_path, run_id):
        st.info("No fills yet.")
        return

    _render_fill_quality(db_path, run_id)
    _render_inventory_buckets(db_path, run_id)
    _render_fair_price_movement(db_path, run_id)
