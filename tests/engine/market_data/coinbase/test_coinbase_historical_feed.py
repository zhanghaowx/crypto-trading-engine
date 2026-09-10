import os
import unittest
from datetime import timedelta
from unittest.mock import MagicMock, Mock, patch

from jolteon.engine.core.time.time_manager import time_manager
from jolteon.engine.market_data.coinbase.data_source import (
    CoinbaseHistoricalDataSource,
)
from jolteon.engine.market_data.core.trade import Trade
from jolteon.engine.market_data.data_source import IDataSource
from jolteon.engine.market_data.historical_feed import (
    HistoricalFeed,
)


class TestHistoricalFeed(unittest.IsolatedAsyncioTestCase):
    @patch.dict(os.environ, {"COINBASE_API_KEY": "api_key"})
    @patch.dict(os.environ, {"COINBASE_API_SECRET": "api_secret"})
    async def asyncSetUp(self):
        self.data_source = CoinbaseHistoricalDataSource()
        self.data_source._client = Mock()
        self.data_source._client.get_market_trades.return_value = {
            "trades": [
                {
                    "trade_id": "34b080bf-fcfd-445a-832b-46b5ddc65601",
                    "product_id": "BTC-USD",
                    "price": "140.91",
                    "size": "4",
                    "time": time_manager().now().isoformat(),
                    "side": "BUY",
                    "bid": "291.13",
                    "ask": "292.40",
                }
            ],
            "best_bid": "291.13",
            "best_ask": "292.40",
        }
        self.historical_feed = HistoricalFeed(data_source=self.data_source)
        self.historical_feed.events.market_trade.connect(self.on_market_trade)
        self.market_trades = list[Trade]()

    def on_market_trade(self, _, market_trade):
        self.market_trades.append(market_trade)

    async def test_connect_with_valid_symbol(self):
        symbol = "BTC-USD"
        await self.historical_feed.connect(
            symbol,
            time_manager().now() - timedelta(seconds=1),
            time_manager().now() + timedelta(seconds=1),
        )

        # Validate raised market trade event
        self.assertEqual(1, len(self.market_trades))
        self.assertEqual(140.91, self.market_trades[0].price)
        self.assertEqual(4.0, self.market_trades[0].quantity)

    async def test_connect_with_valid_symbol_and_cache(self):
        IDataSource.TRADE_CACHE.clear()

        symbol = "BTC-USD"
        now = time_manager().now()
        await self.historical_feed.connect(
            symbol, now - timedelta(minutes=1), now
        )
        await self.historical_feed.connect(
            symbol, now - timedelta(minutes=1), now
        )

        self.assertEqual(1, len(IDataSource.TRADE_CACHE))
        self.assertEqual(2, len(self.market_trades))
        self.assertEqual(self.market_trades[0], self.market_trades[1])

        self.data_source._client.get_market_trades.assert_called_once()

    async def test_connect_with_empty_trades(self):
        # Setup
        self.data_source._client.get_market_trades.return_value = {
            "trades": [],
        }
        time_manager().use_fake_time = MagicMock()
        IDataSource.TRADE_CACHE.clear()

        # Connect
        symbol = "BTC-USD"
        now = time_manager().now()
        await self.historical_feed.connect(
            symbol, now - timedelta(minutes=1), now
        )

        self.assertEqual(1, len(IDataSource.TRADE_CACHE))
        self.assertEqual(0, len(self.market_trades))

        self.data_source._client.get_market_trades.assert_called_once()

        # Verify mock time is set properly
        time_manager().use_fake_time.assert_called_once()
