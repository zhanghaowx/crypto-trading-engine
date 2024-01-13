import logging
import os
import uuid
from copy import copy
from datetime import datetime, timedelta
from random import randint
from typing import Union

from blinker import signal
from coinbase.rest import RESTClient

from crypto_trading_engine.core.side import MarketSide
from crypto_trading_engine.core.time.time_manager import create_time_manager
from crypto_trading_engine.market_data.core.order import Order
from crypto_trading_engine.market_data.core.order_book import OrderBook
from crypto_trading_engine.market_data.core.trade import Trade


class MockExecutionService:
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
        self._client = RESTClient(
            api_key=(api_key if api_key else os.getenv("COINBASE_API_KEY")),
            api_secret=(
                api_secret if api_secret else os.getenv("COINBASE_API_SECRET")
            ),
        )
        self.order_history = dict[str, Order]()
        self.order_fill_event = signal("order_fill")
        self.time_manager = create_time_manager()

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

        if self.time_manager.is_using_fake_time():
            # Get a random market trader near the fake time and do a match
            # close to the market in history
            trade = self._get_any_market_trade(order.symbol)
            self._generate_order_fill(
                symbol=order.symbol,
                side=order.side,
                price=trade.price,
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
                        symbol=sell_order.symbol,
                        side=sell_order.side,
                        price=buy_price,
                        quantity=filled_quantity,
                    )

                    sell_order.quantity -= filled_quantity
                    assert sell_order.quantity >= 0

    # noinspection PyArgumentList
    def _get_any_market_trade(self, symbol):
        now = self.time_manager.get_current_time()
        json_response = self._client.get_market_trades(
            product_id=symbol,
            start=int((now - timedelta(seconds=5)).timestamp()),
            end=int((now + timedelta(seconds=5)).timestamp()),
            limit=1,
        )

        assert len(json_response["trades"]) > 0
        first_trade_json = json_response["trades"][0]

        return Trade(
            trade_id=int(first_trade_json["trade_id"]),
            sequence_number=0,
            symbol=first_trade_json["product_id"],
            maker_order_id="",
            taker_order_id="",
            side=MarketSide(first_trade_json["side"].upper()),
            price=float(first_trade_json["price"]),
            quantity=float(first_trade_json["size"]),
            transaction_time=datetime.fromisoformat(first_trade_json["time"]),
        )

    def _generate_order_fill(
        self, symbol: str, side: MarketSide, price: float, quantity: float
    ):
        trade = Trade(
            trade_id=randint(1, 1000),
            sequence_number=randint(1, 1000),
            symbol=symbol,
            maker_order_id=str(uuid.uuid4()),
            taker_order_id=str(uuid.uuid4()),
            side=side,
            price=price,
            quantity=quantity,
            transaction_time=self.time_manager.get_current_time(),
        )

        self.order_fill_event.send(
            self.order_fill_event,
            trade=trade,
        )
