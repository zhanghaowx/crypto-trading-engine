import logging
import os
from datetime import datetime

from coinbase.rest import RESTClient

from jolteon.core.id_generator import id_generator
from jolteon.core.side import MarketSide
from jolteon.core.time.time_range import TimeRange
from jolteon.market_data.core.trade import Trade
from jolteon.market_data.data_source import IDataSource


class CoinbaseHistoricalDataSource(IDataSource):
    def __init__(self):
        self._client = RESTClient(
            api_key=os.getenv("COINBASE_API_KEY"),
            api_secret=os.getenv("COINBASE_API_SECRET"),
        )

    async def download_market_trades(
        self, symbol: str, start_time: datetime, end_time: datetime
    ):
        key = (symbol, start_time, end_time)
        if self.TRADE_CACHE.get(key) is not None:
            return self.TRADE_CACHE[key]
        market_trades = list[Trade]()

        # Begin download
        time_range = TimeRange(start_time, end_time)
        for period in time_range.generate_time_ranges(interval_in_minutes=1):
            new_trades = self._download(symbol, period.start, period.end)
            market_trades = market_trades + new_trades

        # Save in the cache to reduce calls to Coinbase API
        self.TRADE_CACHE[key] = market_trades
        return market_trades

    def _download(
        self, symbol: str, start_time: datetime, end_time: datetime
    ) -> list[Trade]:
        # Get snapshot information, by product ID, about the last trades
        # (ticks), best bid/ask, and 24h volume.
        max_number_of_trades_limit = 1000
        json_response = self._client.get_market_trades(
            product_id=symbol,
            start=int(start_time.timestamp()),
            end=int(end_time.timestamp()),
            limit=max_number_of_trades_limit,
        )
        assert "trades" in json_response

        market_trades = list[Trade]()
        for trade_json in json_response["trades"]:
            try:
                trade = Trade(
                    trade_id=id_generator().next(),
                    symbol=trade_json["product_id"],
                    client_order_id="",
                    maker_order_id="",
                    taker_order_id="",
                    side=MarketSide.parse(trade_json["side"]),
                    price=float(trade_json["price"]),
                    fee=0.0,
                    quantity=float(trade_json["size"]),
                    transaction_time=datetime.fromisoformat(
                        trade_json["time"]
                    ),
                )
                market_trades.append(trade)
            except Exception as e:
                logging.error(
                    f"Could not parse market trade '{trade_json}': {e}",
                    exc_info=True,
                )
                continue  # Try next trade in the JSON response

        market_trades.sort(key=lambda x: x.transaction_time)
        if (
            len(market_trades) == max_number_of_trades_limit
            and market_trades[-1].transaction_time < end_time
        ):
            logging.warning(
                f"Max number of trades ({len(market_trades)}) "
                f"returned for {start_time} - {end_time}, "
                f"first trade at {market_trades[0].transaction_time}. "
                f"last trade at {market_trades[-1].transaction_time}. "
                f"Consider using a time range smaller than "
                f"{int((end_time - start_time).total_seconds() / 60)} minutes "
                f"when downloading historical market trades!"
            )

        return market_trades
