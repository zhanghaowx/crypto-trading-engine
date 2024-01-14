"""
CLI interface for crypto_trading_engine project.
"""
import signal
import sys
from datetime import datetime

import pytz

from crypto_trading_engine.app import Application


def graceful_exit(signum, frame):
    print("Ctrl+C detected. Performing graceful exit...")
    # Add your cleanup or shutdown code here
    sys.exit(0)


# Register the signal handler for Ctrl+C
signal.signal(signal.SIGINT, graceful_exit)


async def main():
    app = Application("ETH-USD", candlestick_interval_in_seconds=60)

    replay_start = datetime(
        2024, 1, 11, hour=0, minute=0, second=0, tzinfo=pytz.utc
    )
    replay_end = datetime(
        2024, 1, 11, hour=23, minute=59, second=0, tzinfo=pytz.utc
    )

    await app.run_replay(replay_start, replay_end)
