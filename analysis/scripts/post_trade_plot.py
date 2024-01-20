import sqlite3

import pandas as pd
import plotly.graph_objects as go

from jolteon.core.side import MarketSide


class PostTradePlot:
    def __init__(self, database_name: str) -> None:
        assert database_name, "Require a valid database name"
        self._conn = sqlite3.connect(database_name)

    def load_candlesticks(self, table_name: str) -> pd.DataFrame:
        assert table_name, "Require a valid table name"

        # Read candlesticks from database
        df = pd.read_sql(f"SELECT * FROM {table_name}", con=self._conn)
        df["start_time"] = pd.to_datetime(
            df["start_time"], format="%Y-%m-%d %H:%M:%S%z"
        )
        df["end_time"] = pd.to_datetime(df["end_time"], format="%Y-%m-%d %H:%M:%S%z")

        # Add VWAP column
        v = df["volume"].values
        tp = (df["low"] + df["close"] + df["high"]).div(3).values
        df = df.assign(vwap=(tp * v).cumsum() / v.cumsum())

        df.drop(columns=["index"], axis=1, inplace=True)

        return df

    def load_trades(self, table_name: str, market_side: MarketSide) -> pd.DataFrame:
        assert table_name, "Require a valid table name"

        if self.table_exists(table_name):
            # Read candlesticks from database
            df = pd.read_sql(
                f"SELECT * FROM {table_name} " f"WHERE side='{market_side.value}'",
                con=self._conn,
            )
            df["transaction_time"] = pd.to_datetime(
                df["transaction_time"], format="ISO8601"
            )
            df.drop(columns=["index"], axis=1, inplace=True)

            return df
        else:
            return pd.DataFrame()

    def load_opportunities(self):
        df = pd.read_sql("select * from trade_result", con=self._conn)
        df = df[
            [
                "opportunity.bull_flag_pattern.start",
                "opportunity.profit_price",
                "opportunity.stop_loss_price",
            ]
        ]
        df.rename(
            columns={
                "opportunity.bull_flag_pattern.start": "start",
                "opportunity.profit_price": "profit",
                "opportunity.stop_loss_price": "stop_loss",
            },
            inplace=True,
        )
        return df

    def load_bull_flag_pattern(self) -> pd.DataFrame:
        df = pd.read_sql("select * from bull_flag", con=self._conn)
        df = df[df["result"] == "BULL_FLAG"]
        return df

    def load_shooting_star_pattern(self) -> pd.DataFrame:
        df = pd.read_sql("select * from shooting_star", con=self._conn)
        return df

    def table_exists(self, table_name: str) -> bool:
        assert table_name, "Require a valid table name"

        # SQL query to check if the table exists
        query = (
            f"SELECT name FROM sqlite_master "
            f"WHERE type='table' AND name='{table_name}';"
        )

        # Execute the query
        query_result = pd.read_sql_query(query, self._conn)
        return len(query_result) > 0

    def draw_candlesticks(self) -> go.Candlestick:
        df = self.load_candlesticks("calculated_candlestick_feed")
        candlesticks_chart = go.Candlestick(
            x=df["start_time"],
            open=df["open"],
            high=df["high"],
            low=df["low"],
            close=df["close"],
            name="Candlestick",
            yaxis="y1",
        )
        return candlesticks_chart

    def draw_trade_volume(self) -> go.Bar:
        df = self.load_candlesticks("calculated_candlestick_feed")
        df["bullish"] = (df["close"] > df["open"]).astype(int)
        colors = (
            df["bullish"]
            .apply(
                lambda x: "rgba(0, 200, 0, 0.5)" if x == 1 else "rgba(200, 0, 0, 0.5)"
            )
            .to_list()
        )
        volume_bar = go.Bar(
            x=df["start_time"],
            y=df["volume"],
            marker=dict(color=colors),
            name="Volume",
            hoverinfo="skip",
            yaxis="y2",
        )
        return volume_bar

    def draw_buy_trades(self) -> go.Scatter:
        df = self.load_trades("order_fill", MarketSide.BUY)
        return go.Scatter(
            x=df["transaction_time"],
            y=df["price"],
            mode="markers",
            marker=dict(color="darkgreen", size=15, symbol="triangle-up"),
            name="Buy Orders",
        )

    def draw_sell_trades(self) -> go.Scatter:
        df = self.load_trades("order_fill", MarketSide.SELL)
        return go.Scatter(
            x=df["transaction_time"],
            y=df["price"],
            mode="markers",
            marker=dict(color="red", size=15, symbol="triangle-down"),
            name="Sell Orders",
        )

    def draw_profit_and_stop_loss(self):
        df = self.load_opportunities()
        return [
            go.Scatter(
                x=df["start"],
                y=df["profit"],
                mode="markers",
                marker=dict(color="green", size=10, symbol="line-ew-open"),
                name="Profit",
            ),
            go.Scatter(
                x=df["start"],
                y=df["stop_loss"],
                mode="markers",
                marker=dict(color="red", size=10, symbol="line-ew-open"),
                name="Stop Loss",
            ),
        ]

    def draw_bull_flag_pattern(self) -> go.Scatter:
        df = self.load_bull_flag_pattern()
        return go.Scatter(
            x=df["bull_flag.start_time"],
            y=(df["bull_flag.open"] + df["bull_flag.close"]) / 2.0,
            mode="markers",
            marker=dict(color="orange", size=5, symbol="x-thin-open"),
            name="Bull Flag",
        )

    def draw_shooting_star_pattern(self) -> go.Scatter:
        df = self.load_shooting_star_pattern()
        return go.Scatter(
            x=df["shooting_star.start_time"],
            y=(df["shooting_star.open"] + df["shooting_star.close"]) / 2.0,
            mode="markers",
            marker=dict(color="yellow", size=5, symbol="asterisk-open"),
            name="Shooting Star",
        )

    def draw_vwap(self):
        df = self.load_candlesticks("calculated_candlestick_feed")
        return go.Scatter(
            x=df["start_time"],
            y=df["vwap"],
            mode='lines',
            name='VWAP',
            line=dict(color='lightgrey', width=1, dash='dash')
        )

    def draw(self):
        layout = go.Layout(
            title="Candlesticks and Trades",
            xaxis=dict(title="Date (UTC)"),
            yaxis=dict(title="Price (Dollars)"),
            yaxis2=dict(title="Volume", overlaying="y", side="right"),
            width=2000,
            height=2000,
        )
        fig = go.Figure(
            data=[
                self.draw_candlesticks(),
                self.draw_vwap(),
                self.draw_trade_volume(),
                self.draw_buy_trades(),
                self.draw_sell_trades(),
                self.draw_bull_flag_pattern(),
                self.draw_shooting_star_pattern(),
            ]
            + self.draw_profit_and_stop_loss(),
            layout=layout,
        )
        fig.show()