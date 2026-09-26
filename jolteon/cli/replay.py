"""Validate, run, and compare bounded recorded-market experiments."""

import argparse
import asyncio
import json
import sqlite3
from pathlib import Path

from jolteon.analysis.replay_comparison import compare_results
from jolteon.engine.core.replay_manifest import ReplayManifest
from jolteon.engine.market_data.recorded_replay import RecordedReplay
from jolteon.engine.runtime.replay_runtime import run_replay


def _load_result(directory: Path):
    metadata = json.loads((directory / "result.json").read_text())
    with (directory / "events.jsonl").open() as stream:
        events = [json.loads(line) for line in stream]
    return metadata, events


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    for name in ("validate", "run"):
        command = commands.add_parser(name)
        command.add_argument("--manifest", type=Path, required=True)
        if name == "run":
            command.add_argument(
                "--speed", choices=("1x", "10x", "24x", "unbounded")
            )
            command.add_argument("--output", type=Path, required=True)
    compare = commands.add_parser("compare")
    compare.add_argument("runs", type=Path, nargs="+")
    args = parser.parse_args(argv)
    try:
        if args.command == "compare":
            if len(args.runs) < 2:
                raise ValueError("Comparison needs at least two runs")
            left, left_events = _load_result(args.runs[0])
            reports = []
            for directory in args.runs[1:]:
                right, right_events = _load_result(directory)
                reports.append(
                    compare_results(left, right, left_events, right_events)
                )
            print(json.dumps(reports, indent=2))
            statuses = {report["status"] for report in reports}
            if statuses == {"equivalent"}:
                return 0
            if statuses <= {
                "equivalent",
                "equivalent-with-documented-limitations",
            }:
                return 2
            return 1
        document = json.loads(args.manifest.read_text())
        if args.command == "run" and args.speed:
            document["playback"]["speed"] = args.speed
        manifest = ReplayManifest.parse(
            document, args.manifest.resolve().parent
        )
        recording = RecordedReplay.read(manifest)
        if args.command == "validate":
            result = {
                "input_hash": recording.input_hash,
                "counts": recording.counts,
                "limitations": recording.limitations,
            }
        else:
            result = asyncio.run(run_replay(manifest, recording, args.output))
        print(json.dumps(result, indent=2))
        return 0
    except (ValueError, OSError, KeyError, TypeError, sqlite3.Error) as error:
        print(
            json.dumps({"status": "incomplete/invalid", "error": str(error)})
        )
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
