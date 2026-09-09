"""CSS injected into the dashboard's sidebar chrome."""

SIDEBAR_CSS = """
<style>
div[data-testid="stSidebarHeader"] {
    position: relative;
    justify-content: center;
}
div[data-testid="stSidebarCollapseButton"] {
    position: absolute;
    right: 0;
}
a[data-testid="stSidebarNavLink"] {
    font-size: 1.15rem;
}
div[data-testid="stHeaderLogo"] {
    display: none;
}
</style>
"""
