import logging
import uuid
from dataclasses import dataclass
from datetime import datetime
from typing import Union

import pytz
import requests

from jolteon.engine.core.event.signal import signal, subscribe
from jolteon.engine.core.event.signal_subscriber import SignalSubscriber
from jolteon.engine.core.fee_schedule import KRAKEN
from jolteon.engine.core.health_monitor.heartbeat import Heartbeater
from jolteon.engine.core.id_generator import id_generator
from jolteon.engine.core.side import MarketSide
from jolteon.engine.core.time.time_manager import time_manager
from jolteon.engine.market_data.core.bbo import BBO
from jolteon.engine.market_data.core.order import CancelOrder, Order, OrderType
from jolteon.engine.market_data.core.trade import Trade
from jolteon.engine.market_data.data_source import IDataSource


@dataclass
class _RestingOrder:
    order: Order
    price: float
    remaining_quantity: float
    # Displayed quantity assumed to be ahead of us in the queue at our
    # price level. Decremented as opposing trades print at that level;
    # once it runs out, further matching volume fills this order.
    ahead_quantity: float


class MockExecutionService(Heartbeater, SignalSubscriber):
    def __init__(self):
        """
        Creates a mock execution service to act as the exchange.

        Market orders are filled immediately based on the most recent
        market trade at the exchange. Please be aware that the order book
        won't change after a trade. As a result, you might never able to
        clear a whole price level using market orders. Keep this
        limitation in mind when testing your strategy.

        Limit orders rest in a small simulated book and are only filled
        as real market trades print through their price level. Since only
        top-of-book (BBO) data is available (no real depth), the queue
        position of a resting order is approximated from the displayed
        quantity at the touch when the order was placed - it is not a
        precise reconstruction of Kraken's real matching engine.
        """
        super().__init__(type(self).__name__, interval_in_seconds=10)
        self.order_history = dict[str, Order]()
        self.order_fill_event = signal("order_fill")

        self._latest_bbo: dict[str, BBO] = {}
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

        bbo = self._latest_bbo.get(order.symbol)
        ahead_quantity = 0.0
        if bbo is not None:
            if order.side == MarketSide.BUY and price == bbo.bid_price:
                ahead_quantity = bbo.bid_quantity
            elif order.side == MarketSide.SELL and price == bbo.ask_price:
                ahead_quantity = bbo.ask_quantity

        self._resting_orders[order.client_order_id] = _RestingOrder(
            order=order,
            price=price,
            remaining_quantity=order.quantity,
            ahead_quantity=ahead_quantity,
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
            # have cleared it, so treat the whole remainder as filled.
            filled_quantity = resting.remaining_quantity
        else:
            available = market_trade.quantity
            if resting.ahead_quantity > 0:
                consumed = min(resting.ahead_quantity, available)
                resting.ahead_quantity -= consumed
                available -= consumed
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

        logging.warning(
            f"Fail to generate a trade from "
            f"{sum([len(trade_list) for trade_list in cached_trades])} "
            f"cached trades"
        )

        # Second search using Kraken's API
        response = requests.get(
            f"https://api.kraken.com/0/public/Trades?"
            f"pair={order.symbol}&"
            f"since={int(order.creation_time.timestamp())}&"
            f"limit=10"
        )
        assert response.status_code == 200, response

        json_resp = response.json()
        assert json_resp["error"] == [], json_resp
        assert json_resp["result"] is not None, json_resp

        json_trades = json_resp["result"][order.symbol]
        for json_trade in json_trades:
            transaction_time = datetime.fromtimestamp(
                json_trade[2], tz=pytz.utc
            )
            if transaction_time >= order.creation_time:
                return float(json_trade[0])

        return 0.0

    def _generate_order_fill(
        self,
        order: Order,
        filled_price: float,
        maker: bool,
        quantity: Union[float, None] = None,
    ):
        filled_quantity = order.quantity if quantity is None else quantity
        fee = KRAKEN.maker_fee if maker else KRAKEN.taker_fee
        trade = Trade(
            trade_id=id_generator().next(),
            client_order_id=order.client_order_id,
            symbol=order.symbol,
            maker_order_id=str(uuid.uuid4()),
            taker_order_id=str(uuid.uuid4()),
            side=order.side,
            price=filled_price,
            fee=fee(filled_price, filled_quantity),
            quantity=filled_quantity,
            transaction_time=time_manager().now(),
        )

        self.order_fill_event.send(
            self.order_fill_event,
            trade=trade,
        )
