from dataclasses import dataclass

from jolteon.engine.core.parameter.parameter_specification import (
    ParameterGroup,
    parameter,
)


@dataclass(frozen=True)
class MarketMakingParameters(ParameterGroup):
    """
    What a market making strategy needs to quote: how large each quote
    is, how much inventory it may accumulate before it stops quoting on
    that side, and how far the market must move before it replaces a
    resting quote. How far from the fair price a quote sits is decided
    by an IQuoteOffsetService instead.
    """

    quote_size: float = parameter(
        0.0005,
        minimum=0.00001,
        maximum=10.0,
        step=0.0001,
        number_format="%.5f",
        unit="BTC",
        description="How much base currency each resting quote offers.",
    )
    max_inventory: float = parameter(
        0.01,
        minimum=0.00001,
        maximum=100.0,
        step=0.001,
        number_format="%.5f",
        unit="BTC",
        description=(
            "The position at which quoting stops on the side that would "
            "grow it further. Fills on the other side reopen it."
        ),
    )
    requote_tolerance: float = parameter(
        0.0,
        minimum=0.0,
        maximum=1000.0,
        step=0.5,
        number_format="%.2f",
        unit="USD",
        description=(
            "How far the desired price must move before a resting quote "
            "is cancelled and replaced. Zero replaces on every tick that "
            "moves the price at all."
        ),
    )
    book_depth: int = parameter(
        10,
        minimum=1,
        maximum=100,
        step=1,
        unit="levels",
        description=(
            "How many levels a side are handed to the fair price model. "
            "The feed's own subscription depth caps what is available."
        ),
    )


@dataclass(frozen=True)
class QuoteOffsetParameters(ParameterGroup):
    """
    How much edge a quote must earn over the fair price. Which of these
    applies depends on the offset service in use: an edge on top of the
    venue's fee, or a fixed half spread that ignores fees entirely.
    """

    edge: float = parameter(
        5.0,
        minimum=0.01,
        maximum=10000.0,
        step=0.5,
        number_format="%.2f",
        unit="USD",
        description=(
            "What a fill must earn per unit of base, on top of the fee "
            "the venue takes."
        ),
    )
    half_spread: float = parameter(
        50.0,
        minimum=0.01,
        maximum=10000.0,
        step=1.0,
        number_format="%.2f",
        unit="USD",
        description=(
            "A flat distance from the fair price on both sides, used "
            "only by the fee-blind offset service."
        ),
    )
