import copy
import json

import pytest

from jolteon.engine.core.replay_manifest import ReplayManifest, utc_timestamp


def test_roundtrip(replay_dataset, tmp_path):
    _, document = replay_dataset
    path = tmp_path / "manifest.json"
    path.write_text(json.dumps(document))
    assert ReplayManifest.read(path).document == document
    with pytest.raises(ValueError, match="timezone"):
        utc_timestamp("2026-01-01")


@pytest.mark.parametrize(
    "change",
    [
        lambda d: d.update(schema_version=2),
        lambda d: d["market"].update(symbol="ETH/USD"),
        lambda d: d["source"].update(extra=True),
        lambda d: d["source"].update(source_run_id=""),
        lambda d: d["interval"].update(bounds="[]"),
        lambda d: d["interval"].update(end=d["interval"]["start"]),
        lambda d: d["configuration"].update(extra=True),
        lambda d: d["configuration"].update(mode="unknown"),
        lambda d: d["configuration"]["parameters"].pop(""),
        lambda d: d["configuration"]["parameters"][""].pop(
            "MomentumParameters"
        ),
        lambda d: d["configuration"]["parameters"][""][
            "MomentumParameters"
        ].pop("scale"),
        lambda d: d["configuration"]["parameters"][""][
            "MomentumParameters"
        ].update(scale=-1),
        lambda d: d["configuration"]["parameters"][""][
            "MomentumParameters"
        ].update(scale="1"),
        lambda d: d["execution_simulation"].update(latency=1),
        lambda d: d["playback"].update(speed="2x"),
        lambda d: d["initialization"].update(policy="unknown"),
        lambda d: d["initialization"]["instrument_override"].update(reason=""),
        lambda d: d["initialization"]["instrument_override"][
            "specification"
        ].pop("base"),
        lambda d: d["initialization"]["instrument_override"][
            "specification"
        ].update(symbol="ETH/USD"),
        lambda d: d["initialization"]["instrument_override"][
            "specification"
        ].update(qty_min=-1),
        lambda d: d["initialization"]["instrument_override"][
            "specification"
        ].update(price_increment=0),
    ],
)
def test_reject_invalid(replay_dataset, tmp_path, change):
    _, original = replay_dataset
    document = copy.deepcopy(original)
    change(document)
    with pytest.raises(ValueError):
        ReplayManifest.parse(document, tmp_path)


def test_parameter_scope_and_cross_group_validation(replay_dataset):
    from jolteon.engine.core.parameter.replay_parameters import (
        resolved_parameters,
    )

    _, document = replay_dataset
    scopes = document["configuration"]["parameters"]
    with pytest.raises(ValueError, match="scope"):
        resolved_parameters({"": scopes[""], "ETH/USD": scopes[""]})
    scopes[""]["HeartbeatParameters"]["timeout_in_seconds"] = 10.0
    with pytest.raises(ValueError, match="timeout"):
        resolved_parameters(scopes)


@pytest.mark.parametrize(
    "change",
    [
        lambda d: d.update(configuration=[]),
        lambda d: d["source"].update(path=1),
        lambda d: d["interval"].update(start=1),
        lambda d: d["initialization"].update(instrument_override=[]),
        lambda d: d["initialization"]["instrument_override"][
            "specification"
        ].update(price_precision=1.5),
        lambda d: d["configuration"]["parameters"][""][
            "MomentumParameters"
        ].update(scale=True),
    ],
)
def test_malformed_types(replay_dataset, tmp_path, change):
    _, document = replay_dataset
    change(document)
    with pytest.raises(ValueError):
        ReplayManifest.parse(document, tmp_path)
