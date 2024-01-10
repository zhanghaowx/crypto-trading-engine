import asyncio
from datetime import datetime

import pytz

from crypto_trading_engine.core.health_monitor.heartbeat import Heartbeat


class HeartbeatMonitor:
    class DecoratedHeartbeat:
        def __init__(
            self,
            heartbeat: Heartbeat,
            zombie: bool = False,
        ):
            self.heartbeat = heartbeat
            self.zombie = zombie
            self.creation_time = datetime.now(pytz.utc)

        def is_zombie(self):
            return self.zombie

        def set_is_zombie(self, timeout_in_seconds: float):
            seconds_since_creation = (
                datetime.now(pytz.utc) - self.creation_time
            ).total_seconds()
            self.zombie = seconds_since_creation > timeout_in_seconds

    def __init__(self, timeout_in_seconds: float = 10):
        """
        Heartbeat Monitor oversees all heartbeats in the system and maintaining
        a record of the last heartbeat from each component. It decides the
        overall health state of the application.

        Args:
            timeout_in_seconds: Time in seconds to wait before deciding if a
            heartbeat is stale
        """
        self.all_heartbeats: dict[
            str, HeartbeatMonitor.DecoratedHeartbeat
        ] = {}
        self._timeout_in_seconds: float = timeout_in_seconds
        asyncio.create_task(self._detect_zombies_periodically())

    def on_heartbeat(self, sender: str, heartbeat: Heartbeat):
        """
        Store heartbeat on receiving a heartbeat from any component
        Args:
            sender: Name of the sender
            heartbeat: Heartbeat message from the sender

        Returns:
            None
        """
        self.all_heartbeats[sender] = HeartbeatMonitor.DecoratedHeartbeat(
            heartbeat=heartbeat, zombie=False
        )
        self._detect_zombies()

    def _detect_zombies(self):
        for sender, decorated_heartbeat in self.all_heartbeats.items():
            self.all_heartbeats[sender].set_is_zombie(self._timeout_in_seconds)

    async def _detect_zombies_periodically(self):
        while True:
            self._detect_zombies()
            await asyncio.sleep(self._timeout_in_seconds * 0.5)
