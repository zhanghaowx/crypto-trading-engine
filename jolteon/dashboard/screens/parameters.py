import streamlit as st

from jolteon.dashboard.cards import engine_parameters, viewer_settings

_TABS = ("Engine", "Dashboard")

# The key names the query parameter as well as the widget, so the tab a
# reader is on survives a refresh and travels in a shared link.
_TAB_KEY = "tab"

_requested = st.query_params.get(_TAB_KEY, "")
engine_tab, dashboard_tab = st.tabs(
    list(_TABS),
    key=_TAB_KEY,
    # Without a rerun on change the server never learns which tab is
    # open, and neither the URL below nor `.open` could be answered.
    on_change="rerun",
    default=_requested if _requested in _TABS else _TABS[0],
)

_open = st.session_state.get(_TAB_KEY, _TABS[0])
if _open == _TABS[0]:
    # The tab a page opens on needs no saying, and a parameter left
    # trailing behind would be carried into every link copied from here.
    st.query_params.pop(_TAB_KEY, None)
elif st.query_params.get(_TAB_KEY) != _open:
    st.query_params[_TAB_KEY] = _open

# Each tab's content is built only while it is open. Both tabs' contents
# are built on every run otherwise, and the Engine tab builds a widget
# for every tunable the catalog declares and reads every engine's report
# on them. A fragment then keeps a rerun to the tab the edit happened in.
if engine_tab.open:
    with engine_tab:
        st.fragment(engine_parameters.render)()

if dashboard_tab.open:
    with dashboard_tab:
        st.fragment(viewer_settings.render)()
