"""A day rolling over is an accounting boundary and nothing else."""

import unittest
import uuid
from datetime import datetime, timezone

from jolteon.engine.core.event.signal import signal
from jolteon.engine.core.session.trading_session import TradingSessionRun
from jolteon.engine.core.session.trading_session_service import (
    TradingSessionService,
)
from jolteon.engine.core.side import MarketSide
from jolteon.engine.core.time.time_manager import time_manager
from jolteon.engine.market_data.core.bbo import BBO
from jolteon.engine.market_data.core.trade import Trade
from jolteon.engine.position.position_manager import PositionManager


def _bbo() -> BBO:
    return BBO(
        symbol="BTC/USD",
        bid_price=100.0,
        bid_quantity=1.0,
        ask_price=102.0,
        ask_quantity=1.0,
    )


def _buy(quantity: float, at: datetime) -> Trade:
    return Trade(
        exchange_trade_id=1,
        client_order_id="1",
        symbol="BTC/USD",
        maker_order_id=str(uuid.uuid4()),
        taker_order_id=str(uuid.uuid4()),
        side=MarketSide.BUY,
        price=100.0,
        fee=0.1,
        quantity=quantity,
        transaction_time=at,
    )


class TestRolloverLeavesTradingAlone(unittest.TestCase):
    def setUp(self):
        self.recorded = list[TradingSessionRun]()
        self.session_service = TradingSessionService(
            run_id="run-a", exchange="Kraken", symbol="BTC/USD"
        )
        self.session_service.trading_session_run_event.connect(self._record)
        self.position_manager = PositionManager()
        self.session_service.connect()
        self.position_manager.connect()
        time_manager().claim_admin(self)

    def tearDown(self):
        time_manager().reset(admin=self)
        self.position_manager.disconnect()
        self.session_service.disconnect()
        self.session_service.trading_session_run_event.disconnect(self._record)

    def _record(self, _, trading_session_run: TradingSessionRun):
        self.recorded.append(TradingSessionRun(**vars(trading_session_run)))

    def _tick(self, moment: datetime) -> None:
        time_manager().use_fake_time(moment, admin=self)
        bbo_feed = signal("bbo_feed")
        bbo_feed.send(bbo_feed, bbo=_bbo())

    def test_inventory_held_at_midnight_is_still_held_after_it(self):
        before = datetime(2026, 9, 20, 23, 59, 30, tzinfo=timezone.utc)
        self._tick(before)

        order_fill = signal("order_fill")
        order_fill.send(order_fill, trade=_buy(0.003, before))
        held = self.position_manager.positions["BTC/USD"].volume
        pnl = self.position_manager.pnl

        self._tick(datetime(2026, 9, 21, 0, 0, 1, tzinfo=timezone.utc))

        self.assertEqual("2026-09-21", self.session_service.current_session_id)
        self.assertEqual(
            held, self.position_manager.positions["BTC/USD"].volume
        )
        self.assertEqual(pnl, self.position_manager.pnl)

    def test_the_day_the_engine_crossed_into_is_recorded(self):
        self._tick(datetime(2026, 9, 20, 23, 59, 30, tzinfo=timezone.utc))
        self._tick(datetime(2026, 9, 21, 0, 0, 1, tzinfo=timezone.utc))

        self.assertEqual(
            ["2026-09-20", "2026-09-20", "2026-09-21"],
            [run.session_id for run in self.recorded],
        )
