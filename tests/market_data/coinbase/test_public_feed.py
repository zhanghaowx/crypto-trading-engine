import unittest

from crypto_trading_engine.market_data.coinbase.public_feed import (
    CoinbasePublicFeed,
    CoinbaseEnvironment,
)


class TestCandlestick(unittest.IsolatedAsyncioTestCase):
    async def test_public_feed(self):
        candle = CoinbasePublicFeed(CoinbaseEnvironment.SANDBOX)
