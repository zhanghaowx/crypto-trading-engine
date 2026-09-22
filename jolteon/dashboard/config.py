"""How the dashboard was started: the arguments it was given."""

import argparse

from jolteon.engine.core.storage import paths


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    # The engine's own default. Every symbol traded under it has a
    # directory there, which is how the symbols on offer are found.
    parser.add_argument("--root", default=paths.DEFAULT_ROOT)
    # Left unset, each engine's log database is found in that engine's own
    # directory; give this to pin every page to one log file instead.
    parser.add_argument("--log-db", default="")
    # Defaults to the one store at the root of --root, shared by every
    # symbol. The dashboard is the only writer of it; the engine reads.
    parser.add_argument("--params-db", default="")
    # streamlit forwards its own args when not separated by "--"; ignore them.
    args, _ = parser.parse_known_args()
    return args
