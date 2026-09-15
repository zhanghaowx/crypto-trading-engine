import asyncio
import json
import logging
import time
from datetime import datetime, timezone
from enum import StrEnum

import websockets
from websockets.exceptions import ConnectionClosed

from jolteon.engine.core.health_monitor.health import (
    HealthMonitor,
    HealthState,
)
from jolteon.engine.core.health_monitor.heartbeat import (
    starts_heartbeating,
)
from jolteon.engine.core.parameter.parameter_service import parameter_service
from jolteon.engine.core.side import MarketSide
from jolteon.engine.market_data.binance_us.parameters import (
    BinanceUsFeedParameters,
)
from jolteon.engine.market_data.binance_us.rest_client import (
    BinanceUsPublicRestClient,
)
from jolteon.engine.market_data.core.bbo import BBO
from jolteon.engine.market_data.core.instrument import InstrumentSpec
from jolteon.engine.market_data.core.order_book import (
    BookUpdate,
    OrderBook,
    PriceLevel,
)
from jolteon.engine.market_data.core.trade import Trade
from jolteon.engine.market_data.feed import Channel, IMarketDataFeed


class PublicFeed(IMarketDataFeed):
    """Synchronized Binance.US trades, touch, L2 depth and trading rules."""

    STREAM_BASE = "wss://stream.binance.us:9443/stream?streams="
    # The venue closes every stream at 24 hours. Leave time to reconnect
    # cleanly before that forced disconnect.
    MAX_CONNECTION_SECONDS = 23 * 60 * 60 + 50 * 60

    class ErrorCode(StrEnum):
        CONNECTION_LOST = "Connection Lost"
        MALFORMED_RESPONSE = "Malformed Response from Binance.US"

    def __init__(
        self,
        rest_client: BinanceUsPublicRestClient | None = None,
        health_monitor: HealthMonitor | None = None,
    ):
        super().__init__(type(self).__name__, health_monitor=health_monitor)
        self._rest = rest_client or BinanceUsPublicRestClient()
        self._clock = time.monotonic
        self._symbol = ""
        self._wire_symbol = ""
        self._book_depth = 1000
        self._order_book = OrderBook("")
        self._last_update_id: int | None = None
        self._awaiting_bridge = False

    @property
    def channels(self) -> frozenset[Channel]:
        return frozenset(
            {
                Channel.MARKET_TRADE,
                Channel.TICKER,
                Channel.ORDER_BOOK,
                Channel.INSTRUMENT,
            }
        )

    @staticmethod
    def encode_symbol(symbol: str) -> str:
        return symbol.replace("/", "").replace("-", "").lower()

    @starts_heartbeating
    async def connect(
        self,
        symbol: str,
        max_retries: int | None = None,
        retry_interval_in_seconds: float | None = None,
    ) -> None:
        params = parameter_service().get(BinanceUsFeedParameters, symbol)
        max_retries = (
            params.max_retries if max_retries is None else max_retries
        )
        retry_interval_in_seconds = (
            params.retry_interval_in_seconds
            if retry_interval_in_seconds is None
            else retry_interval_in_seconds
        )
        retries = 0
        while retries <= max_retries:
            connected_at = self._clock()
            try:
                await self.connect_once(symbol)
            except asyncio.CancelledError:
                raise
            except Exception as error:
                self.add_issue(
                    HealthState.CRITICAL, self.ErrorCode.CONNECTION_LOST.value
                )
                logging.warning(
                    "Reconnecting to Binance.US after feed error: %s", error
                )
                await asyncio.sleep(retry_interval_in_seconds)

            if self._was_connection_healthy(connected_at, symbol):
                retries = 0
            else:
                retries += 1

    def _was_connection_healthy(
        self, connected_at: float, symbol: str
    ) -> bool:
        minimum = (
            parameter_service()
            .get(BinanceUsFeedParameters, symbol)
            .min_healthy_connection_seconds
        )
        return self._clock() - connected_at >= minimum

    async def connect_once(self, symbol: str) -> None:
        params = parameter_service().get(BinanceUsFeedParameters, symbol)
        self._symbol = symbol.replace("-", "/").upper()
        self._wire_symbol = self.encode_symbol(self._symbol)
        self._book_depth = params.book_depth
        self._order_book = OrderBook(self._symbol, depth=self._book_depth)
        self._last_update_id = None

        streams = "/".join(
            (
                f"{self._wire_symbol}@trade",
                f"{self._wire_symbol}@bookTicker",
                f"{self._wire_symbol}@depth@100ms",
            )
        )
        async with websockets.connect(f"{self.STREAM_BASE}{streams}") as ws:
            await self._publish_instrument()
            await self._load_snapshot()
            self.remove_issue(self.ErrorCode.CONNECTION_LOST.value)
            self.mark_healthy()
            async with asyncio.timeout(self.MAX_CONNECTION_SECONDS):
                while True:
                    try:
                        response = json.loads(await ws.recv())
                        await self._decode_message(response)
                    except StopAsyncIteration:
                        return
                    except ConnectionClosed:
                        raise
                    except Exception as error:
                        self.add_issue(
                            HealthState.CRITICAL,
                            self.ErrorCode.MALFORMED_RESPONSE.value,
                        )
                        logging.error(
                            "Cannot decode Binance.US message: %s",
                            error,
                            exc_info=True,
                        )
                        raise
                    else:
                        self.remove_issue(
                            self.ErrorCode.MALFORMED_RESPONSE.value
                        )

    async def _publish_instrument(self) -> None:
        payload = await asyncio.to_thread(
            self._rest.exchange_info, self._wire_symbol.upper()
        )
        symbols = payload.get("symbols", [])
        if len(symbols) != 1:
            raise ValueError(f"No Binance.US rules for {self._symbol}")
        instrument = self._decode_instrument(symbols[0])
        self.events.instrument.send(
            self.events.instrument, instrument=instrument
        )

    @staticmethod
    def _decode_instrument(payload: dict) -> InstrumentSpec:
        filters = {item["filterType"]: item for item in payload["filters"]}
        price = filters.get("PRICE_FILTER", {})
        lot = filters.get("LOT_SIZE", {})
        notional = filters.get("MIN_NOTIONAL", {})
        return InstrumentSpec(
            symbol=f"{payload['baseAsset']}/{payload['quoteAsset']}",
            base=payload["baseAsset"],
            quote=payload["quoteAsset"],
            price_precision=_precision(price.get("tickSize", "0")),
            qty_precision=_precision(lot.get("stepSize", "0")),
            price_increment=float(price.get("tickSize", 0)),
            qty_min=float(lot.get("minQty", 0)),
            cost_min=float(notional.get("minNotional", 0)),
        )

    async def _load_snapshot(self) -> None:
        payload = await asyncio.to_thread(
            self._rest.depth, self._wire_symbol.upper(), self._book_depth
        )
        self._order_book.apply(self._book_update(payload, is_snapshot=True))
        self._last_update_id = int(payload["lastUpdateId"])

    async def _request_order_book_snapshot(self, symbol: str) -> None:
        self._awaiting_bridge = True
        await self._load_snapshot()

    async def _decode_message(self, response: dict) -> None:
        payload = response.get("data", response)
        event = payload.get("e")
        if event == "serverShutdown":
            raise ConnectionError("Binance.US server is shutting down")
        if event == "trade":
            self._publish_trade(payload)
        elif event == "depthUpdate":
            await self._apply_depth(payload)
        elif {"b", "B", "a", "A"}.issubset(payload):
            self.events.ticker.send(
                self.events.ticker,
                bbo=BBO(
                    symbol=self._symbol,
                    bid_price=float(payload["b"]),
                    bid_quantity=float(payload["B"]),
                    ask_price=float(payload["a"]),
                    ask_quantity=float(payload["A"]),
                ),
            )
        else:
            logging.info("Ignoring Binance.US message: %s", response)

    def _publish_trade(self, payload: dict) -> None:
        trade = Trade(
            trade_id=int(payload["t"]),
            client_order_id="",
            symbol=self._symbol,
            maker_order_id="",
            taker_order_id="",
            side=MarketSide.SELL if payload["m"] else MarketSide.BUY,
            price=float(payload["p"]),
            fee=0.0,
            quantity=float(payload["q"]),
            transaction_time=datetime.fromtimestamp(
                payload["T"] / 1000, tz=timezone.utc
            ),
        )
        self.events.market_trade.send(
            self.events.market_trade, market_trade=trade
        )

    async def _apply_depth(self, payload: dict) -> None:
        assert self._last_update_id is not None, "Snapshot must load first"
        first, last = int(payload["U"]), int(payload["u"])
        if last <= self._last_update_id:
            return
        if first > self._last_update_id + 1:
            await self.resync_order_book(self._order_book)
            return
        self._order_book.apply(self._book_update(payload, is_snapshot=False))
        self._last_update_id = last
        if self._awaiting_bridge:
            self._awaiting_bridge = False
            self.on_order_book_synced()
        self.events.order_book.send(
            self.events.order_book, order_book=self._order_book
        )

    def _book_update(self, payload: dict, is_snapshot: bool) -> BookUpdate:
        bids = payload.get("bids", payload.get("b", []))
        asks = payload.get("asks", payload.get("a", []))
        timestamp = payload.get("E")
        return BookUpdate(
            symbol=self._symbol,
            bids=[PriceLevel(float(p), float(q)) for p, q in bids],
            asks=[PriceLevel(float(p), float(q)) for p, q in asks],
            is_snapshot=is_snapshot,
            exchange_time=(
                datetime.fromtimestamp(timestamp / 1000, tz=timezone.utc)
                if timestamp is not None
                else datetime.now(tz=timezone.utc)
            ),
        )


def _precision(decimal: str) -> int:
    return len(decimal.rstrip("0").partition(".")[2])
