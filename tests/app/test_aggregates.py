import sqlite3
from pathlib import Path

import pandas as pd
import pytest

from jolteon.app import aggregates
from jolteon.app.analytics import HORIZONS

SESSION = "2023-11-14"

_COLUMNS = (
    "side TEXT, fill_price REAL, fair_price_at_fill REAL, fee REAL, "
    "fill_qty REAL, inventory_before REAL, symbol TEXT, session_id TEXT, "
    + ", ".join(f"fair_price_{h} REAL" for h in HORIZONS)
)


def _fill(
    side,
    price,
    fair,
    fee,
    qty,
    inventory,
    at_1s=None,
    symbol="BTC-USD",
    session=SESSION,
):
    return (
        side,
        price,
        fair,
        fee,
        qty,
        inventory,
        symbol,
        session,
        *[at_1s if h == "1s" else None for h in HORIZONS],
    )


def _recording(tmp_path, fills, name="fills.sqlite") -> str:
    db_path = str(Path(tmp_path) / name)
    conn = sqlite3.connect(db_path)
    try:
        conn.execute(f"CREATE TABLE decorated_order_fill ({_COLUMNS})")
        conn.executemany(
            "INSERT INTO decorated_order_fill VALUES "
            f"({', '.join('?' * (8 + len(HORIZONS)))})",
            fills,
        )
        conn.commit()
    finally:
        conn.close()
    return db_path


def _record_sessions(db_path: str, session_runs) -> None:
    """The sessions an engine traded, as it writes them down: one row per
    session and run, with when it first and last had something to
    record."""
    conn = sqlite3.connect(db_path)
    try:
        conn.execute(
            "CREATE TABLE trading_session_run "
            "(session_run_id TEXT PRIMARY KEY, session_id TEXT, "
            "run_id TEXT, exchange TEXT, symbol TEXT, "
            "first_seen_at REAL, last_seen_at REAL)"
        )
        conn.executemany(
            "INSERT INTO trading_session_run VALUES (?,?,?,?,?,?,?)",
            [
                (
                    f"{session}@{run}",
                    session,
                    run,
                    "Kraken",
                    "BTC-USD",
                    first,
                    last,
                )
                for session, run, first, last in session_runs
            ],
        )
        conn.commit()
    finally:
        conn.close()


def _record_bbo(db_path: str, ticks) -> None:
    """Mid prices as `(timestamp, mid)`, the last of which before a
    moment is what inventory is marked at."""
    conn = sqlite3.connect(db_path)
    try:
        conn.execute(
            "CREATE TABLE bbo_feed "
            "(timestamp REAL, symbol TEXT, bid_price REAL, ask_price REAL)"
        )
        conn.executemany(
            "INSERT INTO bbo_feed VALUES (?, 'BTC-USD', ?, ?)",
            [(at, mid - 0.5, mid + 0.5) for at, mid in ticks],
        )
        conn.commit()
    finally:
        conn.close()


def test_fill_quality_splits_buy_from_sell(tmp_path):
    db_path = _recording(
        tmp_path,
        [
            _fill("BUY", 100.0, 101.0, 0.1, 1.0, 0.0, at_1s=103.0),
            _fill("BUY", 100.0, 99.0, 0.2, 1.0, 0.0, at_1s=97.0),
            _fill("SELL", 110.0, 108.0, 0.05, 1.0, 0.0, at_1s=105.0),
        ],
    )

    by_side = aggregates.fill_quality_by_side(db_path)

    assert by_side.loc["BUY", "fill_count"] == 2
    assert by_side.loc["BUY", "avg_edge"] == pytest.approx(0.0)
    assert by_side.loc["BUY", "avg_fee"] == pytest.approx(0.15)
    assert by_side.loc["BUY", "avg_markout_1s"] == pytest.approx(0.0)
    assert by_side.loc["BUY", "avg_net_markout_1s"] == pytest.approx(-0.15)

    assert by_side.loc["SELL", "fill_count"] == 1
    assert by_side.loc["SELL", "avg_edge"] == pytest.approx(2.0)
    assert by_side.loc["SELL", "avg_markout_1s"] == pytest.approx(5.0)
    assert by_side.loc["SELL", "avg_net_markout_1s"] == pytest.approx(4.95)


def test_a_horizon_that_has_not_resolved_is_missing_not_zero(tmp_path):
    """A markout only arrives once its horizon has passed. Counting the
    fills still waiting as zero would drag every average towards it."""
    db_path = _recording(
        tmp_path, [_fill("BUY", 100.0, 100.0, 0.1, 1.0, 0.0, at_1s=None)]
    )

    by_side = aggregates.fill_quality_by_side(db_path)

    assert pd.isna(by_side.loc["BUY", "avg_markout_1s"])


def test_inventory_buckets_are_read_short_through_long(tmp_path):
    db_path = _recording(
        tmp_path,
        [
            _fill("BUY", 100.0, 100.0, 0.1, 1.0, -0.6, at_1s=103.0),
            _fill("SELL", 100.0, 100.0, 0.2, 1.0, 0.0, at_1s=98.0),
            _fill("BUY", 100.0, 100.0, 0.1, 1.0, 0.9, at_1s=100.0),
        ],
    )

    buckets = aggregates.inventory_buckets(db_path)

    assert list(buckets.index) == [
        "Strongly short",
        "Near neutral",
        "Strongly long",
    ]
    assert buckets.loc["Strongly short", "fill_count"] == 1
    assert buckets.loc["Strongly short", "buy_count"] == 1
    assert buckets.loc["Strongly short", "sell_count"] == 0
    assert buckets.loc["Strongly short", "avg_markout_1s"] == pytest.approx(
        3.0
    )
    assert buckets.loc["Strongly short", "net_cash_flow"] == pytest.approx(
        -100.1
    )
    assert buckets.loc["Near neutral", "net_cash_flow"] == pytest.approx(99.8)


def test_a_fill_without_the_position_held_before_it_joins_no_bucket(tmp_path):
    """A bucket says how we traded while holding that much, so a fill
    recorded without that belongs to none of them - rather than falling
    through every bound into the extreme one."""
    db_path = _recording(
        tmp_path, [_fill("BUY", 100.0, 100.0, 0.1, 1.0, None)]
    )

    assert aggregates.inventory_buckets(db_path).empty


def test_position_and_cash_sum_over_every_fill(tmp_path):
    db_path = _recording(
        tmp_path,
        [
            _fill("BUY", 100.0, 100.0, 0.1, 2.0, 0.0),
            _fill("SELL", 110.0, 110.0, 0.2, 1.0, 0.0),
            _fill("BUY", 50.0, 50.0, 0.05, 1.0, 0.0, symbol="ETH-USD"),
        ],
    )

    totals = aggregates.position_and_cash(db_path)

    assert totals.loc["BTC-USD", "position"] == pytest.approx(1.0)
    # -200 paid, +110 received, 0.30 of fees.
    assert totals.loc["BTC-USD", "net_cash"] == pytest.approx(-90.3)
    assert totals.loc["ETH-USD", "position"] == pytest.approx(1.0)
    assert totals.loc["ETH-USD", "net_cash"] == pytest.approx(-50.05)


def test_fees_and_presence_are_asked_of_the_recording(tmp_path):
    db_path = _recording(
        tmp_path,
        [
            _fill("BUY", 100.0, 100.0, 0.1, 1.0, 0.0),
            _fill("SELL", 100.0, 100.0, 0.25, 1.0, 0.0),
        ],
    )

    assert aggregates.any_fills(db_path)
    assert aggregates.total_fees(db_path) == pytest.approx(0.35)


def test_fair_price_movement_is_side_independent(tmp_path):
    db_path = _recording(
        tmp_path,
        [
            _fill("BUY", 100.0, 101.0, 0.1, 1.0, 0.0, at_1s=103.0),
            _fill("SELL", 100.0, 99.0, 0.1, 1.0, 0.0, at_1s=97.0),
        ],
    )

    moved = aggregates.avg_fair_price_movement(db_path)

    # +2 and -2 either side of the fair price it was filled at.
    assert moved["1s"] == pytest.approx(0.0)
    assert pd.isna(moved["30s"])


def test_a_recording_with_no_fills_answers_with_nothing(tmp_path):
    db_path = _recording(tmp_path, [])

    assert not aggregates.any_fills(db_path)
    assert aggregates.total_fees(db_path) == 0.0
    assert aggregates.fill_quality_by_side(db_path).empty
    assert aggregates.inventory_buckets(db_path).empty
    assert aggregates.position_and_cash(db_path).empty
    assert aggregates.avg_fair_price_movement(db_path).isna().all()


def test_a_recording_without_the_columns_answers_with_nothing(tmp_path):
    """An older recording may not have the columns a newer payload
    writes, and a card that cannot be drawn should draw nothing rather
    than take the page down."""
    db_path = str(Path(tmp_path) / "old.sqlite")
    conn = sqlite3.connect(db_path)
    try:
        conn.execute("CREATE TABLE decorated_order_fill (side TEXT)")
        conn.execute("INSERT INTO decorated_order_fill VALUES ('BUY')")
        conn.commit()
    finally:
        conn.close()

    assert aggregates.fill_quality_by_side(db_path).empty
    assert aggregates.inventory_buckets(db_path).empty
    assert aggregates.position_and_cash(db_path).empty
    assert aggregates.total_fees(db_path) == 0.0


def test_a_recording_that_is_not_there_answers_with_nothing(tmp_path):
    missing = str(Path(tmp_path) / "absent.sqlite")

    assert not aggregates.any_fills(missing)
    assert aggregates.fill_quality_by_side(missing).empty
    assert aggregates.total_fees(missing) == 0.0


YESTERDAY = "2023-11-13"
TODAY = "2023-11-14"

# Midnight UTC opening each of those days, which is where a session's
# opening and closing marks are read from.
_OPENS = {
    YESTERDAY: 1699833600.0,
    TODAY: 1699920000.0,
    "2023-11-15": 1700006400.0,
}


def _two_day_recording(tmp_path, fills, ticks=(), name="two-days.sqlite"):
    db_path = _recording(tmp_path, fills, name=name)
    _record_sessions(
        db_path,
        [
            (YESTERDAY, "run-a", _OPENS[YESTERDAY], _OPENS[TODAY]),
            (TODAY, "run-b", _OPENS[TODAY], _OPENS["2023-11-15"]),
        ],
    )
    if ticks:
        _record_bbo(db_path, ticks)
    return db_path


class TestSessionScope:
    """A recording holding two days must not answer for both when one is
    asked about."""

    def _recording(self, tmp_path):
        return _two_day_recording(
            tmp_path,
            [
                _fill("BUY", 100.0, 101.0, 0.1, 1.0, 0.0, session=YESTERDAY),
                _fill("SELL", 110.0, 108.0, 0.2, 1.0, 1.0, session=TODAY),
                _fill("SELL", 112.0, 110.0, 0.3, 1.0, 0.0, session=TODAY),
            ],
        )

    def test_fill_quality_counts_only_the_session_asked_about(self, tmp_path):
        db_path = self._recording(tmp_path)

        by_side = aggregates.fill_quality_by_side(db_path, TODAY)

        assert "BUY" not in by_side.index
        assert by_side.loc["SELL", "fill_count"] == 2

    def test_fees_count_only_the_session_asked_about(self, tmp_path):
        db_path = self._recording(tmp_path)

        assert aggregates.total_fees(db_path, TODAY) == pytest.approx(0.5)
        assert aggregates.total_fees(db_path, YESTERDAY) == pytest.approx(0.1)
        assert aggregates.total_fees(db_path) == pytest.approx(0.6)

    def test_a_session_with_no_fill_of_its_own_holds_none(self, tmp_path):
        db_path = self._recording(tmp_path)

        assert not aggregates.any_fills(db_path, "2023-11-15")
        assert aggregates.any_fills(db_path, TODAY)

    def test_inventory_buckets_count_only_the_session_asked_about(
        self, tmp_path
    ):
        db_path = self._recording(tmp_path)

        buckets = aggregates.inventory_buckets(db_path, TODAY)

        assert buckets["fill_count"].sum() == 2

    def test_fair_price_movement_covers_only_the_session_asked_about(
        self, tmp_path
    ):
        db_path = _two_day_recording(
            tmp_path,
            [
                _fill(
                    "BUY",
                    100.0,
                    100.0,
                    0.0,
                    1.0,
                    0.0,
                    at_1s=110.0,
                    session=YESTERDAY,
                ),
                _fill(
                    "BUY",
                    100.0,
                    100.0,
                    0.0,
                    1.0,
                    0.0,
                    at_1s=102.0,
                    session=TODAY,
                ),
            ],
            name="movement.sqlite",
        )

        moved = aggregates.avg_fair_price_movement(db_path, TODAY)

        assert moved["1s"] == pytest.approx(2.0)

    def test_a_restart_inside_one_day_does_not_split_its_figures(
        self, tmp_path
    ):
        """Two engine runs, one trading session: the day's fills add up
        across the restart rather than being counted as two days."""
        db_path = _recording(
            tmp_path,
            [
                _fill("BUY", 100.0, 101.0, 0.1, 1.0, 0.0, session=TODAY),
                _fill("SELL", 110.0, 108.0, 0.2, 1.0, 1.0, session=TODAY),
            ],
            name="restart.sqlite",
        )
        _record_sessions(
            db_path,
            [
                (TODAY, "morning", _OPENS[TODAY], _OPENS[TODAY] + 3600),
                (
                    TODAY,
                    "afternoon",
                    _OPENS[TODAY] + 7200,
                    _OPENS[TODAY] + 9000,
                ),
            ],
        )

        assert list(aggregates.sessions(db_path)["session_id"]) == [TODAY]
        assert aggregates.total_fees(db_path, TODAY) == pytest.approx(0.3)


class TestSessions:
    def test_the_sessions_a_recording_holds_are_newest_first(self, tmp_path):
        db_path = _two_day_recording(tmp_path, [])

        assert list(aggregates.sessions(db_path)["session_id"]) == [
            TODAY,
            YESTERDAY,
        ]
        assert aggregates.latest_session(db_path) == TODAY

    def test_a_recording_holding_no_session_names_none(self, tmp_path):
        db_path = _recording(tmp_path, [], name="sessionless.sqlite")

        assert aggregates.sessions(db_path).empty
        assert aggregates.latest_session(db_path) is None


class TestMarks:
    def test_inventory_is_marked_at_the_last_price_before_the_moment(
        self, tmp_path
    ):
        db_path = _recording(tmp_path, [], name="marks.sqlite")
        _record_bbo(
            db_path,
            [
                (_OPENS[YESTERDAY] + 60, 100.0),
                (_OPENS[TODAY] - 60, 105.0),
                (_OPENS[TODAY] + 60, 130.0),
            ],
        )

        assert aggregates.marks_at(db_path, _OPENS[TODAY])[
            "BTC-USD"
        ] == pytest.approx(105.0)
        assert aggregates.marks_at(db_path)["BTC-USD"] == pytest.approx(130.0)

    def test_a_recording_with_no_prices_marks_nothing(self, tmp_path):
        db_path = _recording(tmp_path, [], name="unpriced.sqlite")

        assert aggregates.marks_at(db_path).empty


class TestSessionPnL:
    """Inventory crossing midnight must neither earn nor lose anything by
    crossing it, so every one of these prices the day it opened on as
    well as the day it closed on."""

    def _priced(self, tmp_path, fills, name):
        """A two-day recording marked at 100 through yesterday and 130
        through today."""
        return _two_day_recording(
            tmp_path,
            fills,
            ticks=[
                (_OPENS[YESTERDAY] + 60, 100.0),
                (_OPENS[TODAY] - 60, 100.0),
                (_OPENS[TODAY] + 60, 130.0),
            ],
            name=name,
        )

    def test_a_session_that_opens_and_closes_flat(self, tmp_path):
        db_path = self._priced(
            tmp_path,
            [
                _fill("BUY", 100.0, 100.0, 0.1, 1.0, 0.0, session=TODAY),
                _fill("SELL", 110.0, 110.0, 0.2, 1.0, 1.0, session=TODAY),
            ],
            "flat.sqlite",
        )

        today = aggregates.session_pnl(db_path, TODAY).loc["BTC-USD"]

        assert today["opening_position"] == pytest.approx(0.0)
        assert today["position"] == pytest.approx(0.0)
        # Sold ten dollars above cost, less thirty cents of fees.
        assert today["total_pnl"] == pytest.approx(9.7)

    def test_a_session_that_opens_flat_and_ends_holding(self, tmp_path):
        db_path = self._priced(
            tmp_path,
            [_fill("BUY", 100.0, 100.0, 0.0, 1.0, 0.0, session=TODAY)],
            "holding.sqlite",
        )

        today = aggregates.session_pnl(db_path, TODAY).loc["BTC-USD"]

        assert today["opening_inventory_value"] == pytest.approx(0.0)
        # Bought at 100 and the coin is worth 130 by the close.
        assert today["inventory_value"] == pytest.approx(130.0)
        assert today["total_pnl"] == pytest.approx(30.0)

    def test_a_session_carrying_inventory_in_and_filling_nothing(
        self, tmp_path
    ):
        """The day the position was bought earns nothing more for holding
        it, and the day that inherits it earns what the market did."""
        db_path = self._priced(
            tmp_path,
            [_fill("BUY", 100.0, 100.0, 0.0, 1.0, 0.0, session=YESTERDAY)],
            "carried.sqlite",
        )

        today = aggregates.session_pnl(db_path, TODAY).loc["BTC-USD"]

        assert today["opening_position"] == pytest.approx(1.0)
        assert today["position"] == pytest.approx(1.0)
        assert today["net_cash"] == pytest.approx(0.0)
        assert today["opening_inventory_value"] == pytest.approx(100.0)
        assert today["inventory_value"] == pytest.approx(130.0)
        assert today["total_pnl"] == pytest.approx(30.0)

    def test_carrying_inventory_across_midnight_creates_no_pnl(self, tmp_path):
        """What the two days earn apart is what the whole recording
        earns together - the boundary itself is worth nothing."""
        db_path = self._priced(
            tmp_path,
            [_fill("BUY", 100.0, 100.0, 0.0, 1.0, 0.0, session=YESTERDAY)],
            "conserved.sqlite",
        )

        yesterday = aggregates.session_pnl(db_path, YESTERDAY).loc["BTC-USD"]
        today = aggregates.session_pnl(db_path, TODAY).loc["BTC-USD"]
        whole = aggregates.session_pnl(db_path).loc["BTC-USD"]

        assert yesterday["total_pnl"] + today["total_pnl"] == pytest.approx(
            whole["total_pnl"]
        )

    def test_a_session_that_trades_part_of_its_inventory_back_out(
        self, tmp_path
    ):
        db_path = self._priced(
            tmp_path,
            [
                _fill("BUY", 100.0, 100.0, 0.0, 2.0, 0.0, session=YESTERDAY),
                _fill("SELL", 130.0, 130.0, 0.0, 1.0, 2.0, session=TODAY),
            ],
            "partial.sqlite",
        )

        today = aggregates.session_pnl(db_path, TODAY).loc["BTC-USD"]

        assert today["opening_position"] == pytest.approx(2.0)
        assert today["position"] == pytest.approx(1.0)
        # Sold one at 130, carried two in at 100, holds one worth 130.
        assert today["net_cash"] == pytest.approx(130.0)
        assert today["opening_inventory_value"] == pytest.approx(200.0)
        assert today["inventory_value"] == pytest.approx(130.0)
        assert today["total_pnl"] == pytest.approx(60.0)

    def test_a_session_whose_position_crosses_from_long_to_short(
        self, tmp_path
    ):
        db_path = self._priced(
            tmp_path,
            [
                _fill("BUY", 100.0, 100.0, 0.0, 1.0, 0.0, session=YESTERDAY),
                _fill("SELL", 130.0, 130.0, 0.0, 3.0, 1.0, session=TODAY),
            ],
            "crossed.sqlite",
        )

        today = aggregates.session_pnl(db_path, TODAY).loc["BTC-USD"]

        assert today["opening_position"] == pytest.approx(1.0)
        assert today["position"] == pytest.approx(-2.0)
        assert today["inventory_value"] == pytest.approx(-260.0)
        assert today["total_pnl"] == pytest.approx(30.0)

    def test_a_recording_with_no_fills_has_no_pnl_to_report(self, tmp_path):
        db_path = _two_day_recording(tmp_path, [], name="empty-pnl.sqlite")

        assert aggregates.session_pnl(db_path, TODAY).empty


def _record_runs(db_path: str, runs) -> None:
    """The engine runs a recording holds, as `(run_id, started, ended)`."""
    conn = sqlite3.connect(db_path)
    try:
        conn.execute(
            "CREATE TABLE engine_run "
            "(run_id TEXT PRIMARY KEY, exchange TEXT, symbol TEXT, "
            "started_at REAL, ended_at REAL)"
        )
        conn.executemany(
            "INSERT INTO engine_run VALUES (?, 'Kraken', 'BTC-USD', ?, ?)",
            runs,
        )
        conn.commit()
    finally:
        conn.close()


class TestEngineRuns:
    def test_a_session_shows_every_run_that_traded_it(self, tmp_path):
        db_path = _recording(tmp_path, [], name="runs.sqlite")
        _record_sessions(
            db_path,
            [
                (TODAY, "morning", _OPENS[TODAY], _OPENS[TODAY] + 3600),
                (
                    TODAY,
                    "afternoon",
                    _OPENS[TODAY] + 7200,
                    _OPENS[TODAY] + 9000,
                ),
                (YESTERDAY, "morning", _OPENS[YESTERDAY], _OPENS[TODAY]),
            ],
        )
        _record_runs(
            db_path,
            [
                ("morning", _OPENS[YESTERDAY], None),
                ("afternoon", _OPENS[TODAY] + 7200, _OPENS[TODAY] + 9000),
            ],
        )

        runs = aggregates.engine_runs(db_path, TODAY)

        assert list(runs["run_id"]) == ["morning", "afternoon"]

    def test_a_run_that_never_recorded_its_end_says_so(self, tmp_path):
        db_path = _recording(tmp_path, [], name="killed.sqlite")
        _record_sessions(
            db_path, [(TODAY, "killed", _OPENS[TODAY], _OPENS[TODAY] + 60)]
        )
        _record_runs(db_path, [("killed", _OPENS[TODAY], None)])

        runs = aggregates.engine_runs(db_path, TODAY)

        assert pd.isna(runs.loc[0, "ended_at"])

    def test_a_run_spanning_midnight_belongs_to_both_days(self, tmp_path):
        db_path = _recording(tmp_path, [], name="spanning.sqlite")
        _record_sessions(
            db_path,
            [
                (YESTERDAY, "overnight", _OPENS[YESTERDAY], _OPENS[TODAY]),
                (TODAY, "overnight", _OPENS[TODAY], _OPENS[TODAY] + 3600),
            ],
        )
        _record_runs(db_path, [("overnight", _OPENS[YESTERDAY], None)])

        assert list(aggregates.engine_runs(db_path, YESTERDAY)["run_id"]) == [
            "overnight"
        ]
        assert list(aggregates.engine_runs(db_path, TODAY)["run_id"]) == [
            "overnight"
        ]

    def test_a_session_nothing_traded_shows_no_run(self, tmp_path):
        db_path = _two_day_recording(tmp_path, [], name="quiet.sqlite")

        assert aggregates.engine_runs(db_path, "2023-11-15").empty
