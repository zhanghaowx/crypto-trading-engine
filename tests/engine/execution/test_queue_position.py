from datetime import datetime, timezone

from jolteon.engine.core.side import MarketSide
from jolteon.engine.execution.queue_position import (
    L2QueuePositionModel,
    QueuePosition,
)
from jolteon.engine.market_data.core.bbo import BBO
from jolteon.engine.market_data.core.order import Order, OrderType
from jolteon.engine.market_data.core.order_book import (
    BookUpdate,
    OrderBook,
    PriceLevel,
)


def order(side: MarketSide, price: float) -> Order:
    return Order(
        client_order_id="order",
        order_type=OrderType.LIMIT_ORDER,
        symbol="BTC/USD",
        side=side,
        price=price,
        quantity=1.0,
        creation_time=datetime(2024, 1, 1, tzinfo=timezone.utc),
    )


def test_queue_position_consumes_ahead_before_returning_available_volume():
    position = QueuePosition(2.0)

    assert position.consume(1.5) == 0.0
    assert position.ahead_quantity == 0.5
    assert position.consume(1.0) == 0.5
    assert position.ahead_quantity == 0.0


def test_l2_model_reads_the_exact_book_level():
    book = OrderBook("BTC/USD")
    book.apply(
        BookUpdate(
            symbol="BTC/USD",
            bids=[PriceLevel(100.0, 1.0), PriceLevel(99.0, 2.0)],
            asks=[PriceLevel(101.0, 3.0)],
            is_snapshot=True,
            exchange_time=datetime(2024, 1, 1, tzinfo=timezone.utc),
        )
    )

    position = L2QueuePositionModel().create(
        order(MarketSide.BUY, 99.0), book, None
    )

    assert position.ahead_quantity == 2.0


def test_l2_model_falls_back_to_matching_bbo_without_a_book():
    bbo = BBO("BTC/USD", 100.0, 2.0, 101.0, 3.0)
    model = L2QueuePositionModel()

    assert (
        model.create(order(MarketSide.BUY, 100.0), None, bbo).ahead_quantity
        == 2.0
    )
    assert (
        model.create(order(MarketSide.SELL, 101.0), None, bbo).ahead_quantity
        == 3.0
    )
    assert (
        model.create(order(MarketSide.BUY, 99.0), None, bbo).ahead_quantity
        == 0.0
    )
