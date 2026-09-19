import asyncio

from jolteon.engine.core.event.signal import signal, subscribe
from jolteon.engine.core.event.signal_subscriber import SignalSubscriber
from jolteon.engine.market_data.core.bbo import BBO
from jolteon.engine.market_data.core.book_snapshot import BookSnapshot
from jolteon.engine.market_data.core.trade import Trade
from jolteon.engine.post_trade.decorated_order_fill import DecoratedOrderFill
from jolteon.engine.strategy.market_making.fair_value.fair_price_model import (
    IFairPriceModel,
)
from jolteon.engine.strategy.market_making.fair_value.mid_price_model import (
    MidPriceFairPriceModel,
)

_MARKOUT_DELAYS: tuple[tuple[str, float], ...] = (
    ("fair_price_100ms", 0.1),
    ("fair_price_1s", 1.0),
    ("fair_price_5s", 5.0),
    ("fair_price_30s", 30.0),
)


class PostTradeService(SignalSubscriber):
    def __init__(self, fair_price_model: IFairPriceModel | None = None):
        self._fair_price_model = fair_price_model or MidPriceFairPriceModel()
        self.decorated_order_fill_event = signal("decorated_order_fill")

        self._latest_bbo = dict[str, BBO]()
        self._pending_fills = dict[str, DecoratedOrderFill]()

    @subscribe("bbo_feed")
    def on_bbo(self, _: str, bbo: BBO):
        self._latest_bbo[bbo.symbol] = bbo

    @subscribe("order_fill")
    def on_fill(self, _: str, trade: Trade):
        bbo = self._latest_bbo.get(trade.symbol)
        if bbo is None:
            return

        record = DecoratedOrderFill(
            unique_trade_id=trade.unique_trade_id,
            client_order_id=trade.client_order_id,
            exchange=trade.exchange,
            exchange_order_id=trade.exchange_order_id,
            exchange_execution_id=trade.exchange_execution_id,
            transaction_timestamp=trade.transaction_time,
            symbol=trade.symbol,
            side=trade.side,
            fill_price=trade.price,
            fill_qty=trade.quantity,
            fair_price_at_fill=self._fair_price(bbo),
            fee=trade.fee,
        )
        self._pending_fills[trade.unique_trade_id] = record
        self._send(record)

        loop = asyncio.get_running_loop()
        for field_name, delay in _MARKOUT_DELAYS:
            loop.call_later(
                delay,
                self._record_fair_price_after_fill,
                trade.unique_trade_id,
                field_name,
            )

    def _record_fair_price_after_fill(
        self, unique_trade_id: str, field_name: str
    ):
        record = self._pending_fills.get(unique_trade_id)
        if record is None:
            return

        bbo = self._latest_bbo.get(record.symbol)
        if bbo is not None:
            setattr(record, field_name, self._fair_price(bbo))
        self._send(record)

        if field_name == _MARKOUT_DELAYS[-1][0]:
            del self._pending_fills[unique_trade_id]

    def _fair_price(self, bbo: BBO) -> float:
        fair_price = self._fair_price_model.calculate(BookSnapshot(bbo=bbo))
        return (fair_price.bid + fair_price.ask) / 2

    def _send(self, record: DecoratedOrderFill):
        # Resends the whole record, not a partial payload: SQLiteWriter's
        # upsert overwrites every column present in the sent row, so a
        # partial send would clobber earlier markout fair prices back to NULL.
        self.decorated_order_fill_event.send(
            self.decorated_order_fill_event, decorated_order_fill=record
        )
