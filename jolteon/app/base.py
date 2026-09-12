import asyncio
import logging
import threading
from datetime import datetime

import pytz

from jolteon.engine.core.event.signal_manager import SignalManager
from jolteon.engine.core.event.signal_recorder import SignalRecorder
from jolteon.engine.core.logging.logger import setup_global_logger
from jolteon.engine.core.parameter.parameter_service import (
    IParameterService,
    StaticParameterService,
    use_parameter_service,
)
from jolteon.engine.market_data.book_feature_recorder import (
    BookFeatureRecorder,
)
from jolteon.engine.market_data.data_source import DatabaseDataSource
from jolteon.engine.market_data.feed import IMarketDataFeed
from jolteon.engine.market_data.historical_feed import HistoricalFeed
from jolteon.engine.position.position_manager import PositionManager
from jolteon.engine.post_trade.post_trade_service import PostTradeService
from jolteon.engine.strategy.market_making.fair_value.fair_price_model import (
    IFairPriceModel,
)


class ApplicationBase(SignalManager):
    THREAD_ENABLED: bool = True

    def __init__(
        self,
        symbol: str,
        database_name,
        logfile_name,
        strategy: object = None,
        fair_price_model: IFairPriceModel | None = None,
        parameter_service: IParameterService | None = None,
    ):
        """
        Connects different components to build the trading engine. It supports
        one symbol and one strategy.
        """
        self._symbol = symbol

        # Published before anything else is built: the layers underneath
        # the wired components read their own tunables from here, and
        # setup_global_logger below is already one of them.
        self._parameter_service = parameter_service or StaticParameterService()
        use_parameter_service(self._parameter_service)

        # Logs get their own file so their writer never contends with
        # `database_name`'s for its write lock.
        setup_global_logger(
            log_level=logging.DEBUG,
            logfile_name=logfile_name,
            logfile_db=f"{logfile_name}.sqlite",
        )

        self._signal_recorder = SignalRecorder(
            database_name=database_name,
        )
        self._book_feature_recorder = BookFeatureRecorder()
        self._fair_price_model = fair_price_model
        # _fair_price_model, then _position_manager, then
        # _post_trade_service must sort in this order: connect_all()
        # connects subscribers in alphabetical dir() order, an adjustment
        # needs a tick before the strategy quotes off it, and
        # PostTradeService.on_fill relies on PositionManager's
        # position_updated having already fired for the same fill.
        self._position_manager = PositionManager()
        self._post_trade_service = PostTradeService(
            fair_price_model=fair_price_model
        )
        self._strategy = strategy

        self._exec_service: object = None
        self._md: IMarketDataFeed | None = None

        self._background_tasks: dict[
            str, tuple[asyncio.AbstractEventLoop, asyncio.Task]
        ] = {}

    def use_execution_service(self, service: object):
        print(f"Using {type(service).__name__}")
        self._exec_service = service
        return self

    def use_market_data_service(self, market_data: IMarketDataFeed):
        print(f"Using {type(market_data).__name__}")
        self._md = market_data
        return self

    async def run_start(self, *args):
        assert self._md, "Please set a market data service before running"
        self._connect_signals()
        self._parameter_service.start()

        # stop() in a finally, or a feed that raises leaves the parameter
        # poller and the recorder running behind it.
        try:
            if ApplicationBase.THREAD_ENABLED:
                md_thread, md_loop, md_task = self._start_thread(
                    "MD", self._md.connect(self._symbol, *args)
                )
                self._background_tasks["MD"] = (md_loop, md_task)

                # join(), not a sleep loop, so shutdown isn't delayed by a
                # poll interval once the thread actually finishes.
                await asyncio.get_running_loop().run_in_executor(
                    None, md_thread.join
                )
            else:
                await self._md.connect(self._symbol, *args)

            for symbol, position in self._position_manager.positions.items():
                print(f"{symbol}: {position.volume}")
        finally:
            self.stop()

        return self._position_manager.pnl

    def request_shutdown(self):
        # sys.exit() from a signal handler only unwinds the main thread;
        # a task in another thread's loop needs to be cancelled directly.
        for loop, task in self._background_tasks.values():
            loop.call_soon_threadsafe(task.cancel)

    async def run_local_replay(self, db: str):
        data_source = DatabaseDataSource(db)
        start = data_source.start_time()
        end = data_source.end_time()

        self.use_market_data_service(HistoricalFeed(data_source))

        logging.info(f"Replaying {self._symbol} from {start} to {end}")
        print(f"Replaying {self._symbol} from {start} to {end}")
        now = datetime.now(tz=pytz.utc)
        return await self.run_start(start, min(now, end))

    def stop(self):
        # Before the recorder is disconnected and flushed, so the last
        # thing the poller published still reaches the database.
        self._parameter_service.stop()
        self._disconnect_signals()

    def _connect_signals(self):
        self.connect_all()
        self._signal_recorder.start_recording()

    def _disconnect_signals(self):
        self.disconnect_all()
        self._signal_recorder.stop_recording()

    @staticmethod
    def _start_thread(name: str, task):
        ready = threading.Event()
        handle: dict[str, object] = {}

        def run_task():
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)

            running_task = loop.create_task(task)
            handle["loop"] = loop
            handle["task"] = running_task
            ready.set()

            try:
                loop.run_until_complete(running_task)
            except asyncio.CancelledError:
                pass
            except Exception as e:
                logging.error(f"{name} got exception: {e}", exc_info=True)
                raise e

            loop.close()

        thread = threading.Thread(
            name=name,
            target=run_task,
        )
        thread.start()
        ready.wait()

        return thread, handle["loop"], handle["task"]
