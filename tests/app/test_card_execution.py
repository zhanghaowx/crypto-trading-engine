"""Exercise real fragment storage and ScriptRunner dispatch.

AppTest normally starts a fresh runner for each run(), so widget clicks
alone cannot prove fragment isolation. Queue browser-equivalent requests
before that runner shuts down, preserving its registered fragments.
"""

from copy import deepcopy
from unittest import mock

import pytest
from streamlit.errors import StreamlitAPIException
from streamlit.proto.WidgetStates_pb2 import WidgetStates
from streamlit.runtime.scriptrunner import ScriptRunnerEvent
from streamlit.runtime.scriptrunner_utils.script_requests import RerunData
from streamlit.testing.v1 import AppTest
from streamlit.testing.v1.local_script_runner import LocalScriptRunner


def execution_script():
    import streamlit as st

    from jolteon.app.card import Card, render_cards

    st.session_state["page_runs"] = st.session_state.get("page_runs", 0) + 1
    st.selectbox("Engine", ["one", "two"], key="engine")
    calls = st.session_state.setdefault("calls", [])

    def load(name):
        calls.append((name, "load", st.session_state.engine))
        if st.session_state.get("fail") == "load" and name == "a":
            raise ValueError("load failed")
        return object()

    def note(name, phase, model):
        calls.append((name, phase, st.session_state.engine))
        models = st.session_state.setdefault("models", {})
        if phase == "accent":
            models[name] = model
        elif phase != "details":
            assert models[name] is model
        if st.session_state.get("fail") == phase and name == "a":
            raise ValueError(f"{phase} failed")
        if phase == "body":
            st.number_input("Page", key=f"{name}-page", value=1)
        if phase == "details":
            st.write("Details")

    from functools import partial

    render_cards(
        [
            Card(
                name,
                name.upper(),
                ":material/show_chart:",
                body=partial(note, name, "body"),
                load=partial(load, name),
                accent=partial(note, name, "accent"),
                actions=partial(note, name, "actions"),
                details=partial(note, name, "details"),
                width="half",
            )
            for name in ("a", "b")
        ]
    )


def run_requests(requests, **state):
    """Each request is (fragment key or None, widget key, state updates)."""
    pending = iter(requests)
    snapshots = []

    class Runner(LocalScriptRunner):
        def _on_script_finished(self, ctx, event, premature_stop):
            super()._on_script_finished(ctx, event, premature_stop)
            if event == ScriptRunnerEvent.SCRIPT_STOPPED_FOR_RERUN:
                return
            snapshot = deepcopy(self.session_state.filtered_state)
            registered = []
            for name in ("a", "b"):
                try:
                    self._fragment_storage.resolve_target(name)
                except StreamlitAPIException:
                    continue
                registered.append(name)
            snapshot["registered"] = registered
            snapshot["timer_count"] = sum(
                msg.HasField("auto_rerun") for msg in self.forward_msgs()
            )
            snapshots.append(snapshot)
            request = next(pending, None)
            if request is None:
                return
            target, widget_key, updates = request
            for key, value in updates.items():
                self.session_state[key] = value
            widgets = None
            if widget_key:
                widgets = WidgetStates(
                    widgets=self._session_state.get_widget_states()
                )
                if widget_key == "__dismiss__":
                    dialog = next(
                        msg.delta.add_block.dialog
                        for msg in reversed(self.forward_msgs())
                        if msg.HasField("delta")
                        and msg.delta.HasField("add_block")
                        and msg.delta.add_block.HasField("dialog")
                    )
                    widget = next(
                        w for w in widgets.widgets if w.id == dialog.id
                    )
                else:
                    widget = next(
                        w
                        for w in widgets.widgets
                        if w.id.endswith(f"-{widget_key}")
                    )
                if widget.WhichOneof("value") == "trigger_value":
                    widget.trigger_value = True
                elif widget_key == "engine":
                    widget.string_value = "two"
                else:
                    widget.int_value = 2
            self.request_rerun(
                RerunData(
                    fragment_id_queue=(
                        self._fragment_storage.resolve_target(target)
                        if target
                        else []
                    ),
                    widget_states=widgets,
                    is_auto_rerun=target is not None and widgets is None,
                )
            )

    at = AppTest.from_function(execution_script, default_timeout=10)
    for key, value in state.items():
        at.session_state[key] = value
    with mock.patch("streamlit.testing.v1.app_test.LocalScriptRunner", Runner):
        at.run()
    assert not at.exception
    return at, snapshots


@pytest.mark.parametrize("widget", [None, "card-a-refresh", "a-page"])
def test_timer_manual_refresh_and_pagination_execute_only_one_card(widget):
    at, snapshots = run_requests([("a", widget, {})], auto_refresh=False)
    assert at.session_state["page_runs"] == 1
    initial, refreshed = snapshots
    assert initial["timer_count"] == 0
    assert refreshed["calls"][len(initial["calls"]) :] == [
        ("a", phase, "one") for phase in ("load", "accent", "body", "actions")
    ]
    assert refreshed["_card_metrics"]["b"] == initial["_card_metrics"]["b"]
    assert refreshed["_card_metrics"]["a"].refresh_count == 2


@pytest.mark.parametrize("phase", ["load", "accent", "body", "actions"])
def test_failure_is_local_and_retry_recovers(phase):
    at, snapshots = run_requests(
        [("a", "card-a-retry", {"fail": None})],
        fail=phase,
        auto_refresh=False,
    )
    assert snapshots[0]["_card_metrics"]["a"].error_count == 1
    assert snapshots[0]["_card_metrics"]["b"].refresh_count == 1
    assert not at.error
    assert at.session_state["page_runs"] == 1
    metrics = at.session_state["_card_metrics"]["a"]
    assert metrics.refresh_count == 2
    assert metrics.error_count == 1
    assert metrics.total_ms >= metrics.load_ms >= 0
    assert metrics.render_ms >= 0
    assert metrics.last_refresh_at is not None


def test_hidden_cards_suspend_all_work_and_unhide_resumes():
    at, snapshots = run_requests(
        [
            ("a", "card-a-hide", {}),
            # Hiding requests a full run to repack rows; let that run happen
            # before sending subsequent requests (below uses pre-hidden state).
        ]
    )
    assert "card-a" in at.session_state["_card_hidden"]
    assert snapshots[-1]["registered"] == ["b"]
    at, snapshots = run_requests(
        [
            ("b", None, {}),
            ("b", None, {}),
            (None, "card-unhide", {}),
        ],
        _card_hidden={"card-a"},
    )
    for snapshot in snapshots[:3]:
        assert "a" not in snapshot["_card_metrics"]
        assert snapshot["registered"] == ["b"]
        assert all(name == "b" for name, _, _ in snapshot["calls"])
    assert at.session_state["_card_metrics"]["a"].refresh_count == 1


def test_global_context_change_refreshes_both_cards():
    at, snapshots = run_requests([(None, "engine", {})])
    assert at.session_state["page_runs"] == 2
    assert snapshots[-1]["calls"][-8:] == [
        (name, phase, "two")
        for name in ("a", "b")
        for phase in ("load", "accent", "body", "actions")
    ]


def test_details_load_once_without_executing_body_or_sibling():
    at, snapshots = run_requests([("a", "card-a-details", {})])
    assert at.session_state["page_runs"] == 1
    assert snapshots[-1]["calls"][len(snapshots[0]["calls"]) :] == [
        ("a", "load", "one"),
        ("a", "details", "one"),
    ]
    assert at.session_state["_card_metrics"]["a"].refresh_count == 2


def test_dismissing_details_restores_only_the_owning_card():
    at, snapshots = run_requests(
        [
            ("a", "card-a-details", {}),
            (None, "__dismiss__", {}),
        ]
    )
    assert at.session_state["page_runs"] == 1
    assert "_card_details" not in at.session_state
    assert snapshots[-1]["calls"][len(snapshots[-2]["calls"]) :] == [
        ("a", phase, "one") for phase in ("load", "accent", "body", "actions")
    ]


def test_failed_card_shows_error_and_leaves_sibling_usable():
    at, _ = run_requests([], fail="load")
    assert len(at.error) == 1
    assert "A could not refresh" in at.error[0].value
    assert at.button(key="card-a-retry")
    assert at.button(key="card-b-refresh")


def test_details_failure_is_contained():
    at, _ = run_requests([("a", "card-a-details", {"fail": "details"})])
    assert at.error
    assert at.session_state["_card_metrics"]["a"].error_count == 1
    assert at.session_state["_card_metrics"]["b"].refresh_count == 1


def test_visible_cards_register_separate_timers():
    _, snapshots = run_requests([], auto_refresh=True, refresh_seconds=5)
    assert snapshots[0]["registered"] == ["a", "b"]
    assert snapshots[0]["timer_count"] == 2


def test_hiding_a_failed_dialog_closes_it_and_suspends_the_card():
    at, snapshots = run_requests(
        [
            ("a", "card-a-details", {"fail": "details"}),
            (None, "card-a-failure-hide", {}),
        ]
    )
    assert "card-a" in at.session_state["_card_hidden"]
    assert "_card_details" not in at.session_state
    assert snapshots[-1]["registered"] == ["b"]
    assert at.session_state["_card_metrics"]["a"].refresh_count == 2
    assert not at.error
    assert at.button(key="card-unhide")
