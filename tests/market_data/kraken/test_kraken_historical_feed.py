import unittest
from datetime import datetime, timezone
from unittest.mock import patch, MagicMock

from jolteon.core.time.time_manager import time_manager
from jolteon.market_data.core.candlestick import Candlestick
from jolteon.market_data.core.trade import Trade
from jolteon.market_data.kraken.historical_feed import HistoricalFeed


class TestHistoricalFeed(unittest.IsolatedAsyncioTestCase):
    def on_market_trade(self, _: str, market_trade: Trade):
        self.market_trades.append(market_trade)

    def on_candlestick(self, _: str, candlestick: Candlestick):
        self.candlesticks.append(candlestick)

    async def asyncSetUp(self):
        self.market_trades = []
        self.candlesticks = []
        self.historical_feed = HistoricalFeed()
        self.historical_feed.events.matches.connect(self.on_market_trade)
        self.historical_feed.events.candlestick.connect(self.on_candlestick)

    async def asyncTearDown(self):
        time_manager().force_reset()

    async def test_connect_replays_trades_and_generates_candlesticks(self):
        self.assertEqual(len(self.market_trades), 0)
        self.assertEqual(len(self.candlesticks), 0)

        # Set up test parameters
        symbol = "BTC/USD"
        start_time = datetime(2023, 1, 1, 1, 1, 0, tzinfo=timezone.utc)
        end_time = datetime(2023, 1, 1, 1, 2, 0, tzinfo=timezone.utc)

        # Mock the requests.get method to return a custom JSON response
        mock_response = {
            "error": [],
            "result": {
                symbol: [
                    [50000.0, 1.0, start_time.timestamp(), "b", "m", "", 1],
                    [51000.0, 1.0, end_time.timestamp(), "s", "l", "", 2],
                    # Add more simulated trades as needed
                ],
                "last": end_time.timestamp(),  # Mock the last timestamp
            },
        }

        with patch("requests.get", new_callable=MagicMock) as mock_get:
            # Set the return value of the mock to the custom JSON response
            mock_get.return_value = MagicMock()
            mock_get.return_value.status_code = 200
            mock_get.return_value.json.return_value = mock_response

            # Connect and simulate the asynchronous event loop
            await self.historical_feed.connect(symbol, start_time, end_time)

        print(self.candlesticks)
        self.assertEqual(len(self.market_trades), 2)
        self.assertEqual(len(self.candlesticks), 2)
