import asyncio
import logging
from datetime import datetime, timedelta

import pytz
import requests

from jolteon.core.side import MarketSide
from jolteon.market_data.core.trade import Trade
from jolteon.market_data.data_source import IDataSource


class KrakenHistoricalDataSource(IDataSource):
    CACHE = dict[tuple, list[Trade]]()

    async def download_market_trades(
        self, symbol: str, start_time: datetime, end_time: datetime
    ) -> list[Trade]:
        key = (symbol, start_time, end_time)
        if self.CACHE.get(key) is not None:
            return self.CACHE[key]

        market_trades = list[Trade]()
        request_timestamp = start_time.timestamp()

        while request_timestamp < end_time.timestamp():
            # Start requesting REST API for data
            response = requests.get(
                f"https://api.kraken.com/0/public/Trades?"
                f"pair={symbol}&"
                f"since={request_timestamp}"
            )
            if response.status_code != 200:
                raise Exception(
                    f"Error getting historical market trades: "
                    f"HTTP {response.status_code}"
                )

            json_resp = response.json()
            if json_resp["error"] and len(json_resp["error"]) > 0:
                raise Exception(
                    f"Error getting historical market trades: "
                    f"{json_resp['error']}"
                )

            assert json_resp["result"] is not None
            json_trades = json_resp["result"][symbol]
            if len(json_trades) == 0:
                break  # No more trades after a certain timestamp, stop

            for json_trade in json_trades:
                # Array of trade entries
                # [
                #  <price>,
                #  <volume>,
                #  <time>,
                #  <buy/sell>,
                #  <market/limit>,
                #  <miscellaneous>,
                #  <trade_id>
                # ]
                trade = Trade(
                    trade_id=json_trade[6],
                    client_order_id="",
                    symbol=symbol,
                    maker_order_id="",
                    taker_order_id="",
                    side=MarketSide.BUY
                    if json_trade[3] == "b"
                    else MarketSide.SELL,
                    price=float(json_trade[0]),
                    quantity=float(json_trade[1]),
                    transaction_time=datetime.fromtimestamp(
                        json_trade[2], tz=pytz.utc
                    ),
                )
                if (
                    len(market_trades) == 0
                    or trade.trade_id > market_trades[-1].trade_id
                ):
                    # Don't add the same trade more than once to the list
                    market_trades.append(trade)

            last_timestamp = int(json_resp["result"]["last"]) / 1e9

            logging.info(
                f"Downloaded {len(json_trades)} historical trades "
                f"for {symbol} from "
                f"{datetime.fromtimestamp(request_timestamp, tz=pytz.utc)} to "
                f"{datetime.fromtimestamp(last_timestamp, tz=pytz.utc)}"
            )

            # Should at least advance 1 second
            request_timestamp = max(
                (
                    datetime.fromtimestamp(request_timestamp, tz=pytz.utc)
                    + timedelta(seconds=1)
                ).timestamp(),
                last_timestamp,
            )
            assert request_timestamp >= last_timestamp

            # Wait a while before making another API call to avoid errors
            await asyncio.sleep(1.0)

        # Save in the cache to reduce calls to Kraken's API
        self.CACHE[key] = market_trades
        return market_trades
