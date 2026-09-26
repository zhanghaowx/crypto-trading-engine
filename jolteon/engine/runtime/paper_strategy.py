"""Compose the shared market-making strategy and its fair-price model."""

from jolteon.engine.strategy.market_making.fair_value.adjusted_model import (
    AdjustedFairPriceModel,
)
from jolteon.engine.strategy.market_making.fair_value.inventory import (
    InventoryAdjustment,
)
from jolteon.engine.strategy.market_making.fair_value.mid_price_model import (
    MidPriceFairPriceModel,
)
from jolteon.engine.strategy.market_making.fair_value.momentum import (
    MomentumAdjustment,
)
from jolteon.engine.strategy.market_making.fair_value.order_flow_imbalance import (  # noqa: E501
    OrderFlowImbalanceAdjustment,
)
from jolteon.engine.strategy.market_making.market_making_strategy import (
    MarketMakingStrategy,
)
from jolteon.engine.strategy.market_making.quote_offset import (
    FeeAwareQuoteOffsetService,
)


def paper_strategy(symbol, parameters, fee_schedule, health_monitor):
    fair = AdjustedFairPriceModel(
        base=MidPriceFairPriceModel(),
        adjustments=[
            MomentumAdjustment(parameter_service=parameters),
            OrderFlowImbalanceAdjustment(parameter_service=parameters),
            InventoryAdjustment(parameter_service=parameters),
        ],
        parameter_service=parameters,
    )
    strategy = MarketMakingStrategy(
        symbol=symbol,
        fair_price_model=fair,
        parameter_service=parameters,
        quote_offset_service=FeeAwareQuoteOffsetService(
            fee_schedule=fee_schedule, parameter_service=parameters
        ),
        health_monitor=health_monitor,
    )
    return strategy, fair
