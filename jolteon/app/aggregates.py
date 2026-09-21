"""Figures the recording works out for itself, one trading session at a time.

A session's fills outgrow anything the dashboard can sensibly hold, and
these derivations answer in one row per side or per inventory bucket
however many fills there are. Asking SQLite for the answer keeps the
whole table out of the dashboard's hands: nothing to cache, nothing to
trim, and nothing that quietly reports on the most recent hundred
thousand fills as though they were the session.

Every one of these takes the session it is to report on. A recording
holds as many trading sessions as it has been running days, so "every
row in the file" is not an accounting period and is never taken for one;
passing no session at all asks about the whole recording, and says so.

The sign convention is the one `analytics` documents - positive is in
the market maker's favour - written here as SQL rather than as pandas:

    BUY:  value = future_price - execution_price
    SELL: value = execution_price - future_price
"""

import sqlite3

import pandas as pd
import streamlit as st

from jolteon.app.analytics import DEFAULT_INVENTORY_BUCKETS, HORIZONS
from jolteon.app.analytics import InventoryBucket as Bucket
from jolteon.app.data import database_exists, max_rowid
from jolteon.engine.core.session.trading_session import (
    trading_session_window,
)

FILLS = "decorated_order_fill"
BBO = "bbo_feed"
SESSION_RUNS = "trading_session_run"

# Which way a fill's price has to move to be in our favour.
_DIRECTION = "(CASE side WHEN 'BUY' THEN 1 ELSE -1 END)"

# What a fill earned over fair value at the moment it happened.
_EDGE = f"{_DIRECTION} * (fair_price_at_fill - fill_price)"


def _markout(horizon: str) -> str:
    return f"{_DIRECTION} * (fair_price_{horizon} - fill_price)"


def _markout_columns() -> str:
    """Average gross and fee-adjusted markout at each horizon.

    A horizon that has not resolved yet is NULL, and SQL's own AVG passes
    over those exactly as a pandas mean passes over the NaN it reads them
    as - so a fill still waiting on its thirty-second figure counts
    towards the horizons that have arrived, and not towards the one that
    has not.
    """
    return ", ".join(
        f"AVG({_markout(h)}) AS avg_markout_{h}, "
        f"AVG({_markout(h)} - fee) AS avg_net_markout_{h}"
        for h in HORIZONS
    )


# How long an answer may stand before it is worked out again, whatever
# the recording's length says. The engine rewrites a fill in place while
# its markouts resolve, over the longest horizon of thirty seconds, and
# that changes an average without adding a row for it to be noticed by.
_STALE_SECONDS = 30


@st.cache_data(ttl=_STALE_SECONDS, show_spinner=False)
def _answer(
    db_path: str, sql: str, params: tuple, through: int
) -> pd.DataFrame:
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
        return pd.read_sql(sql, conn, params=params)
    except (sqlite3.OperationalError, pd.errors.DatabaseError):
        return pd.DataFrame()
    finally:
        conn.close()


def _query(
    db_path: str, sql: str, params: tuple = (), table: str = FILLS
) -> pd.DataFrame:
    return _answer(db_path, sql, params, max_rowid(db_path, table))


def _session_clause(session_id: str | None) -> tuple[str, tuple]:
    """
    Returns: The condition confining a query to one trading session, and
    what to bind to it - empty for a caller asking about the whole
    recording.
    """
    if session_id is None:
        return "", ()
    return "session_id = ?", (session_id,)


def _where(*conditions: str) -> str:
    kept = [condition for condition in conditions if condition]
    return f"WHERE {' AND '.join(kept)}" if kept else ""


def _numeric(frame: pd.DataFrame) -> pd.DataFrame:
    """Every column as a number.

    An average over horizons none of which have resolved comes back from
    SQL as NULL, which pandas reads as a `None` object and leaves the
    whole column unable to do arithmetic. Read as NaN it behaves like any
    other missing figure.
    """
    return frame.apply(pd.to_numeric, errors="coerce")


def any_fills(db_path: str, session_id: str | None = None) -> bool:
    """Whether the session holds a fill at all - asked of the recording
    rather than of a table read into memory to be measured."""
    session, binding = _session_clause(session_id)
    rows = _query(
        db_path,
        f'SELECT 1 FROM "{FILLS}" {_where(session)} LIMIT 1',
        binding,
    )
    return not rows.empty


def fill_quality_by_side(
    db_path: str, session_id: str | None = None
) -> pd.DataFrame:
    """Fill count, average edge, and average gross and fee-adjusted
    markout at each horizon, broken out by BUY against SELL - whether one
    side of the market is systematically worse than the other, indexed by
    side."""
    session, binding = _session_clause(session_id)
    rows = _query(
        db_path,
        f"SELECT side, COUNT(*) AS fill_count, "
        f"AVG({_EDGE}) AS avg_edge, AVG(fee) AS avg_fee, "
        f"{_markout_columns()} "
        f'FROM "{FILLS}" {_where(session)} GROUP BY side ORDER BY side',
        binding,
    )
    return _numeric(rows.set_index("side")) if not rows.empty else rows


# What a fill did to the position, and the cash it moved doing it.
_SIGNED_QTY = f"{_DIRECTION} * fill_qty"
_CASH = f"-1 * {_SIGNED_QTY} * fill_price - fee"


def position_and_cash(
    db_path: str, session_id: str | None = None
) -> pd.DataFrame:
    """
    What each symbol held when the session opened and when it closed,
    and what the session's own fills moved in cash and paid in fees,
    indexed by symbol.

    All four are sums the recording works out over every fill it holds,
    which is the whole reason to ask it: a position worked out from the
    fills a dashboard happens to be holding is a position that quietly
    starts from the middle of a day.

    The opening position is what the sessions before this one left
    behind, whichever engine run recorded them - so a process that
    started at noon still reports the morning's inventory as the
    afternoon's opening one.
    """
    if session_id is None:
        rows = _query(
            db_path,
            f"SELECT symbol, 0.0 AS opening_position, "
            f"SUM({_SIGNED_QTY}) AS position, "
            f"SUM({_CASH}) AS net_cash, SUM(fee) AS fees "
            f'FROM "{FILLS}" GROUP BY symbol ORDER BY symbol',
        )
    else:
        rows = _query(
            db_path,
            f"SELECT symbol, "
            f"SUM(CASE WHEN session_id < ? THEN {_SIGNED_QTY} ELSE 0 END) "
            f"AS opening_position, "
            f"SUM(CASE WHEN session_id <= ? THEN {_SIGNED_QTY} ELSE 0 END) "
            f"AS position, "
            f"SUM(CASE WHEN session_id = ? THEN {_CASH} ELSE 0 END) "
            f"AS net_cash, "
            f"SUM(CASE WHEN session_id = ? THEN fee ELSE 0 END) AS fees "
            f'FROM "{FILLS}" GROUP BY symbol ORDER BY symbol',
            (session_id,) * 4,
        )
    return _numeric(rows.set_index("symbol")) if not rows.empty else rows


def total_fees(db_path: str, session_id: str | None = None) -> float:
    """Every fee paid over the session."""
    session, binding = _session_clause(session_id)
    rows = _query(
        db_path,
        f'SELECT SUM(fee) AS fees FROM "{FILLS}" {_where(session)}',
        binding,
    )
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
    db_path: str,
    session_id: str | None = None,
    boundaries: tuple[Bucket, ...] = DEFAULT_INVENTORY_BUCKETS,
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
    label, rank = _bucket_case(boundaries)
    session, binding = _session_clause(session_id)
    rows = _query(
        db_path,
        f"SELECT {label} AS bucket, {rank} AS rank, COUNT(*) AS fill_count, "
        f"SUM(CASE side WHEN 'BUY' THEN 1 ELSE 0 END) AS buy_count, "
        f"SUM(CASE side WHEN 'SELL' THEN 1 ELSE 0 END) AS sell_count, "
        f"AVG({_EDGE}) AS avg_edge, "
        f"SUM({_DIRECTION} * -1 * fill_price * fill_qty - fee) "
        f"AS net_cash_flow, "
        f"{_markout_columns()} "
        # A fill recorded without the position held before it belongs to
        # no bucket: it would otherwise fall through every bound into the
        # last one and read as having been made at the extreme.
        f'FROM "{FILLS}" '
        f"{_where(session, 'inventory_before IS NOT NULL')} "
        f"GROUP BY bucket, rank ORDER BY rank",
        binding,
    )
    if rows.empty:
        return rows
    return _numeric(rows.drop(columns="rank").set_index("bucket"))


def avg_fair_price_movement(
    db_path: str, session_id: str | None = None
) -> pd.Series:
    """
    Average signed change in the fair price itself at each horizon,
    across every fill, indexed by horizon label.

    Side-independent: this says nothing about how well we executed, only
    whether the fair price tends to keep drifting after a fill - whether
    the model has any short-term predictive power.
    """
    moved = ", ".join(
        f'AVG(fair_price_{h} - fair_price_at_fill) AS "{h}"' for h in HORIZONS
    )
    session, binding = _session_clause(session_id)
    rows = _query(
        db_path,
        f'SELECT {moved} FROM "{FILLS}" {_where(session)}',
        binding,
    )
    if rows.empty:
        return pd.Series(dtype=float)
    return pd.to_numeric(rows.iloc[0], errors="coerce")


def sessions(db_path: str) -> pd.DataFrame:
    """
    Every trading session this recording holds, newest first, with when
    the engine first and last had something to record in each.

    Read from the sessions the engine wrote down rather than from the
    distinct days in a table of fills: a day the engine ran through
    without filling is still a session, and the fills table is the
    largest thing recorded to be asking for distinct values of.
    """
    return _query(
        db_path,
        f"SELECT session_id, MIN(first_seen_at) AS first_seen_at, "
        f"MAX(last_seen_at) AS last_seen_at "
        f'FROM "{SESSION_RUNS}" GROUP BY session_id '
        f"ORDER BY session_id DESC",
        table=SESSION_RUNS,
    )


def latest_session(db_path: str) -> str | None:
    """The session the recording has got as far as, and nothing at all
    for a recording that holds none."""
    found = sessions(db_path)
    return None if found.empty else str(found.iloc[0]["session_id"])


def marks_at(db_path: str, moment: float | None = None) -> pd.Series:
    """
    Returns: The last mid price recorded for each symbol before `moment`,
    indexed by symbol - the latest one of all where no moment is given.

    This is the price convention inventory is valued at on both sides of
    a session: what the market was last seen at, which is the same thing
    the engine marks its own position to.
    """
    at = "" if moment is None else "WHERE timestamp < ?"
    binding = () if moment is None else (moment,)
    rows = _query(
        db_path,
        f"SELECT symbol, (bid_price + ask_price) / 2.0 AS mark "
        f'FROM "{BBO}" WHERE rowid IN '
        f'(SELECT MAX(rowid) FROM "{BBO}" {at} GROUP BY symbol)',
        binding,
        table=BBO,
    )
    if rows.empty:
        return pd.Series(dtype=float)
    return pd.to_numeric(rows.set_index("symbol")["mark"], errors="coerce")


def session_pnl(db_path: str, session_id: str | None = None) -> pd.DataFrame:
    """
    What one trading session earned, per symbol.

        PnL = cash the session's fills moved, fees included
            + inventory held at the close, marked
            - inventory carried in at the open, marked

    Inventory crossing midnight neither earns nor loses anything by
    crossing it: it comes in valued at the opening mark and the move from
    there is this session's. A session that opens holding coin and
    records no fill at all still has a PnL, which is what that inventory
    did while the market moved.

    Both marks are the last mid price recorded on the relevant side of
    the boundary (see `marks_at`). A session still being traded closes at
    the latest mid there is, since its own end has not been reached.
    """
    totals = position_and_cash(db_path, session_id)
    if totals.empty:
        return totals

    if session_id is None:
        opening_mark = pd.Series(dtype=float)
        closing_mark = marks_at(db_path)
    else:
        opens, closes = trading_session_window(session_id)
        opening_mark = marks_at(db_path, opens.timestamp())
        closing_mark = marks_at(db_path, closes.timestamp())

    priced = totals.copy()
    priced["opening_mark"] = priced.index.map(opening_mark)
    priced["mark_price"] = priced.index.map(closing_mark)
    priced["opening_inventory_value"] = priced["opening_position"] * priced[
        "opening_mark"
    ].fillna(0.0)
    priced["inventory_value"] = priced["position"] * priced[
        "mark_price"
    ].fillna(0.0)
    priced["total_pnl"] = (
        priced["net_cash"]
        + priced["inventory_value"]
        - priced["opening_inventory_value"]
    )
    return priced
