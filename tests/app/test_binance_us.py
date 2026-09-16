import asyncio
from unittest.mock import AsyncMock, patch

import pytest

from jolteon.app.binance_us import BinanceUsApplication
from jolteon.engine.execution.binance_us.fee_schedule import (
    BinanceUsFeeSchedule,
)
from jolteon.engine.execution.mock_execution_service import (
    MockExecutionService,
)


def test_paper_application_uses_binance_feed_and_fees(tmp_path):
    application = BinanceUsApplication(
        "btc-usd",
        str(tmp_path / "live.sqlite"),
        str(tmp_path / "live.log"),
    )

    assert application._symbol == "BTC/USD"
    assert isinstance(application._exec_service, MockExecutionService)
    assert application._exec_service._fee_schedule is BinanceUsFeeSchedule


def test_live_execution_stays_disabled(tmp_path):
    with pytest.raises(NotImplementedError, match="use --paper"):
        BinanceUsApplication(
            "BTC/USD",
            str(tmp_path / "live.sqlite"),
            str(tmp_path / "live.log"),
            use_mock_execution=False,
        )


def test_start_uses_public_feed(tmp_path):
    application = BinanceUsApplication(
        "BTC/USD",
        str(tmp_path / "live.sqlite"),
        str(tmp_path / "live.log"),
    )
    with (
        patch("jolteon.app.binance_us.PublicFeed") as feed,
        patch(
            "jolteon.app.trading_application.TradingApplication.run_start",
            AsyncMock(return_value=3.0),
        ) as run,
    ):
        assert asyncio.run(application.start()) == 3.0

    assert application._md is feed.return_value
    run.assert_awaited_once()


def test_remote_replay_is_explicitly_unsupported(tmp_path):
    application = BinanceUsApplication(
        "BTC/USD",
        str(tmp_path / "live.sqlite"),
        str(tmp_path / "live.log"),
    )
    with pytest.raises(NotImplementedError, match="historical replay"):
        asyncio.run(application.run_replay(None, None))
