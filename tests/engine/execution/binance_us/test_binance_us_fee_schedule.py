from jolteon.engine.execution.binance_us.fee_schedule import (
    BinanceUsFeeSchedule,
)


def test_defaults_to_zero_maker_fee_and_configurable_taker_fee():
    fees = BinanceUsFeeSchedule()
    assert fees.maker_fee(100, 2) == 0
    assert fees.taker_fee(100, 2) == 1.2

    custom = BinanceUsFeeSchedule(
        maker_rate_value=0.001, taker_rate_value=0.002
    )
    assert custom.maker_rate == 0.001
    assert custom.taker_rate == 0.002
