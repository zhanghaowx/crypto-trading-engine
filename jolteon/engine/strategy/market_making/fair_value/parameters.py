from dataclasses import dataclass

from jolteon.engine.core.parameter.parameter_specification import (
    ParameterGroup,
    parameter,
)


@dataclass(frozen=True)
class AdjustedFairPriceParameters(ParameterGroup):
    max_adjustment: float = parameter(
        5.0,
        minimum=0.0,
        maximum=10000.0,
        step=0.5,
        number_format="%.2f",
        unit="USD",
        description=(
            "The furthest the adjustments together may move the fair "
            "price. Worth keeping near the quote offset's edge, since an "
            "adjustment far smaller than the offset cannot influence a "
            "quote and one far larger can quote through it."
        ),
    )


@dataclass(frozen=True)
class MomentumParameters(ParameterGroup):
    scale: float = parameter(
        1.0,
        minimum=0.0,
        maximum=1000.0,
        step=0.1,
        number_format="%.2f",
        description="How far signed trade flow moves the fair price.",
    )
    decay: float = parameter(
        0.9,
        minimum=0.0,
        maximum=0.9999,
        step=0.01,
        number_format="%.4f",
        description=(
            "How much of the running flow each new print leaves behind. "
            "It decays per print rather than per second, so the span it "
            "covers shortens as the market trades faster."
        ),
    )
    min_trades: int = parameter(
        5,
        minimum=1,
        maximum=1000,
        step=1,
        unit="prints",
        description=(
            "How many prints must arrive before the signal is trusted. "
            "The running flow keeps accumulating regardless, so lowering "
            "this exposes a signal that is already part warmed up."
        ),
    )


@dataclass(frozen=True)
class OrderFlowImbalanceParameters(ParameterGroup):
    scale: float = parameter(
        1.0,
        minimum=0.0,
        maximum=100.0,
        step=0.1,
        number_format="%.2f",
        unit="half spreads",
        description=(
            "How far a completely one-sided book moves the fair price."
        ),
    )
    depth: int = parameter(
        10,
        minimum=1,
        maximum=100,
        step=1,
        unit="levels",
        description=(
            "How many levels a side the imbalance is measured over. The "
            "strategy's own book depth caps what is available, so raising "
            "this alone does nothing."
        ),
    )


@dataclass(frozen=True)
class InventoryAdjustmentParameters(ParameterGroup):
    skew_at_max_inventory: float = parameter(
        5.0,
        minimum=0.0,
        maximum=10000.0,
        step=0.5,
        number_format="%.2f",
        unit="USD",
        description=(
            "How far the fair price is skewed when the position has "
            "reached its cap. Stated against the cap rather than per "
            "unit, so raising the cap cannot silently leave the skew "
            "calibrated to the old one."
        ),
    )


@dataclass(frozen=True)
class MicropriceParameters(ParameterGroup):
    scale: float = parameter(
        1.0,
        minimum=0.0,
        maximum=100.0,
        step=0.1,
        number_format="%.2f",
        description=(
            "How far the size-weighted touch moves the fair price away "
            "from the mid."
        ),
    )
