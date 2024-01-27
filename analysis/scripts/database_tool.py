import sqlite3

import pandas as pd

from jolteon.core.side import MarketSide


class DatabaseTool:
    def __init__(self, database_name: str) -> None:
        assert database_name, "Require a valid database name"
        self._conn = sqlite3.connect(database_name)

    def table_exists(self, table_name: str) -> bool:
        """
        Whether the given table name exists in the database
        Args:
            table_name: The name of the table
        Returns:
            True if the table exists, False otherwise

        """
        assert table_name, "Require a valid table name"

        # SQL query to check if the table exists
        query = (
            f"SELECT name FROM sqlite_master "
            f"WHERE type='table' AND name='{table_name}';"
        )

        # Execute the query
        query_result = pd.read_sql_query(query, self._conn)
        return len(query_result) > 0

    def load_table(self, table_name: str) -> pd.DataFrame:
        """
        Load the given table into a DataFrame
        Args:
            table_name: The name of the table
        Returns:
            True if the table exists, False otherwise
        """
        if not self.table_exists(table_name):
            return pd.DataFrame()

        df = pd.read_sql(f"select * from {table_name}", con=self._conn)
        return df

    def load_candlesticks(
        self, table_name: str = "calculated_candlestick_feed"
    ) -> pd.DataFrame:
        assert table_name, "Require a valid table name"

        # Read candlesticks from database
        df = self.load_table(table_name)

        df["start_time"] = pd.to_datetime(df["start_time"], unit="s")
        df["end_time"] = pd.to_datetime(df["end_time"], unit="s")

        # Add Return Pct column
        df["return_pct"] = (df["close"] - df["open"]) / df["open"]

        # Add VWAP column
        typical_price = (df["low"] + df["close"] + df["high"]) / 3.0
        df = df.assign(
            vwap=(typical_price * df["volume"]).cumsum()
            / df["volume"].cumsum()
        )

        return df

    def load_trades(
        self, table_name: str = "order_fill", market_side: MarketSide = None
    ) -> pd.DataFrame:
        assert table_name, "Require a valid table name"

        if self.table_exists(table_name):
            # Read candlesticks from database
            if not market_side:
                df = pd.read_sql(
                    f"SELECT * FROM {table_name}",
                    con=self._conn,
                )
            else:
                df = pd.read_sql(
                    f"SELECT * FROM {table_name} "
                    f"WHERE side='{market_side.value}'",
                    con=self._conn,
                )
            df["transaction_time"] = pd.to_datetime(
                df["transaction_time"], unit="s"
            )

            return df
        else:
            return pd.DataFrame()

    def load_market_trades(
        self, table_name: str = "market_trade_feed"
    ) -> pd.DataFrame:
        assert table_name, "Require a valid table name"

        if self.table_exists(table_name):
            # Read candlesticks from database
            df = self.load_table(table_name)
            if len(df) == 0:
                return pd.DataFrame()

            df["transaction_time"] = pd.to_datetime(
                df["transaction_time"], unit="s"
            )
            df = df.sort_values(by="transaction_time")

            return df
        else:
            return pd.DataFrame()

    def load_trade_result(self, table_name="bull_trend_rider_trade_result"):
        df = self.load_table(table_name)
        if len(df) == 0:
            return pd.DataFrame()

        df["profit"] = (
            df["sell_trades.0.price"] * df["sell_trades.0.quantity"]
            - df["buy_trades.0.price"] * df["buy_trades.0.quantity"]
        )
        return df
