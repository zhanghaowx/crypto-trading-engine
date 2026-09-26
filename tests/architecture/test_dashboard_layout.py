"""The dashboard's pages must not live in a folder Streamlit reserves.

Streamlit takes a folder named `pages` beside an app's entrypoint for its
legacy multipage layout, decided once per process before any script runs.
A session whose first request is any URL but the root - a bookmark to
Health, a reload of Parameters - then has that page's file executed on its
own, without the entrypoint that seeds the session state every page reads,
and the dashboard opens on a traceback. The pages live under `screens`.
"""

import pathlib

DASHBOARD = (
    pathlib.Path(__file__).resolve().parents[2] / "jolteon" / "dashboard"
)


def test_no_folder_beside_the_entrypoint_is_named_pages():
    assert (DASHBOARD / "main.py").is_file()
    assert not (DASHBOARD / "pages").exists(), (
        "jolteon/dashboard/pages would put Streamlit into its legacy "
        "multipage mode; the pages belong under jolteon/dashboard/screens. "
        "See AGENTS.md."
    )


def test_every_screen_the_entrypoint_navigates_to_is_there():
    entrypoint = (DASHBOARD / "main.py").read_text(encoding="utf-8")
    screens = sorted(p.name for p in (DASHBOARD / "screens").glob("*.py"))

    assert screens == [
        "__init__.py",
        "health.py",
        "live.py",
        "parameters.py",
        "post_trade.py",
    ]
    for screen in screens:
        if screen != "__init__.py":
            assert f'"screens/{screen}"' in entrypoint, screen
