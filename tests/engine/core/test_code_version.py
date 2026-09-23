import subprocess
from unittest.mock import patch

from jolteon.engine.core.code_version import (
    UNKNOWN_COMMIT,
    commit_sha,
    working_tree_is_clean,
)


def _uncached(function, *, stdout: str = "", returncode: int = 0, error=None):
    """Call `function` with git stubbed, past its cache."""
    function.cache_clear()
    try:
        with patch("subprocess.run") as run:
            if error is not None:
                run.side_effect = error
            else:
                run.return_value = subprocess.CompletedProcess(
                    args=(), returncode=returncode, stdout=stdout
                )
            return function()
    finally:
        function.cache_clear()


def test_the_commit_the_engine_is_running_is_reported():
    assert _uncached(commit_sha, stdout="abc123def\n") == "abc123def"


def test_a_checkout_with_no_uncommitted_change_is_reported_clean():
    assert _uncached(working_tree_is_clean, stdout="\n") is True


def test_a_checkout_with_an_uncommitted_change_is_reported_dirty():
    assert (
        _uncached(working_tree_is_clean, stdout=" M jolteon/x.py\n") is False
    )


def test_a_run_outside_a_checkout_claims_no_commit():
    """An installed package away from its source has no commit to report,
    and a made-up one would make the run read as reproducible."""
    assert _uncached(commit_sha, returncode=128) == UNKNOWN_COMMIT
    assert _uncached(working_tree_is_clean, returncode=128) is None


def test_a_machine_without_git_claims_no_commit():
    assert (
        _uncached(commit_sha, error=FileNotFoundError("git")) == UNKNOWN_COMMIT
    )
    assert (
        _uncached(working_tree_is_clean, error=FileNotFoundError("git"))
        is None
    )


def test_git_taking_too_long_claims_no_commit():
    assert (
        _uncached(
            commit_sha, error=subprocess.TimeoutExpired(cmd="git", timeout=5)
        )
        == UNKNOWN_COMMIT
    )


def test_the_commit_is_asked_for_once():
    commit_sha.cache_clear()
    try:
        with patch("subprocess.run") as run:
            run.return_value = subprocess.CompletedProcess(
                args=(), returncode=0, stdout="abc123\n"
            )
            commit_sha()
            commit_sha()
        assert run.call_count == 1
    finally:
        commit_sha.cache_clear()


def test_this_repository_reports_its_own_commit():
    commit_sha.cache_clear()
    try:
        assert len(commit_sha()) == 40
    finally:
        commit_sha.cache_clear()
