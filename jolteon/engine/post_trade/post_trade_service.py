from jolteon.engine.core.event.signal import signal, subscribe
from jolteon.engine.core.event.signal_subscriber import SignalSubscriber
from jolteon.engine.market_data.core.trade import Trade
from jolteon.engine.post_trade.decorated_order_fill import DecoratedOrderFill
from jolteon.engine.strategy.market_making.fair_value.fair_price_model import (
    IFairPriceModel,
)
from jolteon.engine.strategy.market_making.fair_value.mid_price_model import (
    MidPriceFairPriceModel,
)


class PostTradeService(SignalSubscriber):
    """Record one immutable analytics row for every execution.

    The service deliberately does not calculate fair value or schedule
    markouts. Fair-price models already publish a timestamped series of
    observations; post-processing joins fills to that series at whatever
    horizons an analysis asks for.
    """

    def __init__(self, fair_price_model: IFairPriceModel | None = None):
        model = fair_price_model or MidPriceFairPriceModel()
        self._fair_price_model_name = type(model).__name__
        self.decorated_order_fill_event = signal("decorated_order_fill")

    @subscribe("order_fill")
    def on_fill(self, _: str, trade: Trade):
        self.decorated_order_fill_event.send(
            self.decorated_order_fill_event,
            decorated_order_fill=DecoratedOrderFill(
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
                fee=trade.fee,
                fair_price_model=self._fair_price_model_name,
            ),
        )
