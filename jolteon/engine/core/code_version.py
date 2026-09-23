"""Which commit of this repository the running engine was built from."""

import subprocess
from functools import lru_cache
from pathlib import Path

_HEAD_COMMAND = ("git", "rev-parse", "HEAD")
_UNCOMMITTED_COMMAND = ("git", "status", "--porcelain")
_TIMEOUT_SECONDS = 5.0

# What is recorded where the commit cannot be established at all, rather
# than a plausible-looking value that would make a run read as
# reproducible when it is not.
UNKNOWN_COMMIT = ""


@lru_cache(maxsize=1)
def commit_sha() -> str:
    """
    Returns: The commit the engine is running, and UNKNOWN_COMMIT where
    there is no repository to ask - an installed package away from its
    source has no commit of its own.
    """
    found = _git(_HEAD_COMMAND)
    return found.strip() if found is not None else UNKNOWN_COMMIT


@lru_cache(maxsize=1)
def working_tree_is_clean() -> bool | None:
    """
    Returns: Whether the checkout holds no uncommitted change, and
    nothing at all where there is no repository to ask.

    A run off a dirty tree is not reproducible from its commit alone, so
    this is recorded beside the commit rather than left to be assumed.
    """
    found = _git(_UNCOMMITTED_COMMAND)
    return None if found is None else not found.strip()


def _git(command: tuple[str, ...]) -> str | None:
    """
    Returns: What git printed, and nothing at all when it cannot be run
    or refuses - most often because the engine is not running out of a
    checkout.
    """
    try:
        completed = subprocess.run(
            command,
            cwd=Path(__file__).resolve().parent,
            capture_output=True,
            text=True,
            timeout=_TIMEOUT_SECONDS,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    return completed.stdout if completed.returncode == 0 else None
