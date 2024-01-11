import unittest
from datetime import datetime, timedelta
from unittest.mock import patch

import pytz
from freezegun import freeze_time

from crypto_trading_engine.risk_limit.order_frequency_limit import (
    OrderFrequencyLimit,
)


class TestOrderFrequencyLimit(unittest.TestCase):
    @freeze_time("2022-01-01 00:00:00 UTC")
    def test_can_send(self):
        # Setup
        order_limit = OrderFrequencyLimit(number_of_orders=5, in_seconds=10)

        # Initially, can_send should return True
        self.assertTrue(order_limit.can_send())

        # Simulate sending 5 orders
        for _ in range(5):
            order_limit.do_send()

        # Now, can_send should return False as the limit is reached
        self.assertFalse(order_limit.can_send())

        # Move time to the next interval
        # Now, can_send should return True again
        with freeze_time("2022-01-01 00:00:11 UTC"):
            order_limit.update()
            self.assertTrue(order_limit.can_send())

    @freeze_time("2022-01-01 00:00:00 UTC")
    def test_do_send(self):
        # Setup
        order_limit = OrderFrequencyLimit(number_of_orders=2, in_seconds=5)

        # Initially, can_send should return True
        self.assertTrue(order_limit.can_send())

        # Send the first order
        order_limit.do_send()

        # Send the second order
        order_limit.do_send()

        # The third attempt should raise an AssertionError
        # as the limit is reached
        with self.assertRaises(AssertionError):
            order_limit.do_send()

    @freeze_time("2022-01-01 00:00:00 UTC")
    def test_update(self):
        # Setup
        order_limit = OrderFrequencyLimit(number_of_orders=3, in_seconds=10)

        # Send two orders
        order_limit.do_send()
        order_limit.do_send()

        # Move time to the next interval
        with freeze_time("2022-01-01 00:00:11 UTC"):
            # Send another order
            order_limit.do_send()

            # The timestamps list should only contain the timestamp of
            # the third order
            order_limit.update()
            self.assertEqual(len(order_limit.timestamps), 1)
