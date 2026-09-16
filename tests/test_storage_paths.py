from jolteon.engine.core.storage import paths


def test_new_sessions_use_exchange_first_paths(tmp_path):
    assert paths.recording(str(tmp_path), "Binance.US", "BTC/USD") == str(
        tmp_path / "binance-us" / "BTC-USD" / "live.sqlite"
    )
    assert paths.log_file(str(tmp_path), "Kraken", "BTC/USD") == str(
        tmp_path / "kraken" / "BTC-USD" / "live.log"
    )


def test_each_exchange_has_its_own_parameter_store(tmp_path):
    assert paths.parameter_store(str(tmp_path), "Kraken") == str(
        tmp_path / "kraken" / "parameters.sqlite"
    )
    assert paths.parameter_store(str(tmp_path), "Binance.US") == str(
        tmp_path / "binance-us" / "parameters.sqlite"
    )
