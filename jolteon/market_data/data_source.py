import sqlite3
from abc import ABC, abstractmethod
from datetime import datetime

import pandas as pd

from jolteon.core.side import MarketSide
from jolteon.market_data.core.events import Events
from jolteon.market_data.core.trade import Trade


class IDataSource(ABC):
    @abstractmethod
    async def download_market_trades(
        self, symbol: str, start_time: datetime, end_time: datetime
    ):
        raise NotImplementedError


class DatabaseDataSource(IDataSource):
    """
    Download historical market trades from a SQLite database
    """

    def __init__(self, database_name: str):
        self._database_name = database_name
        self._table_name = Events().matches.name

    def start_time(self):
        conn = sqlite3.connect(self._database_name)
        df = pd.read_sql(
            f"select * from {self._table_name} "
            f"order by transaction_time asc limit 1",
            con=conn,
        )
        trades = self.to_trades(df)
        return trades[0].transaction_time

    def end_time(self):
        conn = sqlite3.connect(self._database_name)
        df = pd.read_sql(
            f"select * from {self._table_name} "
            f"order by transaction_time desc limit 1",
            con=conn,
        )
        trades = self.to_trades(df)
        return trades[0].transaction_time

    async def download_market_trades(
        self, symbol: str, start_time: datetime, end_time: datetime
    ):
        conn = sqlite3.connect(self._database_name)
        df = pd.read_sql(f"select * from {Events().matches.name}", con=conn)
        return self.to_trades(df)

    @staticmethod
    def to_trades(df: pd.DataFrame) -> list[Trade]:
        """
        Converts a pandas dataframe to a list of trades
        Args:
            df:

        Returns:

        """
        market_trades = list[Trade]()
        for trade_dict in df.to_dict(orient="records"):
            market_trades.append(
                Trade(
                    trade_id=trade_dict["trade_id"],
                    client_order_id=trade_dict["client_order_id"],
                    symbol=trade_dict["symbol"],
                    maker_order_id=trade_dict["maker_order_id"],
                    taker_order_id=trade_dict["taker_order_id"],
                    side=MarketSide.parse(trade_dict["side"]),
                    price=float(trade_dict["price"]),
                    quantity=float(trade_dict["quantity"]),
                    transaction_time=datetime.fromisoformat(
                        trade_dict["transaction_time"]
                    ),
                )
            )
        return market_trades
