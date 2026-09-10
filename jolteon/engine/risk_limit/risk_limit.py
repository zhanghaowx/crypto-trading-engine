from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass
class RiskLimitLevel:
    """
    Point-in-time reading of how close a named risk limit is to being hit.
    Emitted as a signal so it can be recorded and displayed alongside every
    other event the engine produces, e.g. on a live dashboard.
    """

    name: str
    symbol: str
    current: float
    maximum: float


class IRiskLimit(ABC):
    @abstractmethod
    def can_send(self) -> bool:
        """
        Returns: Whether an order could be sent out or it would be prohibited
                 by this limit
        """
        raise NotImplementedError  # pragma: no cover

    @abstractmethod
    def do_send(self) -> bool:
        """
        Returns: Update this limit before actually sending out the order
        """
        raise NotImplementedError  # pragma: no cover
