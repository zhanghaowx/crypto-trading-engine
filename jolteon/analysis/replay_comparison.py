"""Semantic comparison of already loaded replay outputs."""

import math

import pandas as pd

from jolteon.analysis.replay_economics import replay_economics

TOLERANCES = {
    "fair_price": 1e-9,
    "quantity": 1e-12,
    "usd": 1e-8,
    "relative": 1e-12,
}


def difference(left, right, path="") -> str | None:
    if type(left) is not type(right):
        return f"{path}: types differ"
    if isinstance(left, dict):
        if left.keys() != right.keys():
            return f"{path}: fields differ"
        for key in left:
            found = difference(left[key], right[key], f"{path}.{key}")
            if found:
                return found
    elif isinstance(left, list):
        if len(left) != len(right):
            return f"{path}: lengths differ ({len(left)} vs {len(right)})"
        for index, (a, b) in enumerate(zip(left, right)):
            found = difference(a, b, f"{path}[{index}]")
            if found:
                return found
    elif isinstance(left, float):
        exact = path.endswith(("timestamp", "creation_time", ".price"))
        tolerance = (
            TOLERANCES["quantity"]
            if any(
                word in path for word in ("quantity", "volume", "positions")
            )
            else TOLERANCES["usd"]
            if any(word in path for word in ("fee", "cash", "pnl"))
            else TOLERANCES["fair_price"]
        )
        equal = (
            left == right
            if exact
            else math.isclose(
                left, right, abs_tol=tolerance, rel_tol=TOLERANCES["relative"]
            )
        )
        if not math.isfinite(left) or not math.isfinite(right) or not equal:
            return f"{path}: {left!r} != {right!r}"
    elif left != right:
        return f"{path}: {left!r} != {right!r}"
    return None


def compare_results(
    left: dict, right: dict, left_events: list, right_events: list
) -> dict:
    report = {"comparator_version": 1, "tolerances": TOLERANCES}
    for metadata, events in ((left, left_events), (right, right_events)):
        if metadata.get("status") != "completed" or not all(
            key in metadata
            for key in (
                "terminal",
                "input_hash",
                "input_counts",
                "code_hash",
                "manifest",
                "output_counts",
                "delivered_events",
                "limitations",
            )
        ):
            return {
                **report,
                "status": "incomplete/invalid",
                "detail": "Missing completed result metadata",
            }
        from collections import Counter

        required_outputs = {
            "fair_price",
            "fair_price_adjustment",
            "quote_offset",
            "order",
            "cancel_order",
            "order_fill",
            "position_updated",
        }
        if set(metadata["output_counts"]) != required_outputs:
            return {
                **report,
                "status": "incomplete/invalid",
                "detail": "Required output categories are missing",
            }
        if any(
            not isinstance(event.get("payload"), dict)
            or not isinstance(event.get("timestamp"), (int, float))
            for event in events
        ):
            return {
                **report,
                "status": "incomplete/invalid",
                "detail": "Invalid event schema",
            }
        counts = Counter(event.get("channel") for event in events)
        if dict(counts) != {
            key: value
            for key, value in metadata["output_counts"].items()
            if value
        } or metadata["delivered_events"] != sum(
            metadata["input_counts"].values()
        ):
            return {
                **report,
                "status": "incomplete/invalid",
                "detail": "Event counts do not match completed result",
            }
    if left.get("python_version") != right.get("python_version"):
        return {
            **report,
            "status": "input mismatch",
            "detail": "Python version",
        }
    for key in ("input_hash", "input_counts", "code_hash"):
        if left[key] != right[key]:
            return {**report, "status": "input mismatch", "detail": key}

    def economic_manifest(metadata):
        value = dict(metadata["manifest"])
        value.pop("playback")
        source = dict(value["source"])
        source.pop("path")
        value["source"] = source
        return value

    if economic_manifest(left) != economic_manifest(right):
        return {
            **report,
            "status": "input mismatch",
            "detail": "Experiment configuration differs",
        }
    detail = difference(left_events, right_events, "events")
    if detail is None:
        detail = difference(left["terminal"], right["terminal"], "terminal")
    if detail is not None:
        index = next(
            (
                i
                for i, (a, b) in enumerate(zip(left_events, right_events))
                if difference(a, b)
            ),
            min(len(left_events), len(right_events)),
        )
        return {
            **report,
            "status": "result mismatch",
            "detail": detail,
            "left_context": left_events[max(0, index - 2) : index + 2],
            "right_context": right_events[max(0, index - 2) : index + 2],
        }
    economics = replay_economics(pd.DataFrame(left_events))
    limitations = sorted(set(left["limitations"] + right["limitations"]))
    return {
        **report,
        "status": "equivalent-with-documented-limitations"
        if limitations
        else "equivalent",
        "limitations": limitations,
        "economics": economics,
    }
