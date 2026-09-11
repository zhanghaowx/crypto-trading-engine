from collections.abc import Sequence
from dataclasses import dataclass, field

from jolteon.engine.core.event.signal import signal
from jolteon.engine.core.event.signal_subscriber import SignalSubscriber
from jolteon.engine.strategy.market_making.fair_value.fair_price_model import (
    FairPrice,
    FairPriceContext,
    IFairPriceModel,
)
from jolteon.engine.strategy.market_making.fair_value.price_adjustment import (
    IFairPriceAdjustment,
)


@dataclass
class FairPriceAdjustmentSnapshot:
    symbol: str
    base_fair_price: float
    total_adjustment: float
    clamped: bool
    adjustments: dict[str, float] = field(default_factory=dict)


class AdjustedFairPriceModel(IFairPriceModel, SignalSubscriber):
    """
    Wraps a base fair price model (mid-price, typically) and shifts its
    output by the sum of any number of pluggable IFairPriceAdjustments.
    With no adjustments registered, or adjustments that all return 0.0,
    this returns exactly the base model's FairPrice - so a candidate
    adjustment can be registered and observed in a live session with no
    effect on quoting until it is trusted.
    """

    def __init__(
        self,
        base: IFairPriceModel,
        adjustments: Sequence[IFairPriceAdjustment],
        max_adjustment: float | None = None,
    ):
        super().__init__()
        self._base = base
        self._adjustments = list(adjustments)
        self._max_adjustment = max_adjustment
        self.fair_price_adjustment_event = signal("fair_price_adjustment")

    def connect(self) -> None:
        # SignalManager.connect_all() only discovers SignalSubscribers that
        # are attributes of ApplicationBase directly, so a subscribing
        # adjustment held in self._adjustments needs connecting here.
        super().connect()
        for adjustment in self._adjustments:
            adjustment.connect()

    def _calculate(self, context: FairPriceContext) -> FairPrice:
        base_price = self._base.calculate(context)
        base_mid = (base_price.bid + base_price.ask) / 2

        contributions = {
            a.name: a.adjustment(context) for a in self._adjustments
        }
        total = sum(contributions.values())

        clamped = False
        if self._max_adjustment is not None:
            bounded = max(
                -self._max_adjustment, min(self._max_adjustment, total)
            )
            clamped = bounded != total
            total = bounded

        self.fair_price_adjustment_event.send(
            self.fair_price_adjustment_event,
            fair_price_adjustment=FairPriceAdjustmentSnapshot(
                symbol=context.bbo.symbol,
                base_fair_price=base_mid,
                total_adjustment=total,
                clamped=clamped,
                adjustments=contributions,
            ),
        )

        return FairPrice(
            bid=base_price.bid + total, ask=base_price.ask + total
        )
