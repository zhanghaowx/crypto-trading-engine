"""Records which trading sessions an engine run traded, and when."""

import logging
from datetime import datetime

from jolteon.engine.core.event.signal import signal, subscribe
from jolteon.engine.core.event.signal_subscriber import SignalSubscriber
from jolteon.engine.core.session.trading_session import (
    TradingSessionRun,
    trading_session_id,
)
from jolteon.engine.core.time.time_manager import time_manager
from jolteon.engine.market_data.core.bbo import BBO

# How far the clock may move before the open session's row is written
# again. The row is rewritten in place, so this only decides how stale
# the last-traded-at of a session still being traded may read.
_REFRESH_SECONDS = 60.0


class TradingSessionService(SignalSubscriber):
    """
    Watches the clock the engine runs on and names the trading session
    every moment of it belongs to.

    Crossing into the next session is an accounting boundary and nothing
    more: this cancels no order, flattens no inventory and touches no
    strategy state, so a position held at midnight is still held at a
    minute past.
    """

    def __init__(self, run_id: str, exchange: str, symbol: str):
        self._run_id = run_id
        self._exchange = exchange
        self._symbol = symbol
        self._current: TradingSessionRun | None = None
        self.trading_session_run_event = signal("trading_session_run")

    @property
    def current_session_id(self) -> str | None:
        return self._current.session_id if self._current else None

    @subscribe("bbo_feed")
    def on_bbo(self, _: str, bbo: BBO):
        self.observe(time_manager().now())

    def observe(self, moment: datetime) -> None:
        """Note that the engine was trading at `moment`, opening the next
        trading session where that moment has crossed into one."""
        session_id = trading_session_id(moment)
        current = self._current
        if current is None:
            self._open(session_id, moment)
        elif current.session_id != session_id:
            self._record_up_to(moment)
            self._open(session_id, moment)
        elif (
            moment - current.last_seen_at
        ).total_seconds() >= _REFRESH_SECONDS:
            self._record_up_to(moment)

    def stop(self) -> None:
        """Record where the engine left the session it was trading."""
        if self._current is not None:
            self._record_up_to(time_manager().now())
            self._current = None

    def _open(self, session_id: str, moment: datetime) -> None:
        logging.info("Trading session %s opened", session_id)
        self._current = TradingSessionRun(
            session_run_id=TradingSessionRun.identity(
                session_id, self._run_id
            ),
            session_id=session_id,
            run_id=self._run_id,
            exchange=self._exchange,
            symbol=self._symbol,
            first_seen_at=moment,
            last_seen_at=moment,
        )
        self._send(self._current)

    def _record_up_to(self, moment: datetime) -> None:
        assert self._current is not None
        self._current.last_seen_at = moment
        self._send(self._current)

    def _send(self, session_run: TradingSessionRun) -> None:
        self.trading_session_run_event.send(
            self.trading_session_run_event, trading_session_run=session_run
        )
