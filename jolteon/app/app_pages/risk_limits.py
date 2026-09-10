import base64
import math

import altair as alt
import streamlit as st

from jolteon.app.components import (
    BadgeColor,
    card_grid,
    style_chart,
    warn_if_no_db,
)
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

# Gauge axis-label type size, and the breathing room kept between the
# widest label and the edge of the viewBox.
LABEL_FONT_SIZE = 12
LABEL_PADDING = 4
# Half-width of the viewBox when no label needs extra room.
DEFAULT_VIEWBOX_HALF_WIDTH = 92

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

    hi_label = f"±{_fmt_bound(maximum)}"
    # Centre each bound label under its end of the colorbar ring so the pair
    # stays balanced however wide the formatted bound turns out to be, and
    # drop them clear of the track's stroke, which reaches half a
    # stroke-width below the arc endpoints at y = cy.
    lo_x, hi_x = cx - r_ring, cx + r_ring
    label_y = cy + track_stroke / 2 + 10

    # A centred label overhangs its anchor by half its width, so widen the
    # viewBox — symmetrically, to keep the gauge centred — until the longest
    # bound fits. Digits advance about 0.6em in Inter, punctuation about half
    # that; an approximation is fine, it only sets how much air is reserved.
    label_width = sum(
        LABEL_FONT_SIZE * (0.3 if char in ".," else 0.6) for char in hi_label
    )
    half_width = max(
        DEFAULT_VIEWBOX_HALF_WIDTH, r_ring + label_width / 2 + LABEL_PADDING
    )

    svg = f"""
    <svg xmlns="http://www.w3.org/2000/svg"
         viewBox="{cx - half_width:.2f} 14 {2 * half_width:.2f} 112">
      {colorbar}
      <path d="{track_arc}" fill="none" stroke="{GAUGE_TRACK_COLOR}"
            stroke-width="{track_stroke}" stroke-linecap="round" />
      <path d="{track_arc}" fill="none" stroke="{color}"
            stroke-width="{track_stroke}" stroke-linecap="round"
            stroke-dasharray="{circumference:.2f}"
            stroke-dashoffset="{offset:.2f}" />
      <text x="{lo_x:.2f}" y="{label_y:.2f}" text-anchor="middle"
            font-size="{LABEL_FONT_SIZE}" fill="#5A5F4E"
            font-family="'Inter', sans-serif">0</text>
      <text x="{hi_x:.2f}" y="{label_y:.2f}" text-anchor="middle"
            font-size="{LABEL_FONT_SIZE}" fill="#5A5F4E"
            font-family="'Inter', sans-serif">{hi_label}</text>
      <text x="{cx}" y="{cy - 8}" text-anchor="middle" font-size="30"
            font-weight="700" fill="#15171C"
            font-family="'Space Grotesk', sans-serif">{utilization:.0%}</text>
    </svg>
    """
    encoded = base64.b64encode(svg.encode()).decode()
    return f'<img src="data:image/svg+xml;base64,{encoded}" width="100%">'


def _history_chart(history) -> alt.Chart:
    """
    Sparkline of a limit's measured value over time. Built with Altair
    rather than `st.line_chart` so it can carry the card's white background
    and top padding (see `style_chart`), which the built-in chart commands
    don't expose.
    """
    return style_chart(
        alt.Chart(history)
        .mark_line()
        .encode(
            x=alt.X("time:T", title=None),
            y=alt.Y("current:Q", title=None),
        )
        .properties(height=120)
    )


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
    window_seconds = st.session_state.chart_window_minutes * 60

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
        # The gauge always reflects the latest snapshot; only the sparkline
        # is windowed, the same stretch of history Market Data's chart uses.
        cutoff = history["timestamp"].max() - window_seconds
        chart_history = history[history["timestamp"] >= cutoff]
        # A horizontal container rather than `st.columns`: the gauge keeps its
        # natural width and the chart takes whatever is left, so the two sit
        # side by side without the empty space proportional columns leave
        # around a fixed-size gauge in a wide card.
        with st.container(
            horizontal=True, vertical_alignment="center", gap="small"
        ):
            st.html(_gauge_svg(utilization, gauge_color, maximum), width=200)
            st.altair_chart(_history_chart(chart_history), width="stretch")
