"""Validate the complete, versioned contract for a replay experiment."""

import json
import math
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from jolteon.engine.core.parameter.replay_parameters import resolved_parameters
from jolteon.engine.core.time.replay_clock import Playback
from jolteon.engine.market_data.core.instrument import InstrumentSpec


def utc_timestamp(value: str) -> float:
    if not isinstance(value, str):
        raise ValueError("Replay timestamps must be ISO strings")
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError("Replay timestamps require an explicit timezone")
    return parsed.timestamp()


@dataclass(frozen=True)
class ReplayManifest:
    document: dict
    source: Path
    start: float
    end: float
    instrument: InstrumentSpec | None

    @classmethod
    def read(cls, path: Path) -> "ReplayManifest":
        return cls.parse(json.loads(path.read_text()), path.parent)

    @classmethod
    def parse(cls, document: dict, directory: Path) -> "ReplayManifest":
        required = {
            "schema_version",
            "source",
            "market",
            "interval",
            "configuration",
            "initialization",
            "execution_simulation",
            "playback",
        }
        if (
            not isinstance(document, dict)
            or set(document) != required
            or type(document["schema_version"]) is not int
            or document["schema_version"] != 1
        ):
            raise ValueError(
                "Expected complete replay manifest schema_version 1"
            )
        if any(
            not isinstance(document[key], dict)
            for key in required - {"schema_version"}
        ):
            raise ValueError("Manifest sections must be JSON objects")
        if document["market"] != {
            "exchange": "Binance.US",
            "symbol": "BTC/USD",
        }:
            raise ValueError(
                "Replay currently supports Binance.US BTC/USD only"
            )
        source = document["source"]
        if set(source) != {"path", "source_run_id", "allow_gaps"}:
            raise ValueError(
                "Source requires path, source_run_id and allow_gaps"
            )
        if (
            not isinstance(source["source_run_id"], str)
            or not isinstance(source["path"], str)
            or not source["path"]
            or not source["source_run_id"]
            or type(source["allow_gaps"]) is not bool
        ):
            raise ValueError("Explicit source run and gap policy required")
        interval = document["interval"]
        if (
            set(interval) != {"start", "end", "bounds"}
            or interval["bounds"] != "[start,end)"
        ):
            raise ValueError("Interval must use [start,end) bounds")
        start, end = (utc_timestamp(interval[key]) for key in ("start", "end"))
        if start >= end:
            raise ValueError("Replay start must precede end")
        config = document["configuration"]
        if config.get("mode") == "fixed":
            if set(config) != {"mode", "parameters"}:
                raise ValueError(
                    "Fixed configuration requires parameters only"
                )
            resolved_parameters(config["parameters"])
        elif config != {"mode": "recorded"}:
            raise ValueError(
                "Choose fixed or recorded configuration explicitly"
            )
        if document["execution_simulation"] != {
            "model": "current-mock-v1",
            "latency": None,
        }:
            raise ValueError(
                "Only current-mock-v1 without latency is supported"
            )
        if (
            set(document["playback"]) != {"speed"}
            or document["playback"]["speed"] not in Playback.SPEEDS
        ):
            raise ValueError("Unsupported playback speed")
        initial = document["initialization"]
        if (
            set(initial) != {"policy", "instrument_override"}
            or initial["policy"] != "flat-await-inputs"
        ):
            raise ValueError("Initialization must be flat-await-inputs")
        instrument = None
        override = initial["instrument_override"]
        if override is not None:
            if not isinstance(override, dict):
                raise ValueError("Instrument override must be an object")
            if (
                set(override) != {"reason", "specification"}
                or not override["reason"]
            ):
                raise ValueError("Instrument override requires a reason")
            spec = override["specification"]
            if not isinstance(spec, dict) or set(spec) != set(
                InstrumentSpec.__dataclass_fields__
            ):
                raise ValueError("Supply every instrument specification field")
            if (
                spec["symbol"] != "BTC/USD"
                or spec["base"] != "BTC"
                or spec["quote"] != "USD"
            ):
                raise ValueError("Instrument must describe BTC/USD")
            for key in (
                "price_precision",
                "qty_precision",
                "price_increment",
                "qty_min",
                "cost_min",
            ):
                if (
                    type(spec[key]) not in (int, float)
                    or not math.isfinite(spec[key])
                    or spec[key] < 0
                ):
                    raise ValueError(f"Invalid instrument field: {key}")
            if any(
                type(spec[key]) is not int
                for key in ("price_precision", "qty_precision")
            ):
                raise ValueError("Instrument precision must be an integer")
            if spec["price_increment"] <= 0:
                raise ValueError("Instrument price increment must be positive")
            instrument = InstrumentSpec(**spec)
        return cls(
            document,
            (directory / source["path"]).resolve(),
            start,
            end,
            instrument,
        )
