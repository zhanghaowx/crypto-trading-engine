"""Every engine at once, in four figures: how many components are
reporting, how many have gone quiet, how many errors were logged, and how
long a silence counts as gone."""

import streamlit as st

from jolteon.dashboard.data.engines import engine_databases
from jolteon.dashboard.services.health import (
    HEARTBEAT_TIMEOUT_SECONDS,
    heartbeats,
    summary,
)
from jolteon.dashboard.ui.primitives import metric


def render() -> None:
    root = st.session_state.root
    # The tiles under this say so while nothing has been recorded; saying
    # it here too would be the same warning twice.
    if not engine_databases(root):
        return

    latest = heartbeats(root)
    health = summary(root)
    down = len(health.down)

    reporting, quiet, errors, timeout = st.columns(4)
    with reporting:
        metric(
            "Components reporting",
            len(latest),
            decimals=None,
            border=True,
            help="Senders with a heartbeat recorded, across every engine.",
        )
    with quiet:
        metric(
            "Components down",
            down,
            decimals=None,
            color="red" if down else None,
            border=True,
            help=(
                "Senders silent for longer than the heartbeat timeout. "
                "A process that dies never reports its own death."
            ),
        )
    with errors:
        metric(
            "Recorded errors",
            health.errors,
            decimals=None,
            color="red" if health.errors else None,
            border=True,
            help="ERROR and CRITICAL lines across every engine's log.",
        )
    with timeout:
        metric(
            "Heartbeat timeout",
            HEARTBEAT_TIMEOUT_SECONDS,
            decimals=None,
            suffix=" s",
            border=True,
            help=(
                "How long a component may go without reporting before it "
                "is called down."
            ),
        )
