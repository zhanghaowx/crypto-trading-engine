"""
CLI interface for jolteon project.
"""
import argparse
import asyncio
import signal
import sys
from datetime import datetime, timezone

import pytz

from jolteon.app.kraken import KrakenApplication as Application


def graceful_exit(signum, frame):
    print("Ctrl+C detected. Performing graceful exit...")
    # Add your cleanup or shutdown code here
    sys.exit(0)


# Register the signal handler for Ctrl+C
signal.signal(signal.SIGINT, graceful_exit)


async def main():
    app_start_time = datetime.now(tz=pytz.utc)

    parser = argparse.ArgumentParser(description="Jolteon Trading Engine")

    # Add command-line arguments
    # parser.add_argument(
    #     "--database", help="Path to the database file", required=True
    # )
    # parser.add_argument(
    #     "--logfile", help="Path to the log file", required=True
    # )
    parser.add_argument("--replay-start", help="Start time in ISO format")
    parser.add_argument("--replay-end", help="End time in ISO format")

    args = parser.parse_args()

    # Access the arguments
    # database_path = args.database
    # logfile_path = args.logfile
    replay_start = args.replay_start
    replay_end = args.replay_end

    # Your application logic here
    # print(f"Database Path: {database_path}")
    # print(f"Logfile Path: {logfile_path}")

    symbol = "BTC-USD"

    if replay_start and replay_end:
        replay_start_time = datetime.fromisoformat(replay_start).replace(
            tzinfo=timezone.utc
        )
        replay_end_time = datetime.fromisoformat(replay_end).replace(
            tzinfo=timezone.utc
        )
        print(f"Replay Start: {replay_start_time}")
        print(f"Replay End  : {replay_end_time}")
        app = Application(
            symbol,
            use_mock_execution=True,
            candlestick_interval_in_seconds=60,
            database_name="/tmp/replay.sqlite",
            logfile_name="/tmp/replay.log",
        )
        pnl = await app.run_replay(replay_start_time, replay_end_time)
    else:
        app = Application(
            symbol,
            use_mock_execution=False,
            candlestick_interval_in_seconds=60,
            database_name="/tmp/jolteon.sqlite",
            logfile_name="/tmp/jolteon.log",
        )
        pnl = await app.start()
    print(f"PnL: {pnl}")

    app_end_time = datetime.now(tz=pytz.utc)
    print(f"Total Runtime: {app_end_time - app_start_time}")


if __name__ == "__main__":
    asyncio.run(main())
