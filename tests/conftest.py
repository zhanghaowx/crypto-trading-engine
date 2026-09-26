import sys
from contextlib import closing

import pytest
from blinker import ANY

from jolteon.engine.core.event.signal import signal_namespace


# each test runs on cwd to its temp dir
@pytest.fixture(autouse=True)
def go_to_tmpdir(request):
    # Get the fixture dynamically by its name.
    tmpdir = request.getfixturevalue("tmpdir")
    # ensure local test created packages can be imported
    sys.path.insert(0, str(tmpdir))
    # Chdir only for the duration of the test.
    with tmpdir.as_cwd():
        yield


@pytest.fixture(autouse=True)
def disconnect_all_signals():
    """Blinker signals are process-global, so a test that connects a
    receiver and forgets to disconnect it can leak into a later test -
    only visible in a full suite run, not in isolation, since it depends
    on GC timing. No test relies on a signal connection surviving across
    tests, so disconnect everything unconditionally after each one."""
    yield
    for named_signal in signal_namespace.values():
        for receiver in list(named_signal.receivers_for(ANY)):
            named_signal.disconnect(receiver)


@pytest.fixture
def replay_dataset(tmp_path):
    """Tiny complete external recording and fully explicit experiment input."""
    import json
    import sqlite3
    from dataclasses import asdict
    from datetime import datetime, timezone

    from jolteon.engine.core.parameter.parameter_catalog import GROUPS
    from jolteon.engine.market_data.core.instrument import InstrumentSpec

    start = datetime(2026, 1, 1, tzinfo=timezone.utc).timestamp()
    path = tmp_path / "source.sqlite"
    with closing(sqlite3.connect(path)) as conn, conn:
        conn.execute(
            "CREATE TABLE engine_run (run_id, exchange, symbol, "
            "started_at, ended_at)"
        )
        conn.execute(
            "INSERT INTO engine_run VALUES ('source', "
            "'Binance.US', 'BTC/USD', ?, ?)",
            (start, start + 1),
        )
        conn.execute("CREATE TABLE heartbeat (run_id, timestamp)")
        conn.execute(
            "INSERT INTO heartbeat VALUES ('source', ?)", (start + 1,)
        )
        conn.execute(
            "CREATE TABLE order_book_update_feed (run_id, "
            "timestamp, symbol, model, version, sequence, bids, "
            "asks, is_snapshot, exchange_time)"
        )
        conn.execute(
            "INSERT INTO order_book_update_feed VALUES ('source', "
            "?, 'BTC/USD', 'l2', 1, 1, ?, ?, 1, ?)",
            (start, json.dumps([[90, 1]]), json.dumps([[110, 1]]), start),
        )
        conn.execute(
            "CREATE TABLE bbo_feed (run_id, timestamp, symbol, "
            "bid_price, bid_quantity, ask_price, ask_quantity)"
        )
        conn.executemany(
            "INSERT INTO bbo_feed VALUES ('source', ?, 'BTC/USD', ?, 1, ?, 1)",
            [
                (start + 0.001, 90, 110),
                (start + 0.015, 90, 110),
                (start + 0.025, 91, 111),
            ],
        )
        conn.execute(
            "CREATE TABLE market_trade_feed (run_id, timestamp, "
            "symbol, exchange_trade_id, side, price, quantity, "
            "transaction_time)"
        )
        conn.executemany(
            "INSERT INTO market_trade_feed VALUES ('source', ?, "
            "'BTC/USD', ?, ?, ?, ?, ?)",
            [
                (start + 0.01, 1, "SELL", 95, 0.0002, start + 0.01),
                (start + 0.02, 2, "BUY", 105, 0.0005, start + 0.02),
                (start + 0.03, 3, "SELL", 96, 0.0005, start + 0.03),
            ],
        )
    config = {group.__name__: asdict(group()) for group in GROUPS}
    for name in ("MomentumParameters", "OrderFlowImbalanceParameters"):
        config[name]["scale"] = 0.0
    config["InventoryAdjustmentParameters"]["skew_at_max_inventory"] = 0.0
    manifest = {
        "schema_version": 1,
        "source": {
            "path": str(path),
            "source_run_id": "source",
            "allow_gaps": False,
        },
        "market": {"exchange": "Binance.US", "symbol": "BTC/USD"},
        "interval": {
            "start": datetime.fromtimestamp(start, timezone.utc).isoformat(),
            "end": datetime.fromtimestamp(
                start + 0.04, timezone.utc
            ).isoformat(),
            "bounds": "[start,end)",
        },
        "configuration": {"mode": "fixed", "parameters": {"": config}},
        "initialization": {
            "policy": "flat-await-inputs",
            "instrument_override": {
                "reason": "Synthetic fixture rules",
                "specification": asdict(
                    InstrumentSpec(
                        "BTC/USD", "BTC", "USD", 2, 5, 0.01, 0.00001, 0.0
                    )
                ),
            },
        },
        "execution_simulation": {"model": "current-mock-v1", "latency": None},
        "playback": {"speed": "unbounded"},
    }
    return path, manifest


@pytest.fixture
def native_replay_dataset(replay_dataset):
    """A complete synthetic recording with original external-event order."""
    import sqlite3

    source, document = replay_dataset
    spec = document["initialization"]["instrument_override"]["specification"]
    with closing(sqlite3.connect(source)) as conn, conn:
        pending = []
        for table in (
            "order_book_update_feed",
            "bbo_feed",
            "market_trade_feed",
        ):
            conn.execute(f"ALTER TABLE {table} ADD COLUMN external_sequence")
            pending.extend(
                (ts, table, rowid)
                for rowid, ts in conn.execute(
                    f"SELECT rowid,timestamp FROM {table}"
                )
            )
        for sequence, (_, table, rowid) in enumerate(sorted(pending), 2):
            conn.execute(
                f"UPDATE {table} SET external_sequence=? WHERE rowid=?",
                (sequence, rowid),
            )
        columns = ", ".join(spec)
        conn.execute(
            f"CREATE TABLE instrument_feed "
            f"(run_id, timestamp, external_sequence, {columns})"
        )
        conn.execute(
            "INSERT INTO instrument_feed VALUES ("
            + ",".join("?" for _ in range(len(spec) + 3))
            + ")",
            ("source", 1767225600, 1, *spec.values()),
        )
    document["initialization"]["instrument_override"] = None
    return source, document
