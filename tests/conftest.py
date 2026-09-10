import sys

import pytest

from jolteon.core.event.signal_manager import SignalManager


# each test runs on cwd to its temp dir
@pytest.fixture(autouse=True)
def go_to_tmpdir(request):
    # Get the fixture dynamically by its name.
    tmpdir = request.getfixturevalue("tmpdir")
    # ensure local test created packages can be imported
    sys.path.insert(0, str(tmpdir))
    # Chdir only for the duration of the test.
    with tmpdir.as_cwd():
        yield


@pytest.fixture(autouse=True)
def disconnect_all_signals():
    """Blinker signals are process-global, so a test that connects a
    receiver and forgets to disconnect it can leak into a later test -
    only visible in a full suite run, not in isolation, since it depends
    on GC timing. No test relies on a signal connection surviving across
    tests, so disconnect everything unconditionally after each one."""
    yield
    SignalManager.disconnect_all()
