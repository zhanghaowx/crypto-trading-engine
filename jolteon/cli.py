"""
CLI interface for jolteon project.
"""
import asyncio
import signal
import sys
from datetime import datetime

import pytz

from jolteon.app import Application


def graceful_exit(signum, frame):
    print("Ctrl+C detected. Performing graceful exit...")
    # Add your cleanup or shutdown code here
    sys.exit(0)


# Register the signal handler for Ctrl+C
signal.signal(signal.SIGINT, graceful_exit)


async def main(replay: bool = False):
    symbol = "BTC/USD"
    replay_start = datetime(
        2024, 1, 16, hour=0, minute=0, second=0, tzinfo=pytz.utc
    )
    replay_end = datetime(
        2024, 1, 16, hour=23, minute=59, second=0, tzinfo=pytz.utc
    )

    app = Application(symbol, use_mock_execution=False)
    if replay:
        pnl = await app.run_replay(replay_start, replay_end)
    else:
        pnl = await app.run()

    print(f"PnL: {pnl}")


if __name__ == "__main__":
    asyncio.run(main())
