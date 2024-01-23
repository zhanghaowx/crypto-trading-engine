import cProfile
import sqlite3
import tempfile
import unittest
from datetime import datetime

import pandas as pd
import pytz

from jolteon.core.time.time_manager import time_manager
from jolteon.strategy.bull_trend_rider.strategy_parameters import (
    StrategyParameters,
)


###########################################################################
# The followings are scenario tests which will make calls to Kraken's API
###########################################################################
class TestApplication(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.symbol = "BTC/USD"

        from jolteon.app.kraken import KrakenApplication

        KrakenApplication.THREAD_SYNC_INTERVAL = 0.01

        self.application = KrakenApplication(
            symbol=self.symbol,
            database_name=f"{tempfile.gettempdir()}/unittest.sqlite",
            logfile_name=f"{tempfile.gettempdir()}/unittest.log",
            strategy_params=StrategyParameters(),
        )

    async def asyncTearDown(self):
        time_manager().force_reset()

    async def test_replay_on_bull_flag_opportunity(self):
        profiler = cProfile.Profile()
        profiler.enable()

        start_time = datetime(
            2024, 1, 21, hour=18, minute=5, second=0, tzinfo=pytz.utc
        )
        end_time = datetime(
            2024, 1, 21, hour=18, minute=35, second=0, tzinfo=pytz.utc
        )
        pnl = await self.application.run_replay(start_time, end_time)
        print(f"PnL: {pnl}")
        self.assertGreater(pnl, 0)

        profiler.disable()
        profiler.print_stats(sort='cumulative')

        conn = sqlite3.connect(f"{tempfile.gettempdir()}/unittest.sqlite")
        df = pd.read_sql_query("SELECT * FROM sqlite_master", con=conn)
        self.assertGreater(len(df), 0)

        df = pd.read_sql_query("SELECT * FROM heartbeat", con=conn)
        self.assertGreater(len(df), 0)

        conn.close()

    # async def test_replay_on_bull_trend_following(self):
    #     start_time = datetime(
    #         2024, 1, 22, hour=3, minute=30, second=0, tzinfo=pytz.utc
    #     )
    #     end_time = datetime(
    #         2024, 1, 22, hour=4, minute=30, second=0, tzinfo=pytz.utc
    #     )
    #     pnl = await self.application.run_replay(start_time, end_time)
    #     print(f"PnL: {pnl}")
    #     self.assertEqual(pnl, 0)
