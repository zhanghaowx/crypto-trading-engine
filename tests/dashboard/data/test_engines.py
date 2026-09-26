import os
import sqlite3
import time
from pathlib import Path

from jolteon.dashboard.data import engines
from jolteon.dashboard.data.engines import engine_databases
from jolteon.engine.core.engine_run import MarketDataMode
from jolteon.engine.core.storage import paths
from tests.dashboard.conftest import exchange_recording, recording

EXCHANGE = "Binance.US"
SYMBOL = "BTC/USD"


def run_recording(
    root,
    run_id: str,
    started_at: float,
    market_data_mode: str = MarketDataMode.REALTIME,
    symbol: str = SYMBOL,
) -> str:
    """One run's recording, laid out where an engine would lay it and
    holding the run row an engine writes first."""
    path = paths.run_recording(str(root), EXCHANGE, symbol, run_id)
    _write_run(path, run_id, started_at, market_data_mode, symbol)
    return path


def _write_run(
    path: str, run_id: str, started_at: float, market_data_mode, symbol: str
) -> None:
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    try:
        conn.execute(
            "CREATE TABLE engine_run "
            "(run_id TEXT PRIMARY KEY, exchange TEXT, symbol TEXT, "
            "started_at REAL, ended_at REAL, execution_mode TEXT, "
            "market_data_mode TEXT)"
        )
        conn.execute(
            "INSERT INTO engine_run VALUES (?, ?, ?, ?, NULL, 'SIMULATED', ?)",
            (run_id, EXCHANGE, symbol, started_at, str(market_data_mode)),
        )
        conn.execute("CREATE TABLE bbo_feed (timestamp REAL, symbol TEXT)")
        conn.execute(
            "INSERT INTO bbo_feed VALUES (?, ?)", (started_at, symbol)
        )
        conn.commit()
    finally:
        conn.close()


def test_same_symbol_on_two_exchanges_has_two_dashboard_identities(tmp_path):
    kraken = exchange_recording(tmp_path, "Kraken", "BTC/USD")
    binance = exchange_recording(tmp_path, "Binance.US", "BTC/USD")

    found = engine_databases(str(tmp_path))

    assert [(engine.key, engine.path) for engine in found] == [
        ("binance-us:BTC/USD", binance),
        ("kraken:BTC/USD", kraken),
    ]


def test_finds_every_symbol_that_has_been_traded(tmp_path):
    recording(tmp_path, "ETH/USD")
    recording(tmp_path, "BTC/USD")

    found = engine_databases(str(tmp_path))

    assert ["BTC/USD", "ETH/USD"] == [e.symbol for e in found]


def test_a_symbol_directory_holds_its_own_recording_and_log(tmp_path):
    path = recording(tmp_path, "ETH/USD")

    found = engine_databases(str(tmp_path))

    assert found[0].path == path
    assert found[0].path == paths.recording(str(tmp_path), "ETH/USD")
    assert found[0].log_path == paths.log_database(str(tmp_path), "ETH/USD")
    assert found[0].recordings == (path,)


def test_orders_an_instruments_runs_newest_first_by_when_they_started(
    tmp_path,
):
    """
    Neither the file name nor the file time is the order: a run is placed
    by the start its own row records.
    """
    newest = run_recording(tmp_path, "run-b", started_at=3_000)
    middle = run_recording(tmp_path, "run-c", started_at=2_000)
    oldest = run_recording(tmp_path, "run-a", started_at=1_000)
    later = time.time() + 3_600
    os.utime(oldest, (later, later))

    found = engine_databases(str(tmp_path))

    assert found[0].recordings == (newest, middle, oldest)
    assert found[0].path == newest
    assert found[0].log_path == paths.run_log_database(
        str(tmp_path), EXCHANGE, SYMBOL, "run-b"
    )


def test_a_live_run_outranks_a_newer_replay(tmp_path):
    """
    Live and Health are about the engine reading a live feed. A replay
    that started later is a newer recording, not a newer engine.
    """
    live = run_recording(tmp_path, "live-run", started_at=1_000)
    replay = run_recording(
        tmp_path,
        "replay-run",
        started_at=2_000,
        market_data_mode=MarketDataMode.RECORDED,
    )

    found = engine_databases(str(tmp_path))

    assert found[0].recordings == (replay, live)
    assert found[0].path == live
    assert found[0].log_path == paths.run_log_database(
        str(tmp_path), EXCHANGE, SYMBOL, "live-run"
    )


def test_an_instrument_only_ever_replayed_reads_its_newest_replay(tmp_path):
    run_recording(
        tmp_path,
        "first-replay",
        started_at=1_000,
        market_data_mode=MarketDataMode.RECORDED,
    )
    newest = run_recording(
        tmp_path,
        "second-replay",
        started_at=2_000,
        market_data_mode=MarketDataMode.RECORDED,
    )

    found = engine_databases(str(tmp_path))

    assert found[0].path == newest
    assert found[0].recordings[0] == newest


def test_a_recording_with_no_run_row_is_placed_by_its_file_time(tmp_path):
    """
    An engine from before runs were recorded left no row to date its
    recording by, and one that has only just started has not written
    its row yet.
    """
    dated = run_recording(tmp_path, "dated", started_at=1_000)
    undated = exchange_recording(tmp_path, EXCHANGE, SYMBOL)

    found = engine_databases(str(tmp_path))

    assert found[0].recordings == (undated, dated)
    assert found[0].path == undated

    os.utime(undated, (500, 500))
    engine_databases.clear()
    found = engine_databases(str(tmp_path))

    assert found[0].recordings == (dated, undated)
    assert found[0].path == dated


def test_recordings_made_before_one_file_per_run_are_found(tmp_path):
    """
    Engines used to write every run of an instrument into `live.sqlite`
    or `replay.sqlite`. Both are recordings like any other, and which one
    the live pages read is still decided by what the runs recorded.
    """
    live = exchange_recording(tmp_path, EXCHANGE, SYMBOL)
    replay = paths.recording(str(tmp_path), EXCHANGE, SYMBOL, paths.REPLAY)
    _write_run(
        replay,
        "replayed",
        started_at=time.time() + 60,
        market_data_mode=MarketDataMode.RECORDED,
        symbol=SYMBOL,
    )

    found = engine_databases(str(tmp_path))

    assert found[0].recordings == (replay, live)
    assert found[0].path == live
    assert found[0].log_path == paths.log_database(
        str(tmp_path), EXCHANGE, SYMBOL
    )


def test_log_and_parameter_databases_are_not_recordings(tmp_path):
    run = run_recording(tmp_path, "the-run", started_at=1_000)
    sqlite3.connect(
        paths.run_log_database(str(tmp_path), EXCHANGE, SYMBOL, "the-run")
    ).close()
    sqlite3.connect(Path(run).parent / paths.PARAMETERS).close()
    (Path(run).parent / "the-run.sqlite-wal").touch()

    found = engine_databases(str(tmp_path))

    assert found[0].recordings == (run,)


def test_a_directory_with_no_recording_is_not_an_engine(tmp_path):
    """
    A directory left behind empty, or holding only a run's log, is not an
    instrument anything has been recorded for.
    """
    paths.symbol_directory(str(tmp_path), EXCHANGE, "SOL/USD").mkdir(
        parents=True
    )
    log_only = paths.run_log_database(
        str(tmp_path), EXCHANGE, "ADA/USD", "the-run"
    )
    Path(log_only).parent.mkdir(parents=True)
    sqlite3.connect(log_only).close()
    recording(tmp_path, "ETH/USD")

    found = engine_databases(str(tmp_path))

    assert ["ETH/USD"] == [e.symbol for e in found]


def test_a_symbol_with_no_ticks_is_named_after_its_directory(tmp_path):
    """
    An engine that has only just started has recorded nothing to take a
    symbol from, and still has to be nameable.
    """
    path = paths.run_recording(str(tmp_path), EXCHANGE, "SOL/USD", "started")
    Path(path).parent.mkdir(parents=True)
    sqlite3.connect(path).close()

    found = engine_databases(str(tmp_path))

    assert ["SOL/USD"] == [e.symbol for e in found]


def test_the_tuning_store_is_not_a_symbol(tmp_path):
    """
    One store serves every engine, so it sits at the root beside the
    symbols rather than inside any one of them.
    """
    recording(tmp_path, "ETH/USD")
    parameter_store = paths.parameter_store(str(tmp_path))
    Path(parameter_store).parent.mkdir(parents=True, exist_ok=True)
    sqlite3.connect(parameter_store).close()

    found = engine_databases(str(tmp_path))

    assert ["ETH/USD"] == [e.symbol for e in found]


def test_the_root_is_scanned_once_for_every_reader_of_it(
    tmp_path, monkeypatch
):
    """
    Every page asks which engines are running, and naming one means
    opening its recording to read the symbol back. Asked afresh each
    time, a page with several such readers reopens every engine's file on
    every rerun.
    """
    recording(tmp_path, "ETH/USD")
    recording(tmp_path, "BTC/USD")
    opened = []
    real = engines.read_latest_row
    monkeypatch.setattr(
        engines,
        "read_latest_row",
        lambda db_path, table: opened.append(db_path) or real(db_path, table),
    )

    engine_databases(str(tmp_path))
    engine_databases(str(tmp_path))

    assert len(opened) == 2
