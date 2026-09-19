import random
import unittest
from collections.abc import Callable
from datetime import datetime
from unittest.mock import patch

import pytz
from blinker import ANY, NamedSignal

from jolteon.engine.core.event.signal import signal, signal_namespace
from jolteon.engine.core.parameter.parameter_service import (
    StaticParameterService,
)
from jolteon.engine.core.side import MarketSide
from jolteon.engine.execution.kraken.fee_schedule import KrakenFeeSchedule
from jolteon.engine.execution.mock_execution_service import (
    MockExecutionService,
)
from jolteon.engine.market_data.core.bbo import BBO
from jolteon.engine.market_data.core.trade import Trade
from jolteon.engine.position.position_manager import (
    PositionManager,
    PositionUpdate,
)
from jolteon.engine.post_trade.decorated_order_fill import DecoratedOrderFill
from jolteon.engine.post_trade.post_trade_service import PostTradeService
from jolteon.engine.strategy.market_making.market_making_strategy import (
    MarketMakingStrategy,
)
from jolteon.engine.strategy.market_making.parameters import (
    MarketMakingParameters,
)
from jolteon.engine.strategy.market_making.quote_offset import (
    StaticQuoteOffsetService,
)

ReceiverOrder = Callable[[list], None]


def _shuffled(seed: int) -> ReceiverOrder:
    return lambda receivers: random.Random(seed).shuffle(receivers)


_RECEIVER_ORDERS: dict[str, ReceiverOrder] = {
    "unchanged": lambda receivers: None,
    "reversed": lambda receivers: receivers.reverse(),
    **{f"shuffled {seed}": _shuffled(seed) for seed in range(4)},
}


def _bbo(bid_price: float, ask_price: float) -> BBO:
    return BBO(
        symbol="BTC/USD",
        bid_price=bid_price,
        bid_quantity=1.0,
        ask_price=ask_price,
        ask_quantity=1.0,
    )


def _market_trade(side: MarketSide, price: float, quantity: float) -> Trade:
    return Trade(
        exchange_trade_id=0,
        client_order_id="",
        symbol="BTC/USD",
        maker_order_id="",
        taker_order_id="",
        side=side,
        price=price,
        fee=0.0,
        quantity=quantity,
        transaction_time=datetime(2024, 1, 1, tzinfo=pytz.utc),
    )


class _Outcome:
    def __init__(self):
        self.fills = list[tuple]()
        self.decorated_fills = list[tuple]()
        self.positions = list[float]()

    def on_fill(self, _, trade: Trade):
        self.fills.append((trade.side, trade.price, trade.quantity))

    def on_decorated_fill(self, _, decorated_order_fill: DecoratedOrderFill):
        self.decorated_fills.append(
            (
                decorated_order_fill.side,
                decorated_order_fill.fair_price_at_fill,
            )
        )

    def on_position_updated(self, _, position_update: PositionUpdate):
        self.positions.append(position_update.volume)


class TestPaperTradingDeliveryOrder(unittest.IsolatedAsyncioTestCase):
    """
    A paper session's result must not depend on the order a signal calls
    its receivers in.
    """

    def _run_session(self, receiver_order: ReceiverOrder) -> tuple:
        venue = MockExecutionService(KrakenFeeSchedule)
        strategy = MarketMakingStrategy(
            symbol="BTC/USD",
            requote_tolerance=0.0,
            parameter_service=StaticParameterService(
                MarketMakingParameters(quote_size=0.01, max_inventory=0.02)
            ),
            quote_offset_service=StaticQuoteOffsetService(half_spread=1.0),
        )
        position_manager = PositionManager()
        post_trade_service = PostTradeService()
        outcome = _Outcome()
        for component in (
            venue,
            strategy,
            position_manager,
            post_trade_service,
        ):
            component.connect()
        signal("order_fill").connect(outcome.on_fill)
        signal("decorated_order_fill").connect(outcome.on_decorated_fill)
        signal("position_updated").connect(outcome.on_position_updated)

        receivers_as_connected = NamedSignal.receivers_for

        def receivers_for(named_signal, sender):
            receivers = list(receivers_as_connected(named_signal, sender))
            receiver_order(receivers)
            return iter(receivers)

        bbo_feed, market_trade = (
            signal("bbo_feed"),
            signal("market_trade_feed"),
        )
        with patch.object(NamedSignal, "receivers_for", receivers_for):
            bbo_feed.send(bbo_feed, bbo=_bbo(99.0, 101.0))
            # Our bid rests behind the 1.0 displayed at 99 when it arrived,
            # so this print is used up by the queue ahead of us.
            market_trade.send(
                market_trade,
                market_trade=_market_trade(MarketSide.SELL, 99.0, 0.5),
            )
            bbo_feed.send(bbo_feed, bbo=_bbo(100.0, 102.0))
            market_trade.send(
                market_trade,
                # Big enough to clear the 1.0 resting at our ask price
                # before any of it reaches us.
                market_trade=_market_trade(MarketSide.BUY, 103.0, 1.05),
            )
        for named_signal in signal_namespace.values():
            for receiver in list(named_signal.receivers_for(ANY)):
                named_signal.disconnect(receiver)

        resting = sorted(
            (r.order.side, r.price, r.remaining_quantity)
            for r in venue._resting_orders.values()
        )
        return (
            outcome.fills,
            outcome.decorated_fills,
            outcome.positions,
            position_manager.pnl,
            resting,
        )

    async def test_session_outcome_is_independent_of_receiver_order(self):
        expected = self._run_session(_RECEIVER_ORDERS["unchanged"])
        self.assertEqual(
            [(MarketSide.SELL, 102.0, 0.01)],
            expected[0],
        )

        for name, receiver_order in _RECEIVER_ORDERS.items():
            with self.subTest(receiver_order=name):
                self.assertEqual(expected, self._run_session(receiver_order))


if __name__ == "__main__":
    unittest.main()
