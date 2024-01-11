import os
import uuid
from copy import copy
from datetime import datetime
from random import randint
from typing import Union

import pytz
from blinker import signal
from coinbase.rest import RESTClient

from crypto_trading_engine.core.side import MarketSide
from crypto_trading_engine.market_data.core.order import Order, OrderType
from crypto_trading_engine.market_data.core.order_book import OrderBook
from crypto_trading_engine.market_data.core.trade import Trade


class MockExecutionService:
    def __init__(
        self,
        api_key: Union[str, None] = os.getenv("COINBASE_API_KEY"),
        api_secret: Union[str, None] = os.getenv("COINBASE_API_SECRET"),
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
        self._client = RESTClient(api_key=api_key, api_secret=api_secret)
        self.order_history = dict[str, Order]()
        self.order_fill_event = signal("order_fill")
        pass

    def buy(self, symbol: str, price: Union[float, None], quantity: float):
        """
        Place a buy order in the market. Signals will be sent to
        `order_fill_event` if there will be a trade or several trades.

        Args:
            symbol: Symbol of the product to buy
            price: Price of the product to buy
            quantity: Quantity of the product to buy

        Returns:
            None
        """
        buy_order_id = str(uuid.uuid4())
        buy_order = Order(
            client_order_id=buy_order_id,
            order_type=OrderType.MARKET_ORDER,
            symbol=symbol,
            price=price,
            quantity=quantity,
            side=MarketSide.BUY,
        )
        self.order_history[buy_order_id] = buy_order
        self._perform_order_match(buy_order, self._build_order_book(symbol))

    def sell(self, symbol: str, price: Union[float, None], quantity: float):
        """
        Place a sell order in the market. Signals will be sent to
        `order_fill_event` if there will be a trade or several trades.

        Args:
            symbol: Symbol of the product to sell
            price: Price of the product to sell
            quantity: Quantity of the product to sell

        Returns:
            None

        """
        sell_order_id = str(uuid.uuid4())
        sell_order = Order(
            client_order_id=sell_order_id,
            order_type=OrderType.MARKET_ORDER,
            symbol=symbol,
            price=price,
            quantity=quantity,
            side=MarketSide.SELL,
        )
        self.order_history[sell_order_id] = sell_order
        self._perform_order_match(sell_order, self._build_order_book(symbol))

    # noinspection PyArgumentList
    # Definition of RESTClient.get_product_book confuses linter
    def _build_order_book(self, symbol: str):
        json_response = self._client.get_product_book(product_id=symbol)
        assert json_response["pricebook"]["product_id"] == symbol

        # Recreate the order book from JSON response
        order_book = OrderBook()
        for bid in json_response["pricebook"]["bids"]:
            order_book.add_bid(price=bid["price"], quantity=bid["size"])

        for ask in json_response["pricebook"]["asks"]:
            order_book.add_ask(price=ask["price"], quantity=ask["size"])

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
                    trade = Trade(
                        trade_id=randint(1, 1000),
                        sequence_number=randint(1, 1000),
                        symbol=buy_order.symbol,
                        maker_order_id=str(uuid.uuid4()),
                        taker_order_id=str(uuid.uuid4()),
                        side=buy_order.side,
                        price=sell_price,
                        quantity=filled_quantity,
                        transaction_time=datetime.now(pytz.utc),
                    )

                    self.order_fill_event.send(
                        self.order_fill_event, trade=trade
                    )

                    buy_order.quantity -= filled_quantity
                    assert buy_order.quantity >= 0

        if order.side == MarketSide.SELL:
            sell_order = copy(order)
            for buy_price, buy_quantity in sorted(
                order_book.bids.levels.items(), reverse=True
            ):
                if sell_order.quantity <= 0:
                    break
                if not sell_order.price or sell_order.price <= buy_price:
                    filled_quantity = min(sell_order.quantity, buy_quantity)
                    trade = Trade(
                        trade_id=randint(1, 1000),
                        sequence_number=randint(1, 1000),
                        symbol=sell_order.symbol,
                        maker_order_id=str(uuid.uuid4()),
                        taker_order_id=str(uuid.uuid4()),
                        side=sell_order.side,
                        price=buy_price,
                        quantity=filled_quantity,
                        transaction_time=datetime.now(pytz.utc),
                    )

                    self.order_fill_event.send(
                        self.order_fill_event,
                        trade=trade,
                    )

                    sell_order.quantity -= filled_quantity
                    assert sell_order.quantity >= 0
