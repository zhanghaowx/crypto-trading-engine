import unittest
from datetime import datetime, timedelta
from crypto_trading_engine.market_data.core.candlestick import Candlestick
from crypto_trading_engine.strategy.bull_flag.parameters import Parameters
from crypto_trading_engine.market_data.patterns.bull_flag_pattern import (
    BullFlagPattern,
)


class TestBullFlagPattern(unittest.TestCase):
    def setUp(self):
        self.params = Parameters()
        self.start_time = datetime(2024, 1, 1, 0, 0, 0)
        self.pattern_recognizer = BullFlagPattern(self.params)
        self.candlesticks = [
            Candlestick(
                self.start_time + timedelta(minutes=0),
                duration_in_seconds=60,
                open=100,
                close=110,
                high=120,
                low=90,
            ),
            Candlestick(
                self.start_time + timedelta(minutes=1),
                duration_in_seconds=60,
                open=110,
                close=120,
                high=120,
                low=90,
            ),
            Candlestick(
                self.start_time + timedelta(minutes=2),
                duration_in_seconds=60,
                open=110,
                close=109,
                high=110,
                low=109,
            ),
            Candlestick(
                self.start_time + timedelta(minutes=2),
                duration_in_seconds=60,
                open=129,
                close=130,
                high=130,
                low=129,
            ),
        ]

    def test_not_enough_candlesticks(self):
        opportunity = self.pattern_recognizer.is_bull_flag(
            self.candlesticks[0:2]
        )
        self.assertIsNone(opportunity)

        opportunity = self.pattern_recognizer.is_bull_flag(self.candlesticks)
        self.assertIsNotNone(opportunity)

    def test_is_extremely_bullish(self):
        opportunity = self.pattern_recognizer.is_bull_flag(self.candlesticks)
        self.assertFalse(opportunity.starts_extremely_bullish)

        # Change close price to make it extremely bullish
        self.candlesticks[0].close = 101

        opportunity = self.pattern_recognizer.is_bull_flag(self.candlesticks)
        self.assertTrue(opportunity.starts_extremely_bullish)

    def test_consolidation_period(self):
        opportunity = self.pattern_recognizer.is_bull_flag(self.candlesticks)
        self.assertEqual(2, opportunity.consolidation_period_length)
        self.assertEqual(0.1, opportunity.consolidation_period_max_ratio)

        # Change OHCL prices to make it looks like consolidation period
        self.candlesticks[3].low = 100
        self.candlesticks[3].close = 159

        opportunity = self.pattern_recognizer.is_bull_flag(self.candlesticks)
        self.assertEqual(2, opportunity.consolidation_period_length)
        self.assertEqual(3.0, opportunity.consolidation_period_max_ratio)

    def test_score(self):
        # Change close price to make it extremely bullish
        self.candlesticks[0].close = 101

        opportunity = self.pattern_recognizer.is_bull_flag(self.candlesticks)
        self.assertEqual(1.0, opportunity.score)
        self.assertEqual(2, opportunity.risk_reward_ratio)

    def test_if_bearish_during_consolidation(self):
        # Change close price to make it extremely bullish
        self.candlesticks[0].close = 101

        # Change open/close price to make it looks like bearish
        self.candlesticks[2].open = 110
        self.candlesticks[2].close = 109
        self.candlesticks[3].open = 109
        self.candlesticks[3].close = 108

        assert self.candlesticks[2].is_bearish()
        assert self.candlesticks[3].is_bearish()

        opportunity = self.pattern_recognizer.is_bull_flag(self.candlesticks)
        self.assertEqual(0.0, opportunity.score)

    def test_if_bullish_during_consolidation(self):
        # Change close price to make it extremely bullish
        self.candlesticks[0].close = 101

        # Change open/close to make it looks like bullish
        self.candlesticks[2].open = 109
        self.candlesticks[2].close = 110
        self.candlesticks[3].open = 129
        self.candlesticks[3].close = 130

        assert self.candlesticks[2].is_bullish()
        assert self.candlesticks[3].is_bullish()

        opportunity = self.pattern_recognizer.is_bull_flag(self.candlesticks)
        self.assertEqual(1.0, opportunity.score)

    def test_if_consolidation_period_has_support_price(self):
        # Change close price to make it extremely bullish
        self.candlesticks[0].close = 101

        opportunity = self.pattern_recognizer.is_bull_flag(self.candlesticks)
        self.assertEqual(109, opportunity.stop_loss_from_support)
