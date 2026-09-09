import base64
import math

import streamlit as st

from jolteon.app.components import BadgeColor, card_grid, warn_if_no_db
from jolteon.app.data import as_datetime, read_table

# Solid versions of the theme's semantic colors (config.toml), used for the
# gauge arc - `st.progress` has no color option, so the gauge is drawn as
# inline SVG via `st.html`, the same escape hatch health.py uses for tile
# backgrounds.
GAUGE_COLORS: dict[BadgeColor, str] = {
    "green": "#4E9F1F",
    "orange": "#E8873C",
    "red": "#E2574C",
}
GAUGE_TRACK_COLOR = "#D3D9C6"

# Utilization thresholds shared by the badge and the gauge's colorbar zones,
# so the ring around the gauge always reflects the same OK/Elevated/Near
# Limit bands the badge text uses.
ELEVATED_THRESHOLD = 0.7
NEAR_LIMIT_THRESHOLD = 0.9


def risk_limit_badge(utilization: float) -> tuple[str, BadgeColor, str]:
    if utilization >= NEAR_LIMIT_THRESHOLD:
        return "Near Limit", "red", ":material/error:"
    if utilization >= ELEVATED_THRESHOLD:
        return "Elevated", "orange", ":material/warning:"
    return "OK", "green", ":material/check_circle:"


def _fmt_bound(value: float) -> str:
    return f"{value:,.0f}" if abs(value) >= 100 else f"{value:g}"


def _arc_point(
    cx: float, cy: float, r: float, frac: float
) -> tuple[float, float]:
    """A point on the gauge's semicircle at `frac` (0-1) of its sweep, going
    from the leftmost point (frac=0) clockwise over the top to the
    rightmost point (frac=1)."""
    angle = math.pi * (1 - frac)
    return cx + r * math.cos(angle), cy - r * math.sin(angle)


def _arc_path(
    cx: float, cy: float, r: float, frac0: float, frac1: float
) -> str:
    x0, y0 = _arc_point(cx, cy, r, frac0)
    x1, y1 = _arc_point(cx, cy, r, frac1)
    return f"M {x0:.2f} {y0:.2f} A {r} {r} 0 0 1 {x1:.2f} {y1:.2f}"


def _gauge_svg(utilization: float, color: str, maximum: float) -> str:
    """A semicircular utilization gauge: a value arc (length proportional to
    `utilization`, drawn via stroke-dasharray on a half-circle path) plus an
    outer colorbar ring divided into the same OK/Elevated/Near Limit zones
    as the badge, with axis labels for the limit's lower and upper bounds.

    Rendered as a base64 data-URI <img>, not an inline <svg>: `st.html`
    sanitizes with DOMPurify's "html" profile, which strips <svg> outright,
    but permits data: URIs on <img>.
    """
    cx, cy = 110, 100
    r_track, track_stroke = 60, 16
    ring_gap, ring_thickness = 5, 9
    r_ring = r_track + track_stroke / 2 + ring_gap + ring_thickness / 2
    r_label = r_ring + 12

    track_arc = _arc_path(cx, cy, r_track, 0, 1)
    circumference = math.pi * r_track
    offset = circumference * (1 - utilization)

    zones = [
        (0.0, ELEVATED_THRESHOLD, GAUGE_COLORS["green"]),
        (ELEVATED_THRESHOLD, NEAR_LIMIT_THRESHOLD, GAUGE_COLORS["orange"]),
        (NEAR_LIMIT_THRESHOLD, 1.0, GAUGE_COLORS["red"]),
    ]
    colorbar = "\n".join(
        f'<path d="{_arc_path(cx, cy, r_ring, f0, f1)}" fill="none" '
        f'stroke="{zone_color}" stroke-width="{ring_thickness}" />'
        for f0, f1, zone_color in zones
    )

    lo_x, lo_y = _arc_point(cx, cy, r_label, 0)
    hi_x, hi_y = _arc_point(cx, cy, r_label, 1)
    hi_label = f"±{_fmt_bound(maximum)}"

    svg = f"""
    <svg xmlns="http://www.w3.org/2000/svg" viewBox="18 14 184 96">
      {colorbar}
      <path d="{track_arc}" fill="none" stroke="{GAUGE_TRACK_COLOR}"
            stroke-width="{track_stroke}" stroke-linecap="round" />
      <path d="{track_arc}" fill="none" stroke="{color}"
            stroke-width="{track_stroke}" stroke-linecap="round"
            stroke-dasharray="{circumference:.2f}"
            stroke-dashoffset="{offset:.2f}" />
      <text x="{lo_x:.2f}" y="{lo_y + 4:.2f}" text-anchor="start"
            font-size="12" fill="#5A5F4E"
            font-family="'Inter', sans-serif">0</text>
      <text x="{hi_x:.2f}" y="{hi_y + 4:.2f}" text-anchor="end"
            font-size="12" fill="#5A5F4E"
            font-family="'Inter', sans-serif">{hi_label}</text>
      <text x="{cx}" y="{cy - 8}" text-anchor="middle" font-size="30"
            font-weight="700" fill="#15171C"
            font-family="'Space Grotesk', sans-serif">{utilization:.0%}</text>
    </svg>
    """
    encoded = base64.b64encode(svg.encode()).decode()
    return f'<img src="data:image/svg+xml;base64,{encoded}" width="100%">'


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
        with st.container(horizontal=True, vertical_alignment="center"):
            st.caption(symbol, width="content")
            st.badge(label, color=color, icon=icon)
        gauge_color = GAUGE_COLORS.get(color, GAUGE_TRACK_COLOR)
        # A horizontal container rather than `st.columns`: the gauge keeps its
        # natural width and the chart takes whatever is left, so the two sit
        # side by side without the empty space proportional columns leave
        # around a fixed-size gauge in a wide card.
        with st.container(
            horizontal=True, vertical_alignment="center", gap="small"
        ):
            st.html(_gauge_svg(utilization, gauge_color, maximum), width=200)
            st.line_chart(
                history.set_index("time")[["current"]],
                height=120,
                width="stretch",
            )
