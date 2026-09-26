from jolteon.engine.core.storage import paths

RUN_ID = "20260926T100000Z-abcd1234"


def test_each_run_has_its_own_recording_and_log(tmp_path):
    assert paths.run_recording(
        str(tmp_path), "Binance.US", "BTC/USD", RUN_ID
    ) == str(tmp_path / "binance-us" / "BTC-USD" / f"{RUN_ID}.sqlite")
    assert paths.run_log_file(
        str(tmp_path), "Kraken", "BTC/USD", RUN_ID
    ) == str(tmp_path / "kraken" / "BTC-USD" / f"{RUN_ID}.log")
    assert paths.run_log_database(
        str(tmp_path), "Kraken", "BTC/USD", RUN_ID
    ) == str(tmp_path / "kraken" / "BTC-USD" / f"{RUN_ID}.log.sqlite")


def test_recordings_made_before_one_file_per_run_are_still_addressable(
    tmp_path,
):
    assert paths.recording(str(tmp_path), "Binance.US", "BTC/USD") == str(
        tmp_path / "binance-us" / "BTC-USD" / "live.sqlite"
    )
    assert paths.recording(
        str(tmp_path), "Kraken", "BTC/USD", paths.REPLAY
    ) == str(tmp_path / "kraken" / "BTC-USD" / "replay.sqlite")
    assert paths.log_file(str(tmp_path), "Kraken", "BTC/USD") == str(
        tmp_path / "kraken" / "BTC-USD" / "live.log"
    )
    assert paths.log_database(str(tmp_path), "Kraken", "BTC/USD") == str(
        tmp_path / "kraken" / "BTC-USD" / "live.log.sqlite"
    )


def test_each_exchange_has_its_own_parameter_store(tmp_path):
    assert paths.parameter_store(str(tmp_path), "Kraken") == str(
        tmp_path / "kraken" / "parameters.sqlite"
    )
    assert paths.parameter_store(str(tmp_path), "Binance.US") == str(
        tmp_path / "binance-us" / "parameters.sqlite"
    )
