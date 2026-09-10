import asyncio

from jolteon.engine.core.event.signal import signal, subscribe
from jolteon.engine.core.event.signal_subscriber import SignalSubscriber
from jolteon.engine.market_data.core.bbo import BBO
from jolteon.engine.market_data.core.trade import Trade
from jolteon.engine.position.position_manager import PositionUpdate
from jolteon.engine.post_trade.decorated_order_fill import DecoratedOrderFill
from jolteon.engine.strategy.market_making.fair_value.fair_price_model import (
    FairPriceContext,
    IFairPriceModel,
)
from jolteon.engine.strategy.market_making.fair_value.mid_price_model import (
    MidPriceFairPriceModel,
)

_HORIZONS: tuple[tuple[str, float], ...] = (
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
        self._latest_volume = dict[str, float]()
        self._pending_position = dict[str, tuple[float, float]]()
        self._pending_fills = dict[int, DecoratedOrderFill]()

    @subscribe("ticker_feed")
    def on_bbo(self, _: str, bbo: BBO):
        self._latest_bbo[bbo.symbol] = bbo

    @subscribe("position_updated")
    def on_position_updated(self, _: str, position_update: PositionUpdate):
        before = self._latest_volume.get(position_update.symbol, 0.0)
        self._pending_position[position_update.symbol] = (
            before,
            position_update.volume,
        )
        self._latest_volume[position_update.symbol] = position_update.volume

    @subscribe("order_fill")
    def on_fill(self, _: str, trade: Trade):
        bbo = self._latest_bbo.get(trade.symbol)
        if bbo is None:
            return

        # Requires PositionManager's order_fill receiver - and the
        # position_updated it sends - to have already run for this fill.
        # Holds because ApplicationBase constructs _position_manager before
        # _post_trade_service, and SignalManager.connect_all() connects
        # subscribers in alphabetical dir() order.
        inventory_before, inventory_after = self._pending_position.pop(
            trade.symbol, (0.0, 0.0)
        )

        record = DecoratedOrderFill(
            trade_id=trade.trade_id,
            transaction_timestamp=trade.transaction_time,
            symbol=trade.symbol,
            side=trade.side,
            fill_price=trade.price,
            fill_qty=trade.quantity,
            fair_price_at_fill=self._fair_price(bbo),
            fee=trade.fee,
            inventory_before=inventory_before,
            inventory_after=inventory_after,
        )
        self._pending_fills[trade.trade_id] = record
        self._send(record)

        loop = asyncio.get_running_loop()
        for field_name, delay in _HORIZONS:
            loop.call_later(
                delay, self._on_horizon, trade.trade_id, field_name
            )

    def _on_horizon(self, trade_id: int, field_name: str):
        record = self._pending_fills.get(trade_id)
        if record is None:
            return

        bbo = self._latest_bbo.get(record.symbol)
        if bbo is not None:
            setattr(record, field_name, self._fair_price(bbo))
        self._send(record)

        if field_name == _HORIZONS[-1][0]:
            del self._pending_fills[trade_id]

    def _fair_price(self, bbo: BBO) -> float:
        fair_price = self._fair_price_model.calculate(
            FairPriceContext(bbo=bbo)
        )
        return (fair_price.bid + fair_price.ask) / 2

    def _send(self, record: DecoratedOrderFill):
        # Resends the whole record, not a partial payload: SQLiteWriter's
        # upsert overwrites every column present in the sent row, so a
        # partial send would clobber earlier horizon fields back to NULL.
        self.decorated_order_fill_event.send(
            self.decorated_order_fill_event, decorated_order_fill=record
        )
