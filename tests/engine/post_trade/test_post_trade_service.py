import unittest
import uuid
from dataclasses import FrozenInstanceError
from datetime import datetime

import pytz

from jolteon.engine.core.side import MarketSide
from jolteon.engine.execution.unique_trade_id import unique_trade_id
from jolteon.engine.market_data.core.book_snapshot import BookSnapshot
from jolteon.engine.market_data.core.trade import Trade
from jolteon.engine.post_trade.decorated_order_fill import DecoratedOrderFill
from jolteon.engine.post_trade.post_trade_service import PostTradeService
from jolteon.engine.strategy.market_making.fair_value.fair_price_model import (
    FairPrice,
    IFairPriceModel,
)


class _FairPriceModel(IFairPriceModel):
    def _calculate(self, context: BookSnapshot) -> FairPrice:
        return FairPrice(bid=99.0, ask=101.0)


class TestPostTradeService(unittest.TestCase):
    def setUp(self):
        self.post_trade_service = PostTradeService()
        self.records = list[DecoratedOrderFill]()
        self.post_trade_service.decorated_order_fill_event.connect(
            self._on_decorated_order_fill
        )

    def tearDown(self):
        self.post_trade_service.decorated_order_fill_event.disconnect(
            self._on_decorated_order_fill
        )

    def _on_decorated_order_fill(
        self, _, decorated_order_fill: DecoratedOrderFill
    ):
        self.records.append(decorated_order_fill)

    @staticmethod
    def create_fill(
        exchange_trade_id: int,
        side: MarketSide,
        price: float,
        quantity: float,
        symbol: str = "BTC/USD",
        fee: float = 0.1,
    ):
        return Trade(
            exchange_trade_id=exchange_trade_id,
            client_order_id=str(exchange_trade_id),
            symbol=symbol,
            maker_order_id=str(uuid.uuid4()),
            taker_order_id=str(uuid.uuid4()),
            side=side,
            price=price,
            fee=fee,
            quantity=quantity,
            transaction_time=datetime.now(pytz.utc),
            exchange="Mock",
            exchange_order_id=str(exchange_trade_id),
            exchange_execution_id=str(exchange_trade_id),
            unique_trade_id=unique_trade_id(
                "Mock", str(exchange_trade_id), str(exchange_trade_id)
            ),
        )

    def test_records_every_fill_once_without_waiting_for_market_data(self):
        fill = self.create_fill(1, MarketSide.BUY, 100.0, 1.0)

        self.post_trade_service.on_fill("_", fill)

        self.assertEqual(1, len(self.records))
        record = self.records[0]
        self.assertEqual(
            unique_trade_id("Mock", "1", "1"), record.unique_trade_id
        )
        self.assertEqual("1", record.client_order_id)
        self.assertEqual("Mock", record.exchange)
        self.assertEqual("1", record.exchange_order_id)
        self.assertEqual("1", record.exchange_execution_id)
        self.assertEqual(fill.transaction_time, record.transaction_timestamp)
        self.assertEqual(MarketSide.BUY, record.side)
        self.assertEqual(100.0, record.fill_price)
        self.assertEqual(1.0, record.fill_qty)
        self.assertEqual(0.1, record.fee)
        self.assertEqual("MidPriceFairPriceModel", record.fair_price_model)

        # Markouts are deliberately absent from the durable fill fact.
        self.assertFalse(hasattr(record, "fair_price_at_fill"))
        self.assertFalse(hasattr(record, "fair_price_100ms"))

    def test_records_the_model_whose_series_analytics_must_join(self):
        service = PostTradeService(_FairPriceModel())
        records = []
        service.decorated_order_fill_event.connect(
            lambda _, decorated_order_fill: records.append(
                decorated_order_fill
            ),
            weak=False,
        )

        service.on_fill("_", self.create_fill(1, MarketSide.SELL, 100.0, 0.5))

        self.assertEqual("_FairPriceModel", records[0].fair_price_model)

    def test_recorded_fill_is_immutable(self):
        self.post_trade_service.on_fill(
            "_", self.create_fill(1, MarketSide.BUY, 100.0, 1.0)
        )

        with self.assertRaises(FrozenInstanceError):
            setattr(self.records[0], "fill_price", 101.0)


if __name__ == "__main__":
    unittest.main()
