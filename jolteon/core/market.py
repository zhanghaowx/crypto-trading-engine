from enum import StrEnum


class Market(StrEnum):
    MOCK = "MOCK"
    COINBASE = "COINBASE"
    KRAKEN = "KRAKEN"

    @staticmethod
    def parse(value: str):
        try:
            return Market[value.upper()]
        except KeyError:
            raise RuntimeError(f"Unsupported market {value}")
