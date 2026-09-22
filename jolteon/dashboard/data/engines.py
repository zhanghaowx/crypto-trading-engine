"""Finds the engine recordings under a root and names what each one is of."""

from dataclasses import dataclass

import streamlit as st

from jolteon.dashboard.data.sqlite import read_latest_row
from jolteon.engine.core.storage import paths
from jolteon.engine.core.storage.exchange_instrument_directory_discovery import (  # noqa: E501
    discover_exchange_instrument_directories,
)


@dataclass(frozen=True)
class EngineDatabase:
    """One engine recording identified by exchange and canonical symbol."""

    path: str
    exchange: str
    symbol: str
    log_path: str
    legacy: bool = False

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
    Returns: One entry per symbol something has been recorded for under
    `root`, each naming that instrument's recording and its log database.

    Every engine writes under a directory named after the symbol it
    trades, so the symbols on offer are the directories present. Reading
    the directory rather than matching file names against a pattern is
    also what keeps a log database from being taken for a recording of
    its own: it is a file inside a symbol's directory, not another one
    beside it.
    """
    databases = []
    for instrument in discover_exchange_instrument_directories(root):
        recording = str(instrument.path / f"{paths.LIVE}.sqlite")
        databases.append(
            EngineDatabase(
                path=recording,
                exchange=instrument.exchange,
                symbol=_recorded_symbol(recording, instrument.symbol),
                log_path=str(instrument.path / f"{paths.LIVE}.log.sqlite"),
                legacy=instrument.legacy,
            )
        )
    return databases


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
