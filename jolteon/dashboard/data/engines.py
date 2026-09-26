"""Finds the engine recordings under a root and names what each one is of.

An engine writes one recording per run into its instrument's directory,
`<root>/<exchange>/<symbol>/<run_id>.sqlite`, with the run's log database
beside it as `<run_id>.log.sqlite`. Whether a run read a live feed or
replayed a recording is written into the recording, not into its name.
The `live.sqlite` and `replay.sqlite` that engines used to write every
run of an instrument into are recordings like any other.
"""

from dataclasses import dataclass
from pathlib import Path

import streamlit as st

from jolteon.dashboard.data.runs import latest_engine_run
from jolteon.dashboard.data.sqlite import read_latest_row
from jolteon.engine.core.engine_run import MarketDataMode
from jolteon.engine.core.storage import paths
from jolteon.engine.core.storage.exchange_instrument_directory_discovery import (  # noqa: E501
    discover_exchange_instrument_directories,
)

_LOG_DATABASE_SUFFIX = ".log.sqlite"


@dataclass(frozen=True)
class EngineDatabase:
    """One instrument's recordings, identified by exchange and canonical
    symbol.

    `path` is the recording the Live and Health pages read: the newest one
    whose latest run read a live feed, or the newest of all when every
    run replayed a recording. `log_path` is that recording's log database.
    `recordings` is every recording of the instrument, newest first.
    """

    path: str
    exchange: str
    symbol: str
    log_path: str
    legacy: bool = False
    recordings: tuple[str, ...] = ()

    @property
    def key(self) -> str:
        venue = paths.exchange_directory_name(self.exchange)
        return f"{venue}:{self.symbol}"

    @property
    def label(self) -> str:
        return f"{self.exchange} · {self.symbol}"


# How long a scan of the root is reused for. Below the shortest refresh
# interval the Live page offers, so an auto-refresh still picks up an
# engine that has just started, and above a burst of widget clicks, so
# working through a page does not reopen every engine's recording on each
# one. Nothing else invalidates this: a directory appearing on disk is
# not observable without looking for it.
#
# A caller that compares one scan against another within a single run
# also depends on the reuse: read live, the two would disagree by however
# long the first took.
SCAN_SECONDS = 2.0


@st.cache_data(ttl=SCAN_SECONDS, show_spinner=False)
def engine_databases(root: str) -> list[EngineDatabase]:
    """
    Returns: One entry per instrument something has been recorded for
    under `root`, naming every recording of it and the one the live pages
    read.

    Every engine writes under a directory named after the symbol it
    trades, so the symbols on offer are the directories present. A
    recording is any database in such a directory other than a run's log
    database, which sits beside the run it logs. A directory holding no
    recording yet is not an instrument anything has been recorded for.
    """
    databases = []
    for instrument in discover_exchange_instrument_directories(root):
        recordings = _recordings_newest_first(instrument.path)
        if not recordings:
            continue
        current = _live_recording(recordings)
        databases.append(
            EngineDatabase(
                path=current,
                exchange=instrument.exchange,
                symbol=_recorded_symbol(current, instrument.symbol),
                log_path=_log_database(current),
                legacy=instrument.legacy,
                recordings=tuple(found.path for found in recordings),
            )
        )
    return databases


@dataclass(frozen=True)
class _Recording:
    path: str
    started_at: float
    market_data_mode: str


def _recordings_newest_first(directory: Path) -> list[_Recording]:
    found = [
        _describe(file)
        for file in directory.glob("*.sqlite")
        if file.is_file()
        and not file.name.endswith(_LOG_DATABASE_SUFFIX)
        and file.name != paths.PARAMETERS
    ]
    return sorted(
        found, key=lambda item: (item.started_at, item.path), reverse=True
    )


def _describe(file: Path) -> _Recording:
    """
    A recording is placed by when its newest run started. One holding no
    run row - made by an engine from before runs were recorded, or by one
    that has only just opened its file - is placed by when the file last
    changed, and is read as though its run had said nothing about where
    its data came from.
    """
    run = latest_engine_run(str(file))
    if run is None:
        return _Recording(
            str(file), file.stat().st_mtime, MarketDataMode.UNKNOWN
        )
    return _Recording(
        str(file), run.started_at.timestamp(), run.market_data_mode
    )


def _live_recording(recordings: list[_Recording]) -> str:
    """
    Returns: The newest recording whose latest run did not replay a
    recording - the engine reading a live feed is what the Live and
    Health pages are about - or the newest of all when every run did.
    """
    return next(
        (
            found.path
            for found in recordings
            if found.market_data_mode != MarketDataMode.RECORDED
        ),
        recordings[0].path,
    )


def _log_database(recording: str) -> str:
    return f"{Path(recording).with_suffix('')}{_LOG_DATABASE_SUFFIX}"


def _recorded_symbol(db_path: str, directory_symbol: str) -> str:
    """
    Returns: The symbol this recording is of, preferring what was
    recorded over the directory it was recorded in - the directory name
    is a spelling the engine chose, while a recorded tick names the pair
    as the venue does.
    """
    latest = read_latest_row(db_path, "bbo_feed")
    if latest is not None and latest.get("symbol"):
        return str(latest["symbol"])
    return directory_symbol
