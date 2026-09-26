import copy

import pytest

from jolteon.analysis.replay_comparison import compare_results, difference


@pytest.mark.parametrize(
    "left,right",
    [
        (1, "1"),
        ({"a": 1}, {}),
        ([1], []),
        (1, 2),
        (float("nan"), float("nan")),
        ({"timestamp": 1.0}, {"timestamp": 1.000000001}),
    ],
)
def test_differences(left, right):
    assert difference(left, right)


def test_numeric_tolerances():
    assert difference({"quantity": 1.0}, {"quantity": 1.0 + 1e-13}) is None
    assert difference({"quantity": 1.0}, {"quantity": 1.0 + 1e-10})
    assert difference({"pnl": 1.0}, {"pnl": 1.0 + 1e-9}) is None
    assert difference({"pnl": 1.0}, {"pnl": 1.0 + 1e-6})


def test_comparison_statuses():
    left = {
        "status": "completed",
        "terminal": {"pnl": 1.0},
        "input_hash": "abc",
        "input_counts": {"trade": 1},
        "delivered_events": 1,
        "code_hash": "xyz",
        "manifest": {"source": {"path": "a"}, "playback": {"speed": "1x"}},
        "output_counts": {
            "order": 1,
            "fair_price": 0,
            "fair_price_adjustment": 0,
            "quote_offset": 0,
            "cancel_order": 0,
            "order_fill": 0,
            "position_updated": 0,
        },
        "limitations": [],
    }
    events = [
        {"channel": "order", "timestamp": 1.0, "payload": {"price": 100.0}}
    ]
    assert (
        compare_results(left, left, events, events)["status"] == "equivalent"
    )
    assert (
        compare_results({}, left, events, events)["status"]
        == "incomplete/invalid"
    )
    assert (
        compare_results(left, left, [], events)["status"]
        == "incomplete/invalid"
    )
    right = copy.deepcopy(left)
    right["input_hash"] = "changed"
    assert (
        compare_results(left, right, events, events)["status"]
        == "input mismatch"
    )
    right = copy.deepcopy(left)
    right["manifest"]["config"] = "changed"
    assert (
        compare_results(left, right, events, events)["status"]
        == "input mismatch"
    )
    right = copy.deepcopy(left)
    right["terminal"]["pnl"] = 2.0
    assert (
        compare_results(left, right, events, events)["status"]
        == "result mismatch"
    )
    changed = copy.deepcopy(events)
    changed[0]["payload"]["price"] = 101.0
    report = compare_results(left, left, events, changed)
    assert report["status"] == "result mismatch"
    assert report["right_context"] == changed


def test_invalid_output_categories_and_python_version():
    from jolteon.engine.runtime.replay_result import OUTPUT_CHANNELS

    left = {
        "status": "completed",
        "terminal": {},
        "input_hash": "a",
        "input_counts": {},
        "delivered_events": 0,
        "code_hash": "a",
        "manifest": {"source": {"path": "a"}, "playback": {}},
        "output_counts": {},
        "limitations": [],
    }
    assert (
        compare_results(left, left, [], [])["status"] == "incomplete/invalid"
    )
    left["output_counts"] = dict.fromkeys(OUTPUT_CHANNELS, 0)
    assert (
        compare_results(left, left, [{"timestamp": 0}], [])["status"]
        == "incomplete/invalid"
    )
    right = copy.deepcopy(left)
    right["python_version"] = "different"
    assert compare_results(left, right, [], [])["status"] == "input mismatch"
