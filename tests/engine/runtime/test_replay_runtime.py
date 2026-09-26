import asyncio
import json

import pytest

from jolteon.analysis.replay_comparison import compare_results
from jolteon.engine.core.replay_manifest import ReplayManifest
from jolteon.engine.core.time.replay_clock import Playback
from jolteon.engine.core.time.time_manager import time_manager
from jolteon.engine.market_data.recorded_replay import RecordedReplay
from jolteon.engine.runtime.replay_runtime import run_replay


def test_full_replay_at_all_speeds(replay_dataset, tmp_path):
    source, document = replay_dataset
    results = []
    for speed in Playback.SPEEDS:
        document["playback"]["speed"] = speed
        manifest = ReplayManifest.parse(
            json.loads(json.dumps(document)), tmp_path
        )
        recording = RecordedReplay.read(manifest)
        wall = [0.0]

        async def sleep(delay):
            wall[0] += delay

        playback = Playback(speed, lambda: wall[0], sleep)
        output = tmp_path / speed
        result = asyncio.run(run_replay(manifest, recording, output, playback))
        events = [
            json.loads(line)
            for line in (output / "events.jsonl").read_text().splitlines()
        ]
        assert result["status"] == "completed"
        assert result["output_counts"]["order_fill"] == 3
        assert not time_manager().is_using_fake_time()
        results.append((result, events))
    for result, events in results[1:]:
        report = compare_results(results[0][0], result, results[0][1], events)
        assert report["status"] == "equivalent-with-documented-limitations", (
            report
        )
    with pytest.raises(FileExistsError):
        asyncio.run(run_replay(manifest, recording, output))


def test_failed_pacing_restores_clock(replay_dataset, tmp_path):
    _, document = replay_dataset
    manifest = ReplayManifest.parse(document, tmp_path)
    recording = RecordedReplay.read(manifest)

    async def fail(delay):
        raise RuntimeError("pacer failed")

    with pytest.raises(RuntimeError, match="pacer failed"):
        asyncio.run(
            run_replay(
                manifest,
                recording,
                tmp_path / "failed",
                Playback("1x", sleep=fail),
            )
        )
    assert not time_manager().is_using_fake_time()
    assert (
        json.loads((tmp_path / "failed/result.json").read_text())["status"]
        == "failed"
    )


def test_revisions_warmup_and_cancellation(replay_dataset, tmp_path):
    from jolteon.engine.core.health_monitor.health import HealthMonitor
    from jolteon.engine.core.parameter.replay_parameters import (
        ReplayParameters,
    )
    from jolteon.engine.market_data.manifest_feed import ManifestFeed

    _, document = replay_dataset
    document["interval"]["start"] = "2026-01-01T00:00:00.005Z"
    manifest = ReplayManifest.parse(document, tmp_path)
    recording = RecordedReplay.read(manifest)
    recording.revisions = [
        {
            "timestamp": manifest.start - 1,
            "revision": 1,
            "parameters": recording.parameters,
        },
        {
            "timestamp": manifest.start + 0.01,
            "revision": 2,
            "parameters": recording.parameters,
        },
    ]
    parameters = ReplayParameters(recording.parameters)
    feed = ManifestFeed(manifest, recording, parameters, HealthMonitor())
    assert len(feed.channels) == 4
    asyncio.run(feed.connect("BTC/USD"))
    assert parameters.values().revision == 2

    async def cancel(delay):
        raise asyncio.CancelledError()

    with pytest.raises(asyncio.CancelledError):
        asyncio.run(
            run_replay(
                manifest,
                recording,
                tmp_path / "cancelled",
                Playback("1x", sleep=cancel),
            )
        )
    assert (
        json.loads((tmp_path / "cancelled/result.json").read_text())["status"]
        == "interrupted"
    )
    assert not time_manager().is_using_fake_time()


def test_cleanup_failure_is_durable(replay_dataset, tmp_path, monkeypatch):
    from jolteon.engine.core.event.signal_recorder import SignalRecorder

    original = SignalRecorder.close

    def fail(self):
        original(self)
        raise RuntimeError("flush failed")

    monkeypatch.setattr(SignalRecorder, "close", fail)
    _, document = replay_dataset
    manifest = ReplayManifest.parse(document, tmp_path)
    with pytest.raises(RuntimeError, match="flush failed"):
        asyncio.run(
            run_replay(
                manifest,
                RecordedReplay.read(manifest),
                tmp_path / "failed-close",
            )
        )
    result = json.loads((tmp_path / "failed-close/result.json").read_text())
    assert result["status"] == "failed"
    assert "Cleanup failed" in result["error"]


def test_warmup_cost_does_not_consume_playback_time(replay_dataset, tmp_path):
    from jolteon.engine.core.health_monitor.health import HealthMonitor
    from jolteon.engine.core.parameter.replay_parameters import (
        ReplayParameters,
    )
    from jolteon.engine.market_data.manifest_feed import ManifestFeed

    _, document = replay_dataset
    document["interval"]["start"] = "2026-01-01T00:00:00.005Z"
    manifest = ReplayManifest.parse(document, tmp_path)
    recording = RecordedReplay.read(manifest)
    wall = [0.0]
    warmup_cost = [0.0]

    async def sleep(delay):
        wall[0] += delay

    playback = Playback("1x", lambda: wall[0], sleep)
    feed = ManifestFeed(
        manifest,
        recording,
        ReplayParameters(recording.parameters),
        HealthMonitor(),
        playback,
    )
    deliver = feed._deliver

    def slow_warmup(event):
        if event.timestamp < manifest.start:
            wall[0] += 10
            warmup_cost[0] += 10
        deliver(event)

    feed._deliver = slow_warmup
    asyncio.run(feed.connect("BTC/USD"))
    assert warmup_cost[0] > 0
    assert wall[0] - warmup_cost[0] == pytest.approx(
        manifest.end - manifest.start
    )
    assert playback.max_lag_seconds == 0
