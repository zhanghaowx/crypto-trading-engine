"""Drawing one card: its refresh timer, its model, and its failures.

Each card runs inside a fragment of its own, so a card redrawing itself
costs nothing on the rest of the page. What the reader does to a card -
hiding it, opening its details, refreshing it by hand - is kept here too,
because it is what decides what the next pass draws.
"""

import logging
from dataclasses import replace
from datetime import datetime, timezone
from functools import partial
from time import perf_counter
from typing import Callable

import streamlit as st

from jolteon.dashboard import state
from jolteon.dashboard.ui.cards.model import Card, CardMetrics, card_key
from jolteon.dashboard.ui.cards.style import accent_rule

_LOG = logging.getLogger(__name__)
_METRICS = "_card_metrics"

# Where a reader's choices about a card live. Kept out of the widget keys
# below so neither can shadow the other in session state.
_HIDDEN = "_card_hidden"
_DETAILS = "_card_details"


def hidden_keys() -> set[str]:
    return st.session_state.setdefault(_HIDDEN, set())


# Each of these runs as a button's `on_click`, so the choice lands in
# session state *before* the rerun - the rerun's own top-to-bottom pass
# then draws the card the reader just asked for rather than the one they
# clicked on.
def _open_details(key: str) -> None:
    st.session_state[_DETAILS] = key


def _close_details() -> None:
    st.session_state.pop(_DETAILS, None)


def hide(key: str) -> None:
    hidden_keys().add(key)
    if st.session_state.get(_DETAILS) == key:
        _close_details()


def _hide_and_repack(key: str) -> None:
    # A failed dialog must close and let the page repack its card rows.
    hide(key)
    st.rerun(scope="app")


def unhide_all() -> None:
    hidden_keys().clear()


def _details_dialog(spec: Card) -> None:
    """
    What the card has to say beyond what it shows in place, in a modal
    of its own - wide enough for the tables a card has to squeeze.

    Opened from session state rather than straight from the button's own
    return value: the pages this renders on refresh on a timer, and a
    modal opened by a click alone would close again on the first refresh
    after it.
    """

    def dismiss() -> None:
        _close_details()
        st.rerun(spec.id)

    def details() -> None:
        def render(bound: Card) -> None:
            assert bound.details is not None
            bound.details()

        _execute(spec, render)

    st.dialog(
        spec.title,
        icon=spec.icon,
        width="large",
        on_dismiss=dismiss,
    )(details)()


def _chrome(spec: Card, key: str) -> None:
    with st.container(
        horizontal=True,
        horizontal_alignment="right",
        vertical_alignment="center",
        gap="small",
        key=f"card-chrome-{spec.id}",
    ):
        if spec.actions is not None:
            spec.actions()
        if spec.manual_refresh:
            st.button(
                "",
                icon=":material/refresh:",
                key=f"{key}-refresh",
                help="Refresh this card.",
                type="tertiary",
            )
        # Only where there is something more to show: an icon on a card
        # that has nothing behind it promises a detail that is not there.
        if spec.details is not None:
            st.button(
                "",
                icon=":material/more_horiz:",
                key=f"{key}-details",
                help="Show more detail.",
                type="tertiary",
                on_click=_open_details,
                args=(key,),
            )
        st.button(
            "",
            icon=":material/close:",
            key=f"{key}-hide",
            help="Hide this card until the page is reloaded.",
            type="tertiary",
            on_click=hide,
            args=(key,),
        )


def _draw(spec: Card) -> None:
    key = card_key(spec.id)
    if key in hidden_keys():
        # The reader hid the card from inside the card's own fragment,
        # which redraws nothing but itself. Only the page knows how the
        # remaining cards pair up into rows, so it has to run again for
        # this one to leave the page at all.
        st.rerun(scope="app")
    # A card's content is drawn in one place at a time: on the page, or
    # in the modal, never both. Anything inside it that keys a widget or
    # a container of its own - the risk gauges, the page through recent
    # fills - would otherwise be asked for twice in the same run, which
    # Streamlit refuses.
    in_modal = (
        spec.details is not None and st.session_state.get(_DETAILS) == key
    )
    if in_modal:
        with st.container(border=True, key=key):
            with st.expander(f"{spec.icon} {spec.title}", expanded=True):
                st.caption("Details are open.")
            _chrome(replace(spec, actions=None), key)
        _details_dialog(spec)
    else:
        _execute(spec, _render)


def _render(spec: Card) -> None:
    key = card_key(spec.id)
    if spec.frame == "bare":
        # A region of the page rather than a card on it: the body alone,
        # with nothing to title, fold or hide.
        with st.container(key=key):
            spec.body()
        return
    accent = spec.accent() if callable(spec.accent) else spec.accent
    if rule := accent_rule(key, accent):
        st.html(rule)
    with st.container(border=True, key=key):
        # Collapse is browser-only: the content remains live.
        with st.expander(f"{spec.icon} {spec.title}", expanded=True):
            spec.body()
        _chrome(spec, key)


def _execute(spec: Card, render: Callable[[Card], None]) -> None:
    metrics = st.session_state.setdefault(_METRICS, {}).setdefault(
        spec.id, CardMetrics()
    )
    started = perf_counter()
    metrics.refresh_count += 1
    metrics.last_refresh_at = datetime.now(timezone.utc)
    metrics.load_ms = 0.0
    # Replace partial output on failure, so stale figures cannot look current.
    output = st.empty()
    try:
        bound = spec
        with output.container():
            if spec.load is not None:
                loading = perf_counter()
                try:
                    with st.spinner(f"Loading {spec.title}…"):
                        model = spec.load()
                finally:
                    metrics.load_ms = (perf_counter() - loading) * 1000
                bound = replace(
                    spec,
                    body=partial(spec.body, model),
                    actions=partial(spec.actions, model)
                    if spec.actions
                    else None,
                    details=partial(spec.details, model)
                    if spec.details
                    else None,
                    accent=partial(spec.accent, model)
                    if callable(spec.accent)
                    else spec.accent,
                )
            render(bound)
    except Exception:
        # Streamlit's stop/rerun control signals inherit BaseException and
        # must propagate. Ordinary card failures stay inside this boundary.
        metrics.error_count += 1
        _LOG.exception("Card %s failed", spec.id)
        with output.container():
            st.error(f"{spec.title} could not refresh. Try refreshing again.")
            st.button("Retry", key=f"{card_key(spec.id)}-retry")
            st.button(
                "Hide card",
                key=f"{card_key(spec.id)}-failure-hide",
                on_click=_hide_and_repack,
                args=(card_key(spec.id),),
            )
    finally:
        metrics.total_ms = (perf_counter() - started) * 1000
        metrics.render_ms = max(0.0, metrics.total_ms - metrics.load_ms)
        _LOG.debug("Card %s: %s", spec.id, metrics)


def refresh_every(spec: Card) -> float | None:
    """
    Returns: How often the card redraws itself, and nothing at all for a
    card that does not refresh or a reader who has switched refreshing
    off.

    Read afresh on every run rather than held: a reader changing the
    interval on the settings page expects the cards to follow. A card
    asking for an interval of its own still falls silent with the rest
    of them when the reader switches refreshing off.
    """
    dashboard_interval = state.refresh_interval()
    if not spec.refresh or dashboard_interval is None:
        return None
    return (
        dashboard_interval
        if spec.refresh_interval is None
        else spec.refresh_interval
    )


def _fragment_of(spec: Card) -> Callable[[], None]:
    """
    Returns: The card's render pass, named for the card.

    Streamlit identifies a fragment by the name of the function behind it
    and where on the page it was declared, so a plain closure would give
    every card on a page the same identity.
    """

    def draw() -> None:
        _draw(spec)

    draw.__qualname__ = card_key(spec.id)
    return draw


def card(spec: Card) -> None:
    """
    One card, drawn inside a refreshing fragment of its own.

    A fragment redraws only itself, so a card's timer, its pagination and
    its details open and shut without any other card on the page reading
    the recording again or rebuilding a chart. It costs a round trip per
    card rather than one for the page; only the requested card does work.

    The card's own id keys the fragment, which is what lets anything else
    ask for this one card to be redrawn by name.
    """
    st.fragment(
        _fragment_of(spec), run_every=refresh_every(spec), key=spec.id
    )()
