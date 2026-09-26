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
from jolteon.dashboard.data import trade_queries
from jolteon.dashboard.data.fair_prices import read_fair_prices_for_fills
from jolteon.dashboard.data.runs import read_run_table
from jolteon.dashboard.data.sqlite import (
    as_datetime,
    database_exists,
    max_rowid,
    read_after,
    read_latest_per_group,
)
from jolteon.dashboard.state import current_run_id
from jolteon.dashboard.ui.empty_states import empty_state, warn_if_no_db
from jolteon.dashboard.ui.pagination import paginate
from jolteon.dashboard.ui.primitives import (
    MISSING,
    SIDE_COLORS,
    fmt_usd,
    metric,
    row_key,
    sign_color,
)

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
        st.write(MISSING)
        return
    st.markdown(f":{sign_color(value)}[{fmt_usd(value)}]")


def _render_fill_cell(col, label: str, value) -> None:
    with col:
        if label == "Side":
            st.badge(value, color=SIDE_COLORS.get(value, "gray"))
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
            trade_queries.position_and_cash(db_path, run_id), latest_mid
        ),
        realized_pnl_now(db_path, run_id),
        trade_queries.total_fees(db_path, run_id),
    )


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


def render_summary(model: "OrdersModel | None" = None) -> None:
    """
    The session's figures in one row, above everything they are made of.

    A row of the page rather than a card on it, so it has no title to
    say why it is empty under - and nothing to say that the cards below
    do not already: before the first fill, or with no recording to read,
    it draws nothing at all.
    """
    if not database_exists(st.session_state.db_path):
        return
    model = load() if model is None else model
    if not model.fills.empty:
        _render_pnl(model)


def render(model: "OrdersModel | None" = None) -> None:
    """The fills themselves, newest first, a page at a time."""
    if not warn_if_no_db():
        return

    model = load() if model is None else model
    fills = model.fills
    if fills.empty:
        empty_state("No fills yet.")
        return

    # Paged before the display columns are worked out, not after: every
    # one of them - the edge, the cash flow, a markout per horizon - was
    # being computed for a whole session's fills to show the ten on
    # screen.
    page, show_pagination = paginate(
        _newest_first(fills, "transaction_timestamp"),
        key="recent-fills",
        page_size=PAGE_SIZE,
    )
    page = _derive_visible_markouts(st.session_state.db_path, page)
    render_fills_list(fills_table(page))
    show_pagination()
