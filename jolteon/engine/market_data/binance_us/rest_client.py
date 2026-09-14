import requests


class BinanceUsPublicRestClient:
    BASE_URL = "https://api.binance.us"

    def __init__(self, session=requests):
        self._session = session

    def exchange_info(self, symbol: str) -> dict:
        response = self._session.get(
            f"{self.BASE_URL}/api/v3/exchangeInfo",
            params={"symbol": symbol, "showPermissionSets": "false"},
            timeout=10,
        )
        response.raise_for_status()
        return response.json()

    def depth(self, symbol: str, limit: int) -> dict:
        response = self._session.get(
            f"{self.BASE_URL}/api/v3/depth",
            params={"symbol": symbol, "limit": limit},
            timeout=10,
        )
        response.raise_for_status()
        return response.json()
