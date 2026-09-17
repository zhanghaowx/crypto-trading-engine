import uuid
from dataclasses import dataclass
from typing import Union

from jolteon.engine.core.event.signal import signal, subscribe
from jolteon.engine.core.event.signal_subscriber import SignalSubscriber
from jolteon.engine.core.fee_schedule import FeeSchedule
from jolteon.engine.core.health_monitor.health import HealthMonitor
from jolteon.engine.core.health_monitor.heartbeat import Heartbeater
from jolteon.engine.core.id_generator import id_generator
from jolteon.engine.core.parameter.parameter_service import parameter_service
from jolteon.engine.core.side import MarketSide
from jolteon.engine.core.time.time_manager import time_manager
from jolteon.engine.execution.queue_position import QueuePosition
from jolteon.engine.execution.unique_trade_id import unique_trade_id
from jolteon.engine.market_data.core.bbo import BBO
from jolteon.engine.market_data.core.order import CancelOrder, Order, OrderType
from jolteon.engine.market_data.core.order_book import OrderBook
from jolteon.engine.market_data.core.trade import Trade
from jolteon.engine.market_data.data_source import IDataSource

_EXCHANGE = "Mock"


@dataclass
class _RestingOrder:
    order: Order
    price: float
    remaining_quantity: float
    queue_position: QueuePosition


class MockExecutionService(Heartbeater, SignalSubscriber):
    def __init__(
        self,
        fee_schedule: type[FeeSchedule],
        health_monitor: HealthMonitor | None = None,
    ):
        """
        Creates a mock execution service to act as the exchange.

        Market orders are filled immediately based on the most recent
        market trade at the exchange. Please be aware that the order book
        won't change after a trade. As a result, you might never able to
        clear a whole price level using market orders. Keep this
        limitation in mind when testing your strategy.

        Limit orders rest in a small simulated book and are only filled
        as real market trades print through their price level. Queue position
        is initialized from displayed L2 quantity at the exact order price.
        L2 does not reveal rank within a level, so this remains an estimate.
        """
        super().__init__(type(self).__name__, health_monitor=health_monitor)
        self._fee_schedule = fee_schedule
        self.order_history = dict[str, Order]()
        self.order_fill_event = signal("order_fill")
        self._health_monitor = health_monitor
        self._latest_bbo: dict[str, BBO] = {}
        self._latest_order_book: dict[str, OrderBook] = {}
        self._resting_orders: dict[str, _RestingOrder] = {}

    @subscribe("order")
    def on_order(self, sender: object, order: Order):
        """
        Place an order in the market. Signals will be sent to
        `order_fill_event` if there will be a trade or several trades.

        Args:
            sender: Name of the sender of the order request
            order: Details about the order including symbol, price and quantity

        Returns:
            None

        """
        if self._health_monitor and not self._health_monitor.can_trade:
            return
        # Record every order in history
        self.order_history[order.client_order_id] = order

        if order.order_type == OrderType.LIMIT_ORDER:
            self._rest_order(order)
            return

        # Get a random market trader near the fake time and do a match
        # close to the market in history
        price = self._get_closest_market_trade_price(order)
        self._generate_order_fill(
            order=order,
            filled_price=price,
            maker=False,
        )

    @subscribe("cancel_order")
    def on_cancel_order(self, sender: object, cancel_order: CancelOrder):
        self._resting_orders.pop(cancel_order.client_order_id, None)

    @subscribe("ticker_feed")
    def on_bbo(self, sender: object, bbo: BBO):
        self._latest_bbo[bbo.symbol] = bbo

    @subscribe("order_book_feed")
    def on_order_book(self, sender: object, order_book: OrderBook):
        self._latest_order_book[order_book.symbol] = order_book

    @subscribe("market_trade_feed")
    def on_market_trade(self, sender: object, market_trade: Trade):
        for client_order_id in list(self._resting_orders.keys()):
            resting = self._resting_orders.get(client_order_id)
            if resting is None or resting.order.symbol != market_trade.symbol:
                continue
            self._try_fill_resting_order(resting, market_trade)

    def _rest_order(self, order: Order):
        assert order.price is not None, "Limit orders must have a price"
        price = order.price

        queue_position = QueuePosition.best_guess(
            order,
            self._latest_order_book.get(order.symbol),
            self._latest_bbo.get(order.symbol),
        )

        self._resting_orders[order.client_order_id] = _RestingOrder(
            order=order,
            price=price,
            remaining_quantity=order.quantity,
            queue_position=queue_position,
        )

    def _try_fill_resting_order(
        self, resting: _RestingOrder, market_trade: Trade
    ):
        order = resting.order
        crosses = (
            order.side == MarketSide.BUY
            and market_trade.side == MarketSide.SELL
            and market_trade.price <= resting.price
        ) or (
            order.side == MarketSide.SELL
            and market_trade.side == MarketSide.BUY
            and market_trade.price >= resting.price
        )
        if not crosses:
            return

        if market_trade.price != resting.price:
            # Price already traded through our level: the real book must
            # have cleared it, but the print cannot prove more size traded
            # than it carries.
            filled_quantity = min(
                resting.remaining_quantity, market_trade.quantity
            )
        else:
            available = market_trade.quantity
            available = resting.queue_position.consume(available)
            filled_quantity = min(resting.remaining_quantity, available)

        if filled_quantity <= 0:
            return

        resting.remaining_quantity -= filled_quantity
        self._generate_order_fill(
            order=order,
            filled_price=resting.price,
            maker=True,
            quantity=filled_quantity,
        )

        if resting.remaining_quantity <= 1e-12:
            self._resting_orders.pop(order.client_order_id, None)

    # noinspection PyArgumentList
    @staticmethod
    def _get_closest_market_trade_price(order: Order) -> float:
        cached_trades = IDataSource.TRADE_CACHE.values()

        # First search in the cache
        for trades in cached_trades:
            for trade in trades:
                time_difference = (
                    trade.transaction_time - order.creation_time
                ).total_seconds()
                if 0 <= time_difference <= 60:
                    return trade.price

        return 0.0

    def _generate_order_fill(
        self,
        order: Order,
        filled_price: float,
        maker: bool,
        quantity: Union[float, None] = None,
    ):
        filled_quantity = order.quantity if quantity is None else quantity
        fees = parameter_service().get(self._fee_schedule, order.symbol)
        fee = fees.maker_fee if maker else fees.taker_fee
        exchange_trade_id = id_generator().next()
        trade = Trade(
            exchange_trade_id=exchange_trade_id,
            client_order_id=order.client_order_id,
            symbol=order.symbol,
            maker_order_id=str(uuid.uuid4()),
            taker_order_id=str(uuid.uuid4()),
            side=order.side,
            price=filled_price,
            fee=fee(filled_price, filled_quantity),
            quantity=filled_quantity,
            transaction_time=time_manager().now(),
            exchange=_EXCHANGE,
            exchange_order_id=order.client_order_id,
            exchange_execution_id=str(exchange_trade_id),
            unique_trade_id=unique_trade_id(
                _EXCHANGE, order.client_order_id, str(exchange_trade_id)
            ),
        )

        self.order_fill_event.send(
            self.order_fill_event,
            trade=trade,
        )
