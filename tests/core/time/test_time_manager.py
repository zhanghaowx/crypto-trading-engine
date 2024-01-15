import unittest
from datetime import datetime, timedelta
from threading import Thread
import pytz

from crypto_trading_engine.core.time.time_manager import (
    TimeManager,
    time_manager,
)


class TimeManagerTest(unittest.TestCase):
    def tearDown(self):
        time_manager().force_reset()

    def test_use_real_time_admin_taken(self):
        # Arrange
        time_manager = TimeManager()
        admin_user1 = object()
        admin_user2 = object()

        # Act
        time_manager.claim_admin(admin_user1)

        # Assert
        with self.assertRaises(RuntimeError) as context:
            time_manager.use_real_time(admin_user2)

        self.assertEqual(
            "Only one user could set/reset time in TimeManager. "
            "Others shall only read time from TimeManager.",
            str(context.exception),
        )

    def test_use_real_time_without_claim_admin(self):
        # Arrange
        time_manager = TimeManager()
        admin_user = object()

        # Assert
        with self.assertRaises(RuntimeError):
            time_manager.use_real_time(admin_user)

    def test_use_real_time(self):
        # Arrange
        time_manager = TimeManager()
        admin_user = object()

        # Act
        time_manager.claim_admin(admin_user)
        time_manager.use_real_time(admin_user)

        # Assert
        current_time = time_manager.now()
        self.assertAlmostEqual(
            current_time, datetime.now(pytz.utc), delta=timedelta(seconds=1)
        )
        self.assertFalse(time_manager.is_using_fake_time())

    def test_use_fake_time_admin_taken(self):
        # Arrange
        time_manager = TimeManager()
        admin_user1 = object()
        admin_user2 = object()
        fake_time = datetime(2022, 1, 1, tzinfo=pytz.utc)

        # Act
        time_manager.claim_admin(admin_user1)

        # Assert
        with self.assertRaises(RuntimeError) as context:
            time_manager.use_fake_time(fake_time, admin_user2)

        self.assertEqual(
            "Only one user could set/reset time in TimeManager. "
            "Others shall only read time from TimeManager.",
            str(context.exception),
        )

    def test_use_fake_time_without_claim_admin(self):
        # Arrange
        time_manager = TimeManager()
        admin_user = object()
        fake_time = datetime(2022, 1, 1, tzinfo=pytz.utc)

        # Assert
        with self.assertRaises(RuntimeError):
            time_manager.use_fake_time(fake_time, admin_user)

    def test_use_fake_time(self):
        # Arrange
        time_manager = TimeManager()
        admin_user = object()
        fake_time = datetime(2022, 1, 1, tzinfo=pytz.utc)

        # Act
        time_manager.claim_admin(admin_user)
        time_manager.use_fake_time(fake_time, admin_user)

        # Assert
        self.assertEqual(fake_time, time_manager.now())
        self.assertTrue(time_manager.is_using_fake_time())

    def test_switch_back_to_real_time(self):
        # Arrange
        time_manager = TimeManager()
        admin_user = object()
        fake_time = datetime(2022, 1, 1, tzinfo=pytz.utc)

        # Act
        time_manager.claim_admin(admin_user)
        time_manager.use_fake_time(fake_time, admin_user)
        time_manager.use_real_time(admin_user)

        # Assert
        current_time = time_manager.now()
        self.assertAlmostEqual(
            current_time, datetime.now(pytz.utc), delta=timedelta(seconds=1)
        )

    def test_use_fake_time_already_set(self):
        # Arrange
        time_manager = TimeManager()
        admin_user = object()
        fake_time1 = datetime(2022, 1, 1, tzinfo=pytz.utc)
        fake_time2 = datetime(2022, 2, 1, tzinfo=pytz.utc)

        # Act
        time_manager.claim_admin(admin_user)
        time_manager.use_fake_time(fake_time1, admin_user)
        time_manager.use_fake_time(fake_time2, admin_user)

        # Assert
        self.assertEqual(fake_time2, time_manager.now())

    def test_claim_admin(self):
        # Arrange
        tm = time_manager()
        admin_user1 = object()
        admin_user2 = object()

        # Act
        tm.claim_admin(admin_user1)

        # Assert
        with self.assertRaises(RuntimeError) as context:
            tm.claim_admin(admin_user2)

        self.assertEqual(
            "Admin already claimed by another user!", str(context.exception)
        )

    def test_claim_admin_multiple_threads(self):
        # Arrange
        time_manager = TimeManager()
        admin_user1 = object()
        admin_user2 = object()

        def claim_admin_thread():
            time_manager.claim_admin(admin_user1)

        # Act
        thread = Thread(target=claim_admin_thread)
        thread.start()
        thread.join()

        # Assert
        with self.assertRaises(RuntimeError):
            time_manager.claim_admin(admin_user2)

    def test_multi_time_manager(self):
        tm1 = time_manager()
        tm2 = time_manager()
        admin = object()
        fake_time1 = datetime(2022, 1, 1, tzinfo=pytz.utc)

        tm1.claim_admin(admin)
        tm1.use_fake_time(fake_time1, admin)

        self.assertEqual(tm1.now(), tm2.now())

    def test_reset_time_manager(self):
        tm1 = time_manager()
        tm2 = time_manager()
        admin = object()

        tm1.claim_admin(admin)
        with self.assertRaises(RuntimeError):
            tm2.claim_admin(admin)

        tm1.force_reset()
        tm2.claim_admin(admin)

        with self.assertRaises(RuntimeError) as context:
            tm1.claim_admin(admin)
        self.assertEqual(
            "Admin already claimed by another user!", str(context.exception)
        )
