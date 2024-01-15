from datetime import datetime

import pytz

from crypto_trading_engine.core.time.time_manager import create_time_manager
from crypto_trading_engine.risk_limit.risk_limit import IRiskLimit


class OrderFrequencyLimit(IRiskLimit):
    """
    Limits number of orders per second
    """

    def __init__(self, number_of_orders: int, in_seconds: int):
        self.number_of_orders = number_of_orders
        self.in_seconds = in_seconds
        self.timestamps = list[datetime]()

    def can_send(self):
        self._update()
        return len(self.timestamps) < self.number_of_orders

    def do_send(self):
        assert self.can_send()
        now = create_time_manager().get_current_time()
        self.timestamps.append(now)
        self._update()

    def _update(self):
        now = create_time_manager().get_current_time()
        self.timestamps = [
            t
            for t in self.timestamps
            if (now - t).total_seconds() < self.in_seconds
        ]
