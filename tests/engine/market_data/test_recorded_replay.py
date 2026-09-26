import hashlib
import sqlite3
from contextlib import closing

import pytest

from jolteon.engine.core.replay_manifest import ReplayManifest
from jolteon.engine.market_data.recorded_replay import RecordedReplay


def test_read_only_hash_and_gaps(replay_dataset, tmp_path):
    source, document = replay_dataset
    before = hashlib.sha256(source.read_bytes()).hexdigest()
    manifest = ReplayManifest.parse(document, tmp_path)
    one = RecordedReplay.read(manifest)
    assert one.counts["market_trade_feed"] == 3
    assert one.input_hash == RecordedReplay.read(manifest).input_hash
    assert hashlib.sha256(source.read_bytes()).hexdigest() == before
    with closing(sqlite3.connect(source)) as conn, conn:
        conn.execute(
            "UPDATE market_trade_feed SET exchange_trade_id=5 "
            "WHERE exchange_trade_id=3"
        )
    with pytest.raises(ValueError, match="Sequence gap"):
        RecordedReplay.read(manifest)
    document["source"]["allow_gaps"] = True
    changed = RecordedReplay.read(ReplayManifest.parse(document, tmp_path))
    assert changed.input_hash != one.input_hash
    assert any("gap" in reason for reason in changed.limitations)


@pytest.mark.parametrize(
    "sql,expected",
    [
        ("DROP TABLE bbo_feed", "Required replay input"),
        ("DELETE FROM engine_run", "uniquely"),
        ("DELETE FROM order_book_update_feed", "snapshot"),
        ("DELETE FROM market_trade_feed", "no events"),
        ("UPDATE order_book_update_feed SET version=2", "Unsupported"),
        ("UPDATE order_book_update_feed SET bids='[[-1,2]]'", "Invalid book"),
        ("DELETE FROM heartbeat", "cover interval end"),
    ],
)
def test_invalid_source(replay_dataset, tmp_path, sql, expected):
    source, document = replay_dataset
    with closing(sqlite3.connect(source)) as conn, conn:
        conn.execute(sql)
    with pytest.raises(ValueError, match=expected):
        RecordedReplay.read(ReplayManifest.parse(document, tmp_path))


def test_recorded_parameters_and_revisions(replay_dataset, tmp_path):
    source, document = replay_dataset
    params = document["configuration"]["parameters"]
    with closing(sqlite3.connect(source)) as conn, conn:
        conn.execute(
            "CREATE TABLE run_parameter (run_id, symbol, "
            "group_name, field_name, value)"
        )
        conn.execute(
            "CREATE TABLE accepted_parameter_revision (run_id, "
            "symbol, group_name, field_name, value, revision, "
            "effective_at)"
        )
        for symbol, groups in params.items():
            for group, fields in groups.items():
                for field, value in fields.items():
                    conn.execute(
                        "INSERT INTO run_parameter VALUES (?, ?, ?, ?, ?)",
                        ("source", symbol, group, field, value),
                    )
                    conn.execute(
                        "INSERT INTO accepted_parameter_revision "
                        "VALUES (?, ?, ?, ?, ?, ?, ?)",
                        (
                            "source",
                            symbol,
                            group,
                            field,
                            value,
                            1,
                            1767225600.02,
                        ),
                    )
    document["configuration"] = {"mode": "recorded"}
    manifest = ReplayManifest.parse(document, tmp_path)
    recording = RecordedReplay.read(manifest)
    assert recording.parameters == params
    assert recording.revisions[0]["revision"] == 1
    with closing(sqlite3.connect(source)) as conn, conn:
        conn.execute(
            "UPDATE accepted_parameter_revision SET "
            "effective_at=0 WHERE field_name=?",
            ("scale",),
        )
    with pytest.raises(ValueError, match="conflicting"):
        RecordedReplay.read(manifest)
    with closing(sqlite3.connect(source)) as conn, conn:
        conn.execute("DROP TABLE accepted_parameter_revision")
    with pytest.raises(ValueError, match="revision history"):
        RecordedReplay.read(manifest)
    with closing(sqlite3.connect(source)) as conn, conn:
        conn.execute(
            "INSERT INTO run_parameter SELECT * FROM run_parameter LIMIT 1"
        )
    with pytest.raises(ValueError, match="Duplicate"):
        RecordedReplay.read(manifest)


def test_opening_instrument_and_interval(replay_dataset, tmp_path):
    source, document = replay_dataset
    spec = document["initialization"]["instrument_override"]["specification"]
    with closing(sqlite3.connect(source)) as conn, conn:
        names = ", ".join(spec)
        conn.execute(
            f"CREATE TABLE instrument_feed (run_id, timestamp, {names})"
        )
        conn.execute(
            "INSERT INTO instrument_feed VALUES ("
            + ",".join("?" for _ in range(len(spec) + 2))
            + ")",
            ("source", 1767225600, *spec.values()),
        )
    document["initialization"]["instrument_override"] = None
    manifest = ReplayManifest.parse(document, tmp_path)
    assert len(RecordedReplay.read(manifest).limitations) == 1
    with closing(sqlite3.connect(source)) as conn, conn:
        conn.execute("UPDATE instrument_feed SET price_increment=0")
    with pytest.raises(ValueError, match="increment"):
        RecordedReplay.read(manifest)
    with closing(sqlite3.connect(source)) as conn, conn:
        conn.execute("UPDATE instrument_feed SET timestamp=9999999999")
    with pytest.raises(ValueError, match="instrument"):
        RecordedReplay.read(manifest)
    document["interval"]["start"] = "2025-12-31T23:00:00Z"
    with pytest.raises(ValueError, match="before source run"):
        RecordedReplay.read(ReplayManifest.parse(document, tmp_path))
    document["interval"]["start"] = "2026-01-01T00:00:00Z"
    document["interval"]["end"] = "2026-01-02T00:00:00Z"
    with pytest.raises(ValueError, match="beyond completed"):
        RecordedReplay.read(ReplayManifest.parse(document, tmp_path))


def test_snapshot_arrives_after_start(replay_dataset, tmp_path):
    source, document = replay_dataset
    with closing(sqlite3.connect(source)) as conn, conn:
        conn.execute(
            "UPDATE order_book_update_feed SET timestamp=timestamp+0.0001"
        )
    recording = RecordedReplay.read(ReplayManifest.parse(document, tmp_path))
    assert recording.events[0].channel == "instrument_feed"
    assert recording.events[1].channel == "order_book_update_feed"


def test_native_external_order_and_instrument_changes(
    replay_dataset, tmp_path
):
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
            f"CREATE TABLE instrument_feed (run_id, timestamp, "
            f"external_sequence, {columns})"
        )
        conn.execute(
            "INSERT INTO instrument_feed VALUES ("
            + ",".join("?" for _ in range(len(spec) + 3))
            + ")",
            ("source", 1767225600.035, len(pending) + 2, *spec.values()),
        )
    manifest = ReplayManifest.parse(document, tmp_path)
    recording = RecordedReplay.read(manifest)
    assert recording.ordering_policy == "external-sequence-v1"
    assert recording.counts["instrument_feed"] == 2
    with closing(sqlite3.connect(source)) as conn, conn:
        conn.execute("UPDATE bbo_feed SET external_sequence=2")
    with pytest.raises(ValueError, match="sequence contradicts"):
        RecordedReplay.read(manifest)


@pytest.mark.parametrize(
    "sql,expected",
    [
        ("UPDATE bbo_feed SET bid_price=999", "Invalid BBO"),
        ("UPDATE market_trade_feed SET quantity=-1", "Invalid market trade"),
    ],
)
def test_invalid_market_values(replay_dataset, tmp_path, sql, expected):
    source, document = replay_dataset
    with closing(sqlite3.connect(source)) as conn, conn:
        conn.execute(sql)
    with pytest.raises(ValueError, match=expected):
        RecordedReplay.read(ReplayManifest.parse(document, tmp_path))


def test_recorded_feed_health_gap(replay_dataset, tmp_path):
    source, document = replay_dataset
    with closing(sqlite3.connect(source)) as conn, conn:
        for column in ("level", "sender", "message"):
            conn.execute(f"ALTER TABLE heartbeat ADD COLUMN {column}")
        conn.execute(
            "INSERT INTO heartbeat VALUES "
            "('source',1767225600.02,4,'PublicFeed','Connection Lost')"
        )
    manifest = ReplayManifest.parse(document, tmp_path)
    with pytest.raises(ValueError, match="health failure"):
        RecordedReplay.read(manifest)
    document["source"]["allow_gaps"] = True
    recording = RecordedReplay.read(ReplayManifest.parse(document, tmp_path))
    assert any("Connection Lost" in reason for reason in recording.limitations)


def test_warmup_alone_is_not_a_nonempty_interval(replay_dataset, tmp_path):
    _, document = replay_dataset
    document["interval"]["start"] = "2026-01-01T00:00:00.100Z"
    document["interval"]["end"] = "2026-01-01T00:00:00.200Z"
    with pytest.raises(ValueError, match="No market events"):
        RecordedReplay.read(ReplayManifest.parse(document, tmp_path))
