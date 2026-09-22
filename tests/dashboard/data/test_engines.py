import sqlite3
from pathlib import Path

from jolteon.dashboard.data import engines
from jolteon.dashboard.data.engines import engine_databases
from jolteon.engine.core.storage import paths
from tests.dashboard.conftest import exchange_recording, recording


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


def test_a_symbol_with_no_ticks_is_named_after_its_directory(tmp_path):
    """
    An engine that has only just started has recorded nothing to take a
    symbol from, and still has to be nameable.
    """
    paths.symbol_directory(str(tmp_path), "SOL/USD").mkdir(parents=True)

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
