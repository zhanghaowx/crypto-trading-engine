from enum import StrEnum


class MarketSide(StrEnum):
    UNKNOWN = "UNKNOWN"
    BUY = "BUY"
    SELL = "SELL"

    @staticmethod
    def parse(value: str):
        try:
            return MarketSide[value.upper()]
        except KeyError:
            return MarketSide.UNKNOWN
