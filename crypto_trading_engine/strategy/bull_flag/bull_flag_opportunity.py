from dataclasses import dataclass
from datetime import datetime

from crypto_trading_engine.market_data.core.candlestick import Candlestick
from crypto_trading_engine.strategy.bull_flag.parameters import Parameters
from crypto_trading_engine.strategy.core.trade_opportunity import (
    TradeOpportunity,
)


@dataclass
class BullFlagOpportunity(TradeOpportunity):
    start: datetime | None = None
    end: datetime | None = None
    expected_trade_price: float = 0.0
    risk_reward_ratio: float = 0.0
    consolidation_period_length: int = 0
    consolidation_period_max_ratio: float = 0.0
    bull_flag_return_pct: float = 0.0
    bull_flag_open_close: float = 0.0
    starts_extremely_bullish: bool = False
    ends_trending_bearish: bool = True
    stop_loss_from_support: float = 0.0
    stop_loss_from_atr: float = 0.0

    def set_bull_flag(self, candlestick: Candlestick):
        self.bull_flag_open_close = candlestick.close - candlestick.open
        self.bull_flag_return_pct = candlestick.return_percentage()

    def set_consolidation(self, consolidation_period: list[Candlestick]):
        assert self.bull_flag_open_close != 0.0
        assert len(consolidation_period) > 0

        max_ratio = 0.0
        for candlestick in consolidation_period:
            current_body = abs(candlestick.open - candlestick.close)
            max_ratio = max(
                max_ratio, current_body / abs(self.bull_flag_open_close)
            )

        self.consolidation_period_length = len(consolidation_period)
        self.consolidation_period_max_ratio = max_ratio
        self.expected_trade_price = consolidation_period[-1].close

    def grade(self, params: Parameters) -> None:
        assert self.consolidation_period_max_ratio > 0.0
        self.score = 1.0 - max(
            0.0,
            (
                self.consolidation_period_max_ratio
                - params.consolidation_period_threshold
            )
            / params.consolidation_period_threshold,
        )
