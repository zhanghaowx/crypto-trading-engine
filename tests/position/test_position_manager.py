import unittest
import uuid
from datetime import datetime
from random import randint

import pytz

from jolteon.core.side import MarketSide
from jolteon.market_data.core.bbo import BBO
from jolteon.market_data.core.trade import Trade
from jolteon.position.position_manager import PositionManager, PositionUpdate


def randomInt(param, param1):
    pass


class TestPositionManager(unittest.IsolatedAsyncioTestCase):
    def create_trade(
        self,
        market_side: MarketSide,
        symbol: str,
        price: float,
        quantity: float,
    ):
        return Trade(
            trade_id=randint(1, 1000),
            client_order_id="",
            symbol=symbol,
            maker_order_id=str(uuid.uuid4()),
            taker_order_id=str(uuid.uuid4()),
            side=market_side,
            price=price,
            fee=1.0,
            quantity=quantity,
            transaction_time=datetime.now(pytz.utc),
        )

    async def test_buy(self):
        position_manager = PositionManager()

        def buy(symbol: str, price: float, quantity: float):
            position_manager.on_fill(
                "_", self.create_trade(MarketSide.BUY, symbol, price, quantity)
            )

        buy("BTC", 1.5, 2.0)
        self.assertEqual(1, len(position_manager.positions))
        self.assertEqual(2.0, position_manager.positions["BTC"].volume)
        self.assertEqual(3.0, position_manager.positions["BTC"].cash_value)

        buy("BTC", 2.0, 5.0)
        self.assertEqual(1, len(position_manager.positions))
        self.assertEqual(7.0, position_manager.positions["BTC"].volume)
        self.assertEqual(13.0, position_manager.positions["BTC"].cash_value)

        buy("ETH", 2.0, 5.0)
        self.assertEqual(2, len(position_manager.positions))
        self.assertEqual(7.0, position_manager.positions["BTC"].volume)
        self.assertEqual(13.0, position_manager.positions["BTC"].cash_value)
        self.assertEqual(5.0, position_manager.positions["ETH"].volume)
        self.assertEqual(10.0, position_manager.positions["ETH"].cash_value)

    async def test_sell(self):
        position_manager = PositionManager()

        def buy(symbol: str, price: float, quantity: float):
            position_manager.on_fill(
                "_", self.create_trade(MarketSide.BUY, symbol, price, quantity)
            )

        def sell(symbol: str, price: float, quantity: float):
            position_manager.on_fill(
                "_",
                self.create_trade(MarketSide.SELL, symbol, price, quantity),
            )

        buy("BTC", 1.5, 100.0)
        buy("ETH", 2.5, 1000.0)

        sell("ETH", 2.0, 5.0)
        self.assertEqual(2, len(position_manager.positions))
        self.assertEqual(100.0, position_manager.positions["BTC"].volume)
        self.assertEqual(150.0, position_manager.positions["BTC"].cash_value)
        self.assertEqual(995.0, position_manager.positions["ETH"].volume)
        self.assertEqual(2490.0, position_manager.positions["ETH"].cash_value)

        sell("ETH", 1.0, 10.0)
        self.assertEqual(2, len(position_manager.positions))
        self.assertEqual(100.0, position_manager.positions["BTC"].volume)
        self.assertEqual(150.0, position_manager.positions["BTC"].cash_value)
        self.assertEqual(985.0, position_manager.positions["ETH"].volume)
        self.assertEqual(2480.0, position_manager.positions["ETH"].cash_value)

        sell("BTC", 0.5, 20.0)
        self.assertEqual(2, len(position_manager.positions))
        self.assertEqual(80.0, position_manager.positions["BTC"].volume)
        self.assertEqual(140.0, position_manager.positions["BTC"].cash_value)
        self.assertEqual(985.0, position_manager.positions["ETH"].volume)
        self.assertEqual(2480.0, position_manager.positions["ETH"].cash_value)

        self.assertEqual(-2625.0, position_manager.pnl)

    def test_on_fill_invalid_side(self):
        trade = self.create_trade("SHORT_SELL", "BTC-USD", 100.0, 1.0)

        with self.assertRaises(AssertionError) as context:
            position_manager = PositionManager()
            position_manager.on_fill("_", trade)

        self.assertRaisesRegex(
            AssertionError,
            "^Trade has an invalid trade side",
        )

    async def test_total_pnl_marks_open_position_to_market(self):
        position_manager = PositionManager()

        position_manager.on_fill(
            "_", self.create_trade(MarketSide.BUY, "BTC", 100.0, 1.0)
        )
        # Realized PnL reflects only the cash spent so far.
        self.assertEqual(-101.0, position_manager.pnl)
        # With no mark price yet, the open position marks to 0.
        self.assertEqual(-101.0, position_manager.total_pnl)

        position_manager.on_bbo(
            "_",
            BBO(
                symbol="BTC",
                bid_price=109.0,
                bid_quantity=1.0,
                ask_price=111.0,
                ask_quantity=1.0,
            ),
        )

        # Mark-to-market at the new mid (110) reveals the unrealized gain.
        self.assertEqual(-101.0, position_manager.pnl)
        self.assertEqual(9.0, position_manager.total_pnl)

    async def test_sell_without_an_existing_position_opens_a_short(self):
        """
        A sell can be the first fill seen for a symbol, with no buy before
        it, and must open a short rather than being rejected.
        """
        position_manager = PositionManager()

        position_manager.on_fill(
            "_", self.create_trade(MarketSide.SELL, "BTC", 100.0, 2.0)
        )

        self.assertEqual(1, len(position_manager.positions))
        self.assertEqual(-2.0, position_manager.positions["BTC"].volume)
        self.assertEqual(-200.0, position_manager.positions["BTC"].cash_value)
        # Cash in from the sale, less the fee
        self.assertEqual(199.0, position_manager.pnl)

    async def test_selling_more_than_held_runs_the_position_short(self):
        """
        A sell larger than the position held takes it through zero and
        leaves it short.
        """
        position_manager = PositionManager()

        position_manager.on_fill(
            "_", self.create_trade(MarketSide.BUY, "BTC", 100.0, 1.0)
        )
        position_manager.on_fill(
            "_", self.create_trade(MarketSide.SELL, "BTC", 110.0, 3.0)
        )

        self.assertEqual(-2.0, position_manager.positions["BTC"].volume)
        self.assertEqual(-230.0, position_manager.positions["BTC"].cash_value)
        # -100 - 1 (buy) + 330 - 1 (sell)
        self.assertEqual(228.0, position_manager.pnl)

    async def test_on_fill_emits_position_updated(self):
        position_manager = PositionManager()
        updates = list[PositionUpdate]()

        def on_position_updated(_, position_update: PositionUpdate):
            updates.append(position_update)

        position_manager.position_updated_event.connect(on_position_updated)

        position_manager.on_fill(
            "_", self.create_trade(MarketSide.BUY, "BTC", 100.0, 1.0)
        )
        position_manager.on_fill(
            "_", self.create_trade(MarketSide.SELL, "BTC", 100.0, 0.4)
        )

        self.assertEqual(
            [
                PositionUpdate(symbol="BTC", volume=1.0),
                PositionUpdate(symbol="BTC", volume=0.6),
            ],
            updates,
        )

    async def test_total_pnl_marks_a_short_position_to_market(self):
        """
        A short loses value as the price rises, so the mark-to-market has to
        carry the sign of the position rather than its size.
        """
        position_manager = PositionManager()

        position_manager.on_fill(
            "_", self.create_trade(MarketSide.SELL, "BTC", 100.0, 1.0)
        )
        self.assertEqual(99.0, position_manager.pnl)

        position_manager.on_bbo(
            "_",
            BBO(
                symbol="BTC",
                bid_price=109.0,
                bid_quantity=1.0,
                ask_price=111.0,
                ask_quantity=1.0,
            ),
        )

        # Sold at 100, now marked at 110: an 11.0 loss once the fee is in
        self.assertEqual(99.0, position_manager.pnl)
        self.assertEqual(-11.0, position_manager.total_pnl)
