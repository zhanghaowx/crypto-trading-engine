from datetime import datetime
from threading import Lock
from typing import Union

import pytz


class TimeManager:
    """
    Provides a way to switch between using real machine time or use a fake
    time.
    When fake time is set and stored in the class, the time is frozen until
    the next change.
    There could be only one TimeManager for the entire application in order to
    ensure fake time is synchronized between classes.
    """

    _lock = Lock()

    def __init__(self) -> None:
        self._fake_time: Union[None, datetime] = None
        self._fake_time_admin: object = None

    def claim_admin(self, user: object) -> None:
        """
        Claim the admin of the fake time. Only the 1st user who invoked this
        method will grant admin and other users will be rejected.
        Args:
            user: A unique identifier for the user who wants to claim the admin
        Returns:
            None
        """
        with self._lock:
            if self._fake_time_admin:
                raise RuntimeError("Admin already claimed by another user!")
            self._fake_time_admin = user

        assert (
            self._fake_time_admin
        ), "Attempting to claim admin without success"

    def use_real_time(self, admin: object) -> None:
        """
        Set to use real time. Only the admin will be able to reset the fake
        time.

        Args:
            admin: A unique identifier from the admin to check for permissions
        Returns:
            None
        """
        self._check_admin(admin)

        with self._lock:
            if self._fake_time:
                self._fake_time = None

    def use_fake_time(self, fake_time: datetime, admin: object) -> None:
        """
        Set to use a fake time. Only the admin will be able to reset the fake
        time.

        Args:
            fake_time: A fake datetime to use
            admin: A unique identifier from the admin to check for permissions
        Returns:
            None
        """
        self._check_admin(admin)

        with self._lock:
            self._fake_time = fake_time

    def get_current_time(self) -> datetime:
        """
        Get the current time based on if the fake time is set.
        Returns: The current real time or fake time.
        """
        with self._lock:
            if self._fake_time:
                return self._fake_time
            else:
                return datetime.now(pytz.utc)

    def _check_admin(self, user: object) -> None:
        if not self._fake_time_admin:
            raise RuntimeError(
                "Admin not assigned yet. Please claim your admin permission "
                "first."
            )

        if self._fake_time_admin != user:
            raise RuntimeError(
                "Only one user could set/reset time in TimeManager. "
                "Others shall only read time from TimeManager."
            )


def create_time_manager(singleton=TimeManager()):
    return singleton
