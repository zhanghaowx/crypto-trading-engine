"""Figures the recording works out for itself.

A session's fills outgrow anything the dashboard can sensibly hold, and
these derivations answer in one row per side or per inventory bucket
however many fills there are. Asking SQLite for the answer keeps the
whole table out of the dashboard's hands: nothing to cache, nothing to
trim, and nothing that quietly reports on the most recent hundred
thousand fills as though they were the session.

Fills are recorded immutably, so fair value at the fill and at each
horizon is joined here against the recorded fair-price series rather than
read from a column. The sign convention is the one `analytics` documents
- positive is in the market maker's favour - written here as SQL rather
than as pandas:

    BUY:  value = future_price - execution_price
    SELL: value = execution_price - future_price
"""

import sqlite3

import pandas as pd
import streamlit as st

from jolteon.app.analytics import (
    DEFAULT_INVENTORY_BUCKETS,
    DEFAULT_MAX_FAIR_PRICE_LAG_SECONDS,
    FILL_TIME,
    HORIZONS,
    horizon_seconds,
    observation_tolerance,
)
from jolteon.app.analytics import InventoryBucket as Bucket
from jolteon.app.data import (
    database_exists,
    ensure_fair_price_lookup_index,
    max_rowid,
)

FILLS = "decorated_order_fill"
FAIR_PRICES = "fair_price"

# Which way a fill's price has to move to be in our favour.
_DIRECTION = "(CASE side WHEN 'BUY' THEN 1 ELSE -1 END)"

# Names the joined fair prices take inside the analysis relation. Prefixed
# so they cannot collide with a recorded column of the fills table.
_AT_FILL = "_fair_price_at_fill"

# At the fill itself the whole tolerance applies: the latest fair price
# before an execution is the one the strategy was quoting against, however
# recently the book last moved. The forward horizons cap it by the horizon
# they measure - see `analytics.observation_tolerance`.
_AT_FILL_TOLERANCE = DEFAULT_MAX_FAIR_PRICE_LAG_SECONDS


def _horizon_price(horizon: str) -> str:
    return f"_fair_price_{horizon}"


_EDGE = f"{_DIRECTION} * ({_AT_FILL} - fill_price)"


def _markout(horizon: str) -> str:
    return f"{_DIRECTION} * ({_horizon_price(horizon)} - fill_price)"


def _markout_columns() -> str:
    """Average gross and fee-adjusted markout at each horizon.

    A horizon with no observation close enough to measure it is NULL, and
    SQL's own AVG passes over those exactly as a pandas mean passes over
    the NaN it reads them as - so a fill whose thirty-second figure has
    not happened yet counts towards the horizons that have, and not
    towards the one that has not.
    """
    return ", ".join(
        f"AVG({_markout(h)}) AS avg_markout_{h}, "
        f"AVG({_markout(h)} - fee) AS avg_net_markout_{h}"
        for h in HORIZONS
    )


# How long an answer may stand before it is worked out again, whatever
# the recording's length says. A fill recorded seconds ago has no
# thirty-second fair price to join to yet, and gains one as the recording
# runs on past it - which changes an average without adding a fill for it
# to be noticed by.
_STALE_SECONDS = 30


@st.cache_data(ttl=_STALE_SECONDS, show_spinner=False)
def _answer(db_path: str, sql: str, through: int) -> pd.DataFrame:
    """
    The rows `sql` returns, or nothing where the recording cannot answer
    it - an older one may not have the columns a newer payload writes.

    `through` is how far the recording has got, and is what decides
    whether the last answer still stands: every one of these reads the
    whole table, so a refresh that finds nothing new should not read it
    again.
    """
    if not database_exists(db_path):
        return pd.DataFrame()
    conn = sqlite3.connect(db_path)
    try:
        return pd.read_sql(sql, conn)
    except (sqlite3.OperationalError, pd.errors.DatabaseError):
        return pd.DataFrame()
    finally:
        conn.close()


def _query(db_path: str, sql: str) -> pd.DataFrame:
    # Keyed on fills alone, not on fair prices too: fair prices arrive
    # continuously, so counting them would change the key on every refresh
    # and never let an answer stand. `_STALE_SECONDS` is what covers the
    # horizons that resolve without a new fill.
    return _answer(db_path, sql, max_rowid(db_path, FILLS))


def _fair_price_at(target: str, *, tolerance: float, future: bool) -> str:
    """SQL for the recorded fair price nearest `target` on the fill's own
    model, or NULL where the nearest one sits further away than
    `tolerance` - a data gap rather than a measurement of this horizon."""
    if future:
        predicate = f"fp.timestamp >= {target}"
        distance = f"fp.timestamp - ({target})"
        order = "ASC, fp.rowid ASC"
    else:
        predicate = f"fp.timestamp <= {target}"
        distance = f"({target}) - fp.timestamp"
        order = "DESC, fp.rowid DESC"

    return (
        f"(SELECT (fp.bid_fair_price + fp.ask_fair_price) / 2.0 "
        f'FROM "{FAIR_PRICES}" fp '
        f"WHERE fp.symbol = f.symbol "
        f"AND fp.model = f.fair_price_model "
        f"AND {predicate} "
        f"AND {distance} <= {tolerance} "
        f"ORDER BY fp.timestamp {order} LIMIT 1)"
    )


def _analysis_cte() -> str:
    """One per-fill relation carrying the joined fair prices, shared by
    every markout aggregate below."""
    fill_time = f"f.{FILL_TIME}"
    at_fill = _fair_price_at(
        fill_time, tolerance=_AT_FILL_TOLERANCE, future=False
    )
    derived = [f"{at_fill} AS {_AT_FILL}"]
    for horizon in HORIZONS:
        target = f"({fill_time} + {horizon_seconds(horizon)})"
        price = _fair_price_at(
            target,
            tolerance=observation_tolerance(horizon),
            future=True,
        )
        derived.append(f"{price} AS {_horizon_price(horizon)}")

    return (
        "WITH derived_fill AS ("
        f"SELECT f.*, {', '.join(derived)} "
        f'FROM "{FILLS}" f'
        ") "
    )


def _numeric(frame: pd.DataFrame) -> pd.DataFrame:
    """Every column as a number.

    An average over horizons none of which have resolved comes back from
    SQL as NULL, which pandas reads as a `None` object and leaves the
    whole column unable to do arithmetic. Read as NaN it behaves like any
    other missing figure.
    """
    return frame.apply(pd.to_numeric, errors="coerce")


def any_fills(db_path: str) -> bool:
    """Whether the recording holds a fill at all - asked of the recording
    rather than of a table read into memory to be measured."""
    rows = _query(db_path, f'SELECT 1 FROM "{FILLS}" LIMIT 1')
    return not rows.empty


def fill_quality_by_side(db_path: str) -> pd.DataFrame:
    """Fill count, average edge, and average gross and fee-adjusted
    markout at each horizon, broken out by BUY against SELL - whether one
    side of the market is systematically worse than the other, indexed by
    side."""
    ensure_fair_price_lookup_index(db_path)
    rows = _query(
        db_path,
        _analysis_cte() + "SELECT side, COUNT(*) AS fill_count, "
        f"AVG({_EDGE}) AS avg_edge, AVG(fee) AS avg_fee, "
        f"{_markout_columns()} "
        "FROM derived_fill GROUP BY side ORDER BY side",
    )
    return _numeric(rows.set_index("side")) if not rows.empty else rows


# What a fill did to the position, and the cash it moved doing it.
_SIGNED_QTY = f"{_DIRECTION} * fill_qty"
_CASH = f"-1 * {_SIGNED_QTY} * fill_price - fee"


def position_and_cash(db_path: str) -> pd.DataFrame:
    """
    What each symbol is holding and what its fills have moved in cash,
    indexed by symbol.

    Both are sums over every fill ever recorded, which is the whole
    reason to ask the recording for them: a position worked out from the
    fills a dashboard happens to be holding is a position that quietly
    starts from the middle of the session.
    """
    rows = _query(
        db_path,
        f"SELECT symbol, SUM({_SIGNED_QTY}) AS position, "
        f"SUM({_CASH}) AS net_cash "
        f'FROM "{FILLS}" GROUP BY symbol ORDER BY symbol',
    )
    return _numeric(rows.set_index("symbol")) if not rows.empty else rows


def total_fees(db_path: str) -> float:
    """Every fee paid over the session."""
    rows = _query(db_path, f'SELECT SUM(fee) AS fees FROM "{FILLS}"')
    if rows.empty or pd.isna(rows.iloc[0]["fees"]):
        return 0.0
    return float(rows.iloc[0]["fees"])


def _bucket_case(boundaries: tuple[Bucket, ...]) -> tuple[str, str]:
    """
    Returns: The SQL naming which bucket a fill's prior inventory falls
    into, and the SQL ranking those buckets in the order they are read
    in - short through long.

    A level belongs to the first bucket whose bound it does not exceed,
    which is what `classify_inventory_bucket` does with its own bins.
    """
    label, rank = "CASE", "CASE"
    for position, (name, bound) in enumerate(boundaries[:-1]):
        label += f" WHEN inventory_before <= {bound} THEN '{name}'"
        rank += f" WHEN inventory_before <= {bound} THEN {position}"
    label += f" ELSE '{boundaries[-1][0]}' END"
    rank += f" ELSE {len(boundaries) - 1} END"
    return label, rank


def inventory_buckets(
    db_path: str, boundaries: tuple[Bucket, ...] = DEFAULT_INVENTORY_BUCKETS
) -> pd.DataFrame:
    """
    Fill count, the BUY/SELL split, average edge, markout and net cash
    flow, one row per inventory bucket - classified by the position
    already held before each fill rather than by what the fill changed it
    to, so a bucket says how we traded while holding that much.

    `net_cash_flow` is this bucket's own fills' cash in and out, net of
    fees. It is not a realized against inventory split, which needs
    position state outliving any one bucket.
    """
    ensure_fair_price_lookup_index(db_path)
    label, rank = _bucket_case(boundaries)
    rows = _query(
        db_path,
        _analysis_cte() + f"SELECT {label} AS bucket, {rank} AS rank, "
        "COUNT(*) AS fill_count, "
        "SUM(CASE side WHEN 'BUY' THEN 1 ELSE 0 END) AS buy_count, "
        "SUM(CASE side WHEN 'SELL' THEN 1 ELSE 0 END) AS sell_count, "
        f"AVG({_EDGE}) AS avg_edge, "
        f"SUM({_DIRECTION} * -1 * fill_price * fill_qty - fee) "
        "AS net_cash_flow, "
        f"{_markout_columns()} "
        # A fill recorded without the position held before it belongs to
        # no bucket: it would otherwise fall through every bound into the
        # last one and read as having been made at the extreme.
        "FROM derived_fill WHERE inventory_before IS NOT NULL "
        "GROUP BY bucket, rank ORDER BY rank",
    )
    if rows.empty:
        return rows
    return _numeric(rows.drop(columns="rank").set_index("bucket"))


def avg_fair_price_movement(db_path: str) -> pd.Series:
    """
    Average signed change in the fair price itself at each horizon,
    across every fill, indexed by horizon label.

    Side-independent: this says nothing about how well we executed, only
    whether the fair price tends to keep drifting after a fill - whether
    the model has any short-term predictive power.
    """
    ensure_fair_price_lookup_index(db_path)
    moved = ", ".join(
        f'AVG({_horizon_price(h)} - {_AT_FILL}) AS "{h}"' for h in HORIZONS
    )
    rows = _query(
        db_path, _analysis_cte() + f"SELECT {moved} FROM derived_fill"
    )
    if rows.empty:
        return pd.Series(dtype=float)
    return pd.to_numeric(rows.iloc[0], errors="coerce")
