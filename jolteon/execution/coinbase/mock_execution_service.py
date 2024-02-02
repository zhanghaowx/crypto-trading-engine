import logging
import os
import uuid
from copy import copy
from datetime import timedelta
from typing import Union

import numpy as np
from coinbase.rest import RESTClient

from jolteon.core.event.signal import signal
from jolteon.core.health_monitor.heartbeat import Heartbeater
from jolteon.core.id_generator import id_generator
from jolteon.core.side import MarketSide
from jolteon.core.time.time_manager import time_manager
from jolteon.market_data.core.order import Order
from jolteon.market_data.core.order_book import OrderBook
from jolteon.market_data.core.trade import Trade


class MockExecutionService(Heartbeater):
    def __init__(
        self,
        api_key: Union[str, None] = None,
        api_secret: Union[str, None] = None,
    ):
        """
        Creates a mock execution service to act as the exchange. It will
        respond to requests such as buy and sell, and based on the actual
        order book at the exchange, it will generate fake fill notices.

        In order to simulate a real market, this class needs to use Coinbase
        Advanced Trade API. API key and secret should be preloaded into
        the environment.

        Please be aware that the order book won't change after a trade. It
        will always stay in sync with the production order book. As a result,
        you might see unexpected results such as you can never trade a whole
        price level using market orders. Keep this limitation in mind when
        testing your strategy.
        """
        super().__init__(type(self).__name__, interval_in_seconds=10)
        self._client = RESTClient(
            api_key=(api_key if api_key else os.getenv("COINBASE_API_KEY")),
            api_secret=(
                api_secret if api_secret else os.getenv("COINBASE_API_SECRET")
            ),
        )
        self.order_history = dict[str, Order]()
        self.order_fill_event = signal("order_fill")

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

        if time_manager().is_using_fake_time():
            # Get a random market trader near the fake time and do a match
            # close to the market in history
            price = self._get_any_market_trade_price(order.symbol)
            self._generate_order_fill(
                client_order_id=order.client_order_id,
                symbol=order.symbol,
                side=order.side,
                price=price,
                quantity=order.quantity,
            )
        else:
            # Get current order book and do a match close to the current market
            order_book = self._build_order_book(order.symbol)

            bid_levels = order_book.bids.levels
            ask_levels = order_book.asks.levels
            logging.info(
                f"Built order book for {order.symbol}: "
                f"Depth=("
                f"BidDepth={len(bid_levels)}, "
                f"AskDepth={len(ask_levels)}"
                f"),"
                f"BBO=("
                f"Bid={next(iter(bid_levels.keys()), None)}, "
                f"Ask={next(iter(ask_levels.keys()), None)}"
                f")"
            )
            self._perform_order_match(order, order_book)

    # noinspection PyArgumentList
    def _build_order_book(self, symbol: str):
        json_response = self._client.get_product_book(
            product_id=symbol, limit=100
        )
        assert json_response["pricebook"]["product_id"] == symbol

        # Recreate the order book from JSON response
        order_book = OrderBook()
        for bid in json_response["pricebook"]["bids"]:
            order_book.add_bid(
                price=float(bid["price"]), quantity=float(bid["size"])
            )

        for ask in json_response["pricebook"]["asks"]:
            order_book.add_ask(
                price=float(ask["price"]), quantity=float(ask["size"])
            )

        return order_book

    def _perform_order_match(self, order: Order, order_book: OrderBook):
        if order.side == MarketSide.BUY:
            buy_order = copy(order)
            for sell_price, sell_quantity in sorted(
                order_book.asks.levels.items()
            ):
                if buy_order.quantity <= 0:
                    break
                if not buy_order.price or buy_order.price >= sell_price:
                    filled_quantity = min(buy_order.quantity, sell_quantity)
                    self._generate_order_fill(
                        client_order_id=buy_order.client_order_id,
                        symbol=buy_order.symbol,
                        side=buy_order.side,
                        price=sell_price,
                        quantity=filled_quantity,
                    )

                    buy_order.quantity -= filled_quantity
                    assert buy_order.quantity >= 0

        else:
            assert (
                order.side == MarketSide.SELL
            ), f"'{order.side}' is not a valid MarketSide"

            sell_order = copy(order)
            for buy_price, buy_quantity in sorted(
                order_book.bids.levels.items(), reverse=True
            ):
                if sell_order.quantity <= 0:
                    break
                if not sell_order.price or sell_order.price <= buy_price:
                    filled_quantity = min(sell_order.quantity, buy_quantity)
                    self._generate_order_fill(
                        client_order_id=sell_order.client_order_id,
                        symbol=sell_order.symbol,
                        side=sell_order.side,
                        price=buy_price,
                        quantity=filled_quantity,
                    )

                    sell_order.quantity -= filled_quantity
                    assert sell_order.quantity >= 0

    # noinspection PyArgumentList
    def _get_any_market_trade_price(self, symbol) -> float:
        now = time_manager().now()
        json_response = self._client.get_market_trades(
            product_id=symbol,
            start=int((now - timedelta(seconds=5)).timestamp()),
            end=int((now + timedelta(seconds=5)).timestamp()),
            limit=10,
        )

        assert len(json_response["trades"]) > 0

        for trade_json in json_response["trades"]:
            try:
                return float(trade_json["price"])
            except ValueError as e:
                logging.error(
                    f"Could not parse trade '{trade_json}': {e}", exc_info=True
                )
                continue  # Try next trade in the JSON response

        logging.error(
            f"No valid trades found for '{symbol}' at {now}", exc_info=True
        )
        return np.nan

    def _generate_order_fill(
        self,
        client_order_id: str,
        symbol: str,
        side: MarketSide,
        price: float,
        quantity: float,
    ):
        trade = Trade(
            trade_id=id_generator().next(),
            client_order_id=client_order_id,
            symbol=symbol,
            maker_order_id=str(uuid.uuid4()),
            taker_order_id=str(uuid.uuid4()),
            side=side,
            price=price,
            fee=0.0,
            quantity=quantity,
            transaction_time=time_manager().now(),
        )

        self.order_fill_event.send(
            self.order_fill_event,
            trade=trade,
        )
