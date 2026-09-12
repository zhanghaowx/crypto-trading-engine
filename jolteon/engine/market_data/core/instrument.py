from dataclasses import dataclass


@dataclass(frozen=True)
class InstrumentSpec:
    """
    What a venue will accept for one symbol: how finely a price may be
    expressed, and how small an order may be.

    An order breaking one of these is not mispriced so much as
    unsendable. The venue refuses it outright, which from the engine's
    side looks like an order that simply never appeared, so a quote is
    worth checking against these before it is sent rather than after.

    Every limit defaults to zero, meaning unstated. A symbol the venue
    has said nothing about is therefore unconstrained, which is what a
    replay or a test gets: it quotes as it did before any of this
    existed instead of refusing to quote at all.
    """

    PRIMARY_KEY = "symbol"

    symbol: str
    base: str = ""
    quote: str = ""
    price_precision: int = 0
    qty_precision: int = 0
    price_increment: float = 0.0
    qty_min: float = 0.0
    cost_min: float = 0.0

    def round_price(self, price: float) -> float:
        """
        Returns: The nearest price the venue will quote at.

        Rounded to the declared precision as well as the increment, since
        dividing by a decimal increment leaves float dust that the venue
        reads as too many decimal places.
        """
        if self.price_increment <= 0.0:
            return price
        return round(
            round(price / self.price_increment) * self.price_increment,
            self.price_precision,
        )

    def rejects(self, quantity: float, price: float) -> str | None:
        """
        Returns: Why the venue would refuse an order of this size, or
        None if it would accept it.

        A reason rather than a yes or no, because a caller that cannot
        quote can only usefully report which limit it broke.
        """
        if quantity < self.qty_min:
            return (
                f"quote size {quantity} is below {self.symbol}'s minimum "
                f"order size of {self.qty_min}"
            )
        if quantity * price < self.cost_min:
            return (
                f"quote notional {quantity * price:.4f} is below "
                f"{self.symbol}'s minimum of {self.cost_min}"
            )
        return None
