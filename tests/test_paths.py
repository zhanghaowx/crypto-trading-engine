from jolteon import paths


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


def test_discovers_the_same_symbol_on_two_exchanges(tmp_path):
    paths.symbol_directory(str(tmp_path), "Kraken", "BTC/USD").mkdir(
        parents=True
    )
    paths.symbol_directory(str(tmp_path), "Binance.US", "BTC/USD").mkdir(
        parents=True
    )

    found = paths.session_directories(str(tmp_path))

    assert [(item.exchange, item.symbol) for item in found] == [
        ("Binance.US", "BTC/USD"),
        ("Kraken", "BTC/USD"),
    ]


def test_reads_legacy_kraken_layout(tmp_path):
    legacy = paths.symbol_directory(str(tmp_path), "ETH/USD")
    legacy.mkdir(parents=True)

    assert paths.session_directories(str(tmp_path)) == [
        paths.SessionDirectory("Kraken", "ETH/USD", legacy, legacy=True)
    ]


def test_new_kraken_session_wins_over_duplicate_legacy_session(tmp_path):
    paths.symbol_directory(str(tmp_path), "BTC/USD").mkdir(parents=True)
    current = paths.symbol_directory(str(tmp_path), "Kraken", "BTC/USD")
    current.mkdir(parents=True)

    assert paths.session_directories(str(tmp_path)) == [
        paths.SessionDirectory("Kraken", "BTC/USD", current)
    ]
