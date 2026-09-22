"""Markouts and edge, derived from immutable fills and fair prices.

The engine records execution facts once and records every fair-price
observation separately. Markouts are reconstructed here by timestamp joins:

    fair at fill -> latest selected-model fair price at or before the fill
    future fair  -> first selected-model fair price at or after fill + horizon

Positive values are always favorable to the market maker; negative values
are adverse selection:

    BUY:  value = future_price - execution_price
    SELL: value = execution_price - future_price

`future_price` is the horizon fair price for markout, or the fair price at
fill time for edge.
"""

import pandas as pd

HORIZONS = ("100ms", "1s", "5s", "30s")
HORIZON_SECONDS = {"100ms": 0.1, "1s": 1.0, "5s": 5.0, "30s": 30.0}

# A fair-price observation further from the requested timestamp than this is
# a data gap, not a valid markout sample. BTC/USD normally updates much more
# frequently; keeping the tolerance explicit prevents a reconnect minutes
# later from masquerading as a one-second markout.
DEFAULT_MAX_FAIR_PRICE_LAG_SECONDS = 1.0

# The clock both tables are joined on. SignalRecorder stamps every recorded
# row with its own `now()`, so fills and fair prices share one clock even
# when the venue's own transaction times drift against it.
FILL_TIME = "timestamp"

# Which way a fill points: what a buy pays out, a sell takes in.
SIDE_DIRECTION = {"BUY": 1.0, "SELL": -1.0}

_FILL_COLUMNS = frozenset({FILL_TIME, "symbol", "fair_price_model"})
_FAIR_COLUMNS = frozenset(
    {"timestamp", "symbol", "model", "bid_fair_price", "ask_fair_price"}
)


def horizon_seconds(horizon: str) -> float:
    """Parse an analytics horizon label into seconds.

    Default dashboard horizons use HORIZON_SECONDS, but post-processing may
    ask for a new horizon without changing anything in the trading engine.
    """
    if horizon in HORIZON_SECONDS:
        return HORIZON_SECONDS[horizon]
    try:
        if horizon.endswith("ms"):
            return float(horizon[:-2]) / 1000.0
        if horizon.endswith("s"):
            return float(horizon[:-1])
        if horizon.endswith("m"):
            return float(horizon[:-1]) * 60.0
    except ValueError as error:
        raise ValueError(f"Invalid markout horizon: {horizon}") from error
    raise ValueError(f"Invalid markout horizon: {horizon}")


def observation_tolerance(
    horizon: str, max_lag: float = DEFAULT_MAX_FAIR_PRICE_LAG_SECONDS
) -> float:
    """How far past a horizon an observation may sit and still measure it.

    Capped by the horizon itself: a fair price a full second after the fill
    describes a one-second markout, not a hundred-millisecond one, so
    allowing the flat tolerance everywhere would let the shortest horizons
    silently report a longer one's number.
    """
    return min(max_lag, horizon_seconds(horizon))


def _blank_derived_columns(
    fills: pd.DataFrame, horizons: tuple[str, ...]
) -> pd.DataFrame:
    result = fills.reset_index(drop=True).copy()
    result["fair_price_at_fill"] = float("nan")
    result["fair_price_at_fill_age"] = float("nan")
    for horizon in horizons:
        result[f"fair_price_{horizon}"] = float("nan")
        result[f"markout_lag_{horizon}"] = float("nan")
    return result


def _fair_price_series(fair_prices: pd.DataFrame) -> pd.DataFrame:
    fair = fair_prices.copy()
    fair["timestamp"] = pd.to_numeric(
        fair["timestamp"], errors="coerce"
    ).astype(float)
    fair["fair_mid"] = (
        pd.to_numeric(fair["bid_fair_price"], errors="coerce")
        + pd.to_numeric(fair["ask_fair_price"], errors="coerce")
    ) / 2
    return fair.dropna(subset=["timestamp", "fair_mid", "symbol", "model"])


def _observations_for(fair: pd.DataFrame, symbol: str, model: str):
    columns = ["timestamp", "fair_mid"]
    order = ["timestamp"]
    # Two observations may share a timestamp; breaking the tie by insertion
    # order is what makes merge_asof pick the same one on every run.
    if "_jolteon_rowid" in fair.columns:
        columns.append("_jolteon_rowid")
        order.append("_jolteon_rowid")
    matching = fair["symbol"].eq(symbol) & fair["model"].eq(model)
    return fair.loc[matching, columns].sort_values(order, kind="stable")


def derive_fill_markouts(
    fills: pd.DataFrame,
    fair_prices: pd.DataFrame,
    *,
    horizons: tuple[str, ...] = HORIZONS,
    max_observation_lag: float = DEFAULT_MAX_FAIR_PRICE_LAG_SECONDS,
) -> pd.DataFrame:
    """Return fills enriched with fair-at-fill and future fair prices.

    Each fill names the fair-price model it was quoted against, so a model
    wrapping another leaves two series that are never mixed together.

    At fill, the latest observation at or before the execution is used. At a
    future horizon, the first observation at or after the target is used.
    Matches farther away than `observation_tolerance` allows are left
    missing rather than reported as a horizon they do not measure.
    """
    original_index = fills.index
    result = _blank_derived_columns(fills, horizons)
    if (
        fills.empty
        or fair_prices.empty
        or not _FILL_COLUMNS.issubset(result.columns)
        or not _FAIR_COLUMNS.issubset(fair_prices.columns)
    ):
        result.index = original_index
        return result

    fair = _fair_price_series(fair_prices)
    result[FILL_TIME] = pd.to_numeric(
        result[FILL_TIME], errors="coerce"
    ).astype(float)
    derivable = result.dropna(subset=[FILL_TIME, "symbol", "fair_price_model"])

    for (symbol, model), group in derivable.groupby(
        ["symbol", "fair_price_model"], sort=False
    ):
        prices = _observations_for(fair, str(symbol), str(model))
        if prices.empty:
            continue

        left = pd.DataFrame(
            {"fill_timestamp": group[FILL_TIME], "_fill_row": group.index}
        ).sort_values("fill_timestamp")

        _apply_at_fill(result, left, prices, max_observation_lag)
        for horizon in horizons:
            _apply_horizon(result, left, prices, horizon, max_observation_lag)

    result.index = original_index
    return result


def _apply_at_fill(
    result: pd.DataFrame,
    left: pd.DataFrame,
    prices: pd.DataFrame,
    max_observation_lag: float,
) -> None:
    matched = pd.merge_asof(
        left,
        prices,
        left_on="fill_timestamp",
        right_on="timestamp",
        direction="backward",
    ).set_index("_fill_row")
    age = matched["fill_timestamp"] - matched["timestamp"]
    observed = matched.index[matched["timestamp"].notna()]
    result.loc[observed, "fair_price_at_fill_age"] = age.loc[observed]
    rows = matched.index[age.ge(0) & age.le(max_observation_lag)]
    result.loc[rows, "fair_price_at_fill"] = matched.loc[rows, "fair_mid"]


def _apply_horizon(
    result: pd.DataFrame,
    left: pd.DataFrame,
    prices: pd.DataFrame,
    horizon: str,
    max_observation_lag: float,
) -> None:
    target = left.assign(
        target_timestamp=left["fill_timestamp"] + horizon_seconds(horizon)
    ).sort_values("target_timestamp")
    matched = pd.merge_asof(
        target,
        prices,
        left_on="target_timestamp",
        right_on="timestamp",
        direction="forward",
    ).set_index("_fill_row")
    lag = matched["timestamp"] - matched["target_timestamp"]
    observed = matched.index[matched["timestamp"].notna()]
    result.loc[observed, f"markout_lag_{horizon}"] = lag.loc[observed]
    tolerance = observation_tolerance(horizon, max_observation_lag)
    rows = matched.index[lag.ge(0) & lag.le(tolerance)]
    result.loc[rows, f"fair_price_{horizon}"] = matched.loc[rows, "fair_mid"]


def _signed(fills: pd.DataFrame, execution_price: pd.Series) -> pd.Series:
    direction = fills["side"].map(SIDE_DIRECTION)
    return direction * (execution_price - fills["fill_price"])


def compute_markout(fills: pd.DataFrame, horizon: str) -> pd.Series:
    """Signed USD markout at horizon after each fill.

    NaN wherever no valid fair-price observation exists for that horizon.
    """
    return _signed(fills, fills[f"fair_price_{horizon}"])


def compute_net_markout(markout: pd.Series, fee: pd.Series) -> pd.Series:
    """Markout after subtracting the fee paid on the fill."""
    return markout - fee


def compute_edge(fills: pd.DataFrame) -> pd.Series:
    """Signed USD execution edge: how far the fill price sat from fair
    value at the moment of execution, in the market maker's favor."""
    return _signed(fills, fills["fair_price_at_fill"])


def compute_fill_edge(fills: pd.DataFrame) -> pd.Series:
    """Total USD edge kept on each fill: the per-unit edge scaled by how
    much was traded, less the fee paid to trade it."""
    return compute_edge(fills) * fills["fill_qty"] - fills["fee"]


def usd_to_bps(usd: pd.Series, execution_price: pd.Series) -> pd.Series:
    """A USD amount as basis points of the execution price."""
    return usd / execution_price * 10_000
