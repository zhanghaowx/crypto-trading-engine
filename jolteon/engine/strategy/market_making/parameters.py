from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass
class MarketMakingParameters:
    """
    The tunable parameters a market making strategy needs to quote: how
    large each quote is, and how much inventory it is allowed to
    accumulate before it stops quoting on that side. How far from the
    fair price a quote sits is decided by an IQuoteOffsetService instead.
    """

    quote_size: float
    max_inventory: float


class IParameterService(ABC):
    @abstractmethod
    def get(self, symbol: str) -> MarketMakingParameters:
        """
        Returns: The market making parameters to use for the given symbol.
        """
        raise NotImplementedError  # pragma: no cover


class StaticParameterService(IParameterService):
    """
    Simplest possible parameter service: fixed parameters, the same for
    every symbol, defaulting to conservative values suitable for paper
    trading. Intended as a starting point that can be replaced by a
    service that varies parameters per symbol or reloads them from an
    external source, without changing anything else in the strategy.
    """

    DEFAULT_QUOTE_SIZE = 0.0005
    DEFAULT_MAX_INVENTORY_IN_QUOTES = 20
    DEFAULT_MAX_INVENTORY = (
        DEFAULT_MAX_INVENTORY_IN_QUOTES * DEFAULT_QUOTE_SIZE
    )

    def __init__(
        self,
        quote_size: float = DEFAULT_QUOTE_SIZE,
        max_inventory: float = DEFAULT_MAX_INVENTORY,
    ):
        self._parameters = MarketMakingParameters(
            quote_size=quote_size,
            max_inventory=max_inventory,
        )

    def get(self, symbol: str) -> MarketMakingParameters:
        return self._parameters
