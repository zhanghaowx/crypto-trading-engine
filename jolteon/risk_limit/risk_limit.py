from abc import ABC, abstractmethod


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
