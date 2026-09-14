from enum import StrEnum


class Market(StrEnum):
    MOCK = "MOCK"
    KRAKEN = "KRAKEN"
    BINANCE_US = "BINANCE_US"

    @staticmethod
    def parse(value: str):
        normalized = value.upper().replace(".", "_").replace("-", "_")
        try:
            return Market[normalized]
        except KeyError:
            raise RuntimeError(f"Unsupported market {value}")
