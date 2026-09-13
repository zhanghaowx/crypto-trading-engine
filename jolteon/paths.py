"""
Where a session's files live.

One engine trades one symbol, and everything that engine writes goes in a
directory of its own named after that symbol - its recording, its log,
and the database that log is mirrored into:

    <root>/
        parameters.sqlite
        BTC-USD/
            live.sqlite
            live.log
            live.log.sqlite
        ETH-USD/
            live.sqlite
            ...

A second engine on another symbol writes alongside the first without
either knowing about the other, and the dashboard finds every symbol by
listing the root rather than by matching names against a pattern - which
is what it used to do, and what led it to mistake a log database for a
symbol of its own.

The tuning store is the exception and sits at the root, because it is
shared: one store serves every engine, and which symbol a value applies
to is a column inside it rather than where the file sits.

Both the engine and the dashboard read this module. Neither imports the
other, so the layout they have to agree on lives here instead.
"""

from pathlib import Path

DEFAULT_ROOT = "/tmp/jolteon"

# What a session is called within a symbol's directory. A replay records
# a fresh session from old data, so it must not land on top of what a
# live session recorded for the same symbol.
LIVE = "live"
REPLAY = "replay"

_PARAMETERS = "parameters.sqlite"


def as_directory_name(symbol: str) -> str:
    """
    Returns: The symbol as it is spelled on disk, since the separator a
    venue writes a pair with is also a path separator.
    """
    return symbol.replace("/", "-")


def as_symbol(directory_name: str) -> str:
    """
    Returns: The symbol a directory was named after.

    The last separator is the one that divides the pair, so a base asset
    spelled with a dash of its own survives the round trip.
    """
    base, separator, quote = directory_name.rpartition("-")
    return f"{base}/{quote}" if separator else directory_name


def symbol_directory(root: str, symbol: str) -> Path:
    return Path(root) / as_directory_name(symbol)


def recording(root: str, symbol: str, session: str = LIVE) -> str:
    """Where a session records every signal it publishes."""
    return str(symbol_directory(root, symbol) / f"{session}.sqlite")


def log_file(root: str, symbol: str, session: str = LIVE) -> str:
    """
    Where a session writes its log. Its database sits beside it under the
    same name, which is what the logger appends `.sqlite` to.
    """
    return str(symbol_directory(root, symbol) / f"{session}.log")


def parameter_store(root: str) -> str:
    return str(Path(root) / _PARAMETERS)


def traded_symbols(root: str) -> list[str]:
    """
    Returns: Every symbol something has been recorded for, taken from the
    directories present.

    An empty list for a root nothing has run under yet, which is an
    ordinary state rather than a failure: the dashboard is often open
    before the first engine starts.
    """
    directory = Path(root)
    if not directory.is_dir():
        return []
    return sorted(
        as_symbol(child.name)
        for child in directory.iterdir()
        if child.is_dir()
    )


def prepare(*file_paths: str) -> None:
    """
    Makes each file's directory, so the first write to it does not fail
    on a symbol nothing has run for before.
    """
    for path in file_paths:
        Path(path).parent.mkdir(parents=True, exist_ok=True)
