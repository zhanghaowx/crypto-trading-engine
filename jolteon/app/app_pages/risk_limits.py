import streamlit as st

from jolteon.app.components import BadgeColor, card_grid, warn_if_no_db
from jolteon.app.data import as_datetime, read_table


def risk_limit_badge(utilization: float) -> tuple[str, BadgeColor, str]:
    if utilization >= 0.9:
        return "Near Limit", "red", ":material/error:"
    if utilization >= 0.7:
        return "Elevated", "orange", ":material/warning:"
    return "OK", "green", ":material/check_circle:"


def render() -> None:
    if not warn_if_no_db():
        return

    risk = read_table(st.session_state.db_path, "risk_limit_snapshot")
    if risk.empty:
        st.info(
            "No risk limit data recorded yet "
            "(no strategy is live, or nothing has flushed to disk yet)."
        )
        return

    risk = risk.sort_values("timestamp")
    risk["time"] = as_datetime(risk["timestamp"])
    groups = list(risk.groupby(["name", "symbol"]))

    for (name, symbol), history in card_grid(groups, columns=3):
        latest = history.iloc[-1]
        maximum = latest["maximum"]
        utilization = (
            min(abs(latest["current"]) / maximum, 1.0) if maximum else 0.0
        )
        label, color, icon = risk_limit_badge(utilization)

        st.markdown(f"**{name.title()}**")
        st.caption(symbol)
        st.badge(label, color=color, icon=icon)
        st.progress(utilization)
        st.caption(
            f"{latest['current']:.4f} / ±{maximum:.4f} ({utilization:.0%})"
        )
        st.line_chart(history.set_index("time")[["current"]], height=120)
