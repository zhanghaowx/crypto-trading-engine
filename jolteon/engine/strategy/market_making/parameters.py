from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass
class MarketMakingParameters:
    """
    The tunable parameters a market making strategy needs to quote: how
    large each quote is, how far from the fair price it sits, and how
    much inventory it is allowed to accumulate before it stops quoting
    on that side.
    """

    quote_size: float
    half_spread: float
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
    DEFAULT_HALF_SPREAD = 5.0
    DEFAULT_MAX_INVENTORY = 0.002

    def __init__(
        self,
        quote_size: float = DEFAULT_QUOTE_SIZE,
        half_spread: float = DEFAULT_HALF_SPREAD,
        max_inventory: float = DEFAULT_MAX_INVENTORY,
    ):
        self._parameters = MarketMakingParameters(
            quote_size=quote_size,
            half_spread=half_spread,
            max_inventory=max_inventory,
        )

    def get(self, symbol: str) -> MarketMakingParameters:
        return self._parameters
