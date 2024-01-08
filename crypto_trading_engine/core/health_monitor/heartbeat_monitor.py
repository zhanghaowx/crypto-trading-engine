from crypto_trading_engine.core.health_monitor.heartbeat import Heartbeat, Heartbeater


class HeartbeatMonitor:
    """
    Heartbeat Monitor oversees all heartbeats in the system and maintaining a record of the last heartbeat from each
    component. It decides the overall health state of the application.
    """
    def __init__(self):
        self._all_issues = {}

    def on_heartbeat(self, sender: str, heartbeat: Heartbeater):
        """
        On receiving a heartbeat from any component
        Args:
            sender: Name of the sender
            heartbeat: Heartbeat message from the sender

        Returns:
            None
        """
        self._all_issues[sender] = heartbeat
