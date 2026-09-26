"""Read and validate one consistent SQLite external-event stream."""

import hashlib
import json
import sqlite3
from collections import Counter
from contextlib import closing
from dataclasses import dataclass

from jolteon.engine.core.parameter.replay_parameters import (
    recorded_value,
    resolved_parameters,
)
from jolteon.engine.core.replay_manifest import ReplayManifest
from jolteon.engine.market_data.core.instrument import InstrumentSpec

CHANNELS = (
    "instrument_feed",
    "order_book_update_feed",
    "bbo_feed",
    "market_trade_feed",
)
ORDER_POLICY = "recorder-time-channel-row-v1"


@dataclass(frozen=True)
class ReplayEvent:
    timestamp: float
    channel: str
    payload: dict
    ordinal: int

    def canonical(self) -> dict:
        return {
            "timestamp": self.timestamp,
            "channel": self.channel,
            "payload": self.payload,
            "ordinal": self.ordinal,
        }


@dataclass
class RecordedReplay:
    events: list[ReplayEvent]
    parameters: dict
    revisions: list[dict]
    limitations: list[str]
    input_hash: str
    counts: dict[str, int]
    ordering_policy: str = ORDER_POLICY

    @classmethod
    def read(cls, manifest: ReplayManifest) -> "RecordedReplay":
        with closing(
            sqlite3.connect(manifest.source.as_uri() + "?mode=ro", uri=True)
        ) as conn:
            conn.row_factory = sqlite3.Row
            conn.execute("BEGIN")
            return _read(conn, manifest)


def _rows(conn, table: str, where: str = "", args: tuple = ()) -> list[dict]:
    try:
        return [
            dict(row)
            for row in conn.execute(
                f'SELECT rowid AS _rowid, * FROM "{table}" {where}', args
            )
        ]
    except sqlite3.OperationalError as error:
        raise ValueError(f"Required replay input {table}: {error}") from error


def _parameters(rows: list[dict]) -> dict:
    scopes: dict = {}
    for row in rows:
        group = scopes.setdefault(row["symbol"], {}).setdefault(
            row["group_name"], {}
        )
        if row["field_name"] in group:
            raise ValueError("Duplicate recorded parameter field")
        group[row["field_name"]] = recorded_value(
            row["group_name"], row["field_name"], row["value"]
        )
    resolved_parameters(scopes)
    return scopes


def _read(conn, manifest: ReplayManifest) -> RecordedReplay:
    run_id = manifest.document["source"]["source_run_id"]
    runs = _rows(conn, "engine_run", "WHERE run_id = ?", (run_id,))
    if len(runs) != 1 or (runs[0]["exchange"], runs[0]["symbol"]) != (
        "Binance.US",
        "BTC/USD",
    ):
        raise ValueError(
            "Source run must uniquely identify Binance.US BTC/USD"
        )
    if manifest.start < runs[0]["started_at"]:
        raise ValueError("Replay interval begins before source run")
    if runs[0]["ended_at"] and manifest.end > runs[0]["ended_at"]:
        raise ValueError("Replay interval extends beyond completed source run")
    limitations: list[str] = []
    config = manifest.document["configuration"]
    revisions = []
    if config["mode"] == "fixed":
        parameters = config["parameters"]
    else:
        parameters = _parameters(
            _rows(conn, "run_parameter", "WHERE run_id = ?", (run_id,))
        )
        tables = {
            row[0]
            for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            )
        }
        if "accepted_parameter_revision" not in tables:
            raise ValueError(
                "Recorded mode requires accepted revision history; "
                "use explicit fixed configuration"
            )
        rows = _rows(
            conn,
            "accepted_parameter_revision",
            "WHERE run_id = ? ORDER BY effective_at, revision, rowid",
            (run_id,),
        )
        for number in dict.fromkeys(row["revision"] for row in rows):
            group = [row for row in rows if row["revision"] == number]
            times = {row["effective_at"] for row in group}
            if len(times) != 1:
                raise ValueError(
                    "Revision has conflicting effective timestamps"
                )
            revisions.append(
                {
                    "revision": number,
                    "timestamp": times.pop(),
                    "parameters": _parameters(group),
                }
            )
    resolved_parameters(parameters)
    instrument = manifest.instrument
    if instrument is None:
        specs = _rows(
            conn,
            "instrument_feed",
            "WHERE symbol = ? AND timestamp <= ?",
            ("BTC/USD", manifest.start),
        )
        specs.sort(key=lambda row: (row["timestamp"], row["_rowid"]))
        if not specs or specs[-1].get("run_id") != run_id:
            raise ValueError(
                "No unambiguous opening instrument; "
                "supply instrument_override with a reason"
            )
        instrument = InstrumentSpec(
            **{
                key: specs[-1][key]
                for key in InstrumentSpec.__dataclass_fields__
            }
        )
        if instrument.price_increment <= 0:
            raise ValueError("Opening instrument has no valid price increment")
    else:
        limitations.append(
            "Instrument rules explicitly supplied; historical rules unverified"
        )
    books = _rows(
        conn,
        "order_book_update_feed",
        "WHERE run_id = ? AND symbol = ? AND timestamp < ? "
        "ORDER BY timestamp, rowid",
        (run_id, "BTC/USD", manifest.end),
    )
    snapshots = [
        row
        for row in books
        if row["is_snapshot"] and row["timestamp"] <= manifest.start
    ]
    opening: dict | None
    if snapshots:
        opening = snapshots[-1]
    else:
        opening = next((row for row in books if row["is_snapshot"]), None)
    if opening is None:
        raise ValueError(
            "No opening L2 snapshot in source run before interval end"
        )
    origin = min(manifest.start, opening["timestamp"])
    selected_books = [
        row for row in books if row["_rowid"] >= opening["_rowid"]
    ]
    events = [ReplayEvent(origin, "instrument_feed", instrument.__dict__, 0)]
    counts: Counter = Counter()
    native_order = True
    fields: tuple[str, ...]
    for channel in CHANNELS[1:]:
        rows = (
            selected_books
            if channel == "order_book_update_feed"
            else _rows(
                conn,
                channel,
                "WHERE run_id = ? AND symbol = ? AND timestamp >= ? "
                "AND timestamp < ? ORDER BY timestamp, rowid",
                (run_id, "BTC/USD", origin, manifest.end),
            )
        )
        if not rows:
            raise ValueError(f"Required channel has no events: {channel}")
        if channel == "order_book_update_feed":
            fields = (
                "symbol",
                "model",
                "version",
                "sequence",
                "bids",
                "asks",
                "is_snapshot",
                "exchange_time",
            )
            identifiers = [int(row["sequence"]) for row in rows]
            for row in rows:
                if row["model"] != "l2" or row["version"] != 1:
                    raise ValueError("Unsupported recorded book format")
                for side in ("bids", "asks"):
                    levels = json.loads(row[side])
                    if any(price <= 0 or qty < 0 for price, qty in levels):
                        raise ValueError("Invalid book price or quantity")
        elif channel == "market_trade_feed":
            fields = (
                "symbol",
                "exchange_trade_id",
                "side",
                "price",
                "quantity",
                "transaction_time",
            )
            identifiers = [int(row["exchange_trade_id"]) for row in rows]
        else:
            fields = (
                "symbol",
                "bid_price",
                "bid_quantity",
                "ask_price",
                "ask_quantity",
            )
            identifiers = []
        if any(b != a + 1 for a, b in zip(identifiers, identifiers[1:])):
            if not manifest.document["source"]["allow_gaps"]:
                raise ValueError(f"Sequence gap or duplicate in {channel}")
            limitations.append(f"Allowed sequence gap or duplicate: {channel}")
        native_order = native_order and all(
            row.get("external_sequence") is not None for row in rows
        )
        for row in rows:
            if channel == "bbo_feed" and not (
                0 < row["bid_price"] < row["ask_price"]
                and row["bid_quantity"] > 0
                and row["ask_quantity"] > 0
            ):
                raise ValueError("Invalid BBO prices or quantities")
            if channel == "market_trade_feed" and not (
                row["side"] in ("BUY", "SELL")
                and row["price"] > 0
                and row["quantity"] > 0
            ):
                raise ValueError("Invalid market trade")
            events.append(
                ReplayEvent(
                    float(row["timestamp"]),
                    channel,
                    {key: row[key] for key in fields},
                    row.get("external_sequence", row["_rowid"]),
                )
            )
    table_names = {
        row[0]
        for row in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        )
    }
    if "instrument_feed" in table_names:
        changes = _rows(
            conn,
            "instrument_feed",
            "WHERE run_id = ? AND symbol = ? AND timestamp > ? "
            "AND timestamp < ? ORDER BY timestamp, rowid",
            (run_id, "BTC/USD", origin, manifest.end),
        )
        for row in changes:
            native_order = (
                native_order and row.get("external_sequence") is not None
            )
            events.append(
                ReplayEvent(
                    row["timestamp"],
                    "instrument_feed",
                    {
                        key: row[key]
                        for key in InstrumentSpec.__dataclass_fields__
                    },
                    row.get("external_sequence", row["_rowid"]),
                )
            )
    if native_order:
        events.sort(key=lambda event: event.ordinal)
        if any(
            a.timestamp > b.timestamp or a.ordinal == b.ordinal
            for a, b in zip(events, events[1:])
        ):
            raise ValueError(
                "External event sequence contradicts timestamps or duplicates"
            )
        ordering = "external-sequence-v1"
    else:
        events.sort(
            key=lambda event: (
                event.timestamp,
                CHANNELS.index(event.channel),
                event.ordinal,
            )
        )
        ordering = ORDER_POLICY
        limitations.insert(
            0,
            "Legacy event order cannot establish original live delivery order",
        )
    if not any(
        event.timestamp >= manifest.start
        and event.channel != "instrument_feed"
        for event in events
    ):
        raise ValueError("No market events inside the requested interval")
    for event in events:
        counts[event.channel] += 1
    # Recorder heartbeats bound a source run even when markets are quiet.
    last_recorded = conn.execute(
        "SELECT max(timestamp) FROM heartbeat WHERE run_id = ?", (run_id,)
    ).fetchone()[0]
    if last_recorded is None or last_recorded < manifest.end:
        raise ValueError("Source recording does not cover interval end")
    heartbeat_columns = {
        row[1] for row in conn.execute("PRAGMA table_info(heartbeat)")
    }
    if {"level", "sender", "message"} <= heartbeat_columns:
        health_gaps = _rows(
            conn,
            "heartbeat",
            "WHERE run_id = ? AND timestamp >= ? AND timestamp < ? "
            "AND sender = 'PublicFeed' AND level >= 3",
            (run_id, origin, manifest.end),
        )
        if health_gaps and not manifest.document["source"]["allow_gaps"]:
            raise ValueError("Recorded market-data health failure in interval")
        for gap in health_gaps:
            limitations.append(
                f"Allowed feed health failure at {gap['timestamp']}: "
                f"{gap['message']}"
            )
    revisions = [row for row in revisions if row["timestamp"] < manifest.end]
    digest = hashlib.sha256()
    from itertools import chain

    header = {
        "ordering": ordering,
        "parameters": parameters,
        "revisions": revisions,
        "limitations": limitations,
    }
    for value in chain([header], (event.canonical() for event in events)):
        digest.update(
            json.dumps(
                value, sort_keys=True, separators=(",", ":"), allow_nan=False
            ).encode()
        )
        digest.update(b"\n")
    return RecordedReplay(
        events,
        parameters,
        revisions,
        limitations,
        digest.hexdigest(),
        dict(counts),
        ordering,
    )
