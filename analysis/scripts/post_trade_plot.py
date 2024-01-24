import os
import sqlite3
from datetime import datetime, timedelta

import numpy as np
import pandas as pd
import plotly.graph_objects as go
from sklearn.linear_model import LinearRegression

from jolteon.core.side import MarketSide


class PostTradePlot:
    def __init__(self, database_name: str) -> None:
        assert database_name, "Require a valid database name"
        self._conn = sqlite3.connect(database_name)

    def get_summary(self):
        df = self.load_trade_result()
        # Tables
        n_bull_flag = len(self.load_bull_flag_pattern())
        n_shooting_star = len(self.load_shooting_star_pattern())

        if len(df) == 0:
            return {
                "Number of Bull Flag": n_bull_flag,
                "Number of Shooting Star": n_shooting_star,
                "Win Rate": "0%",
                "PnL": "0",
            }
        # Assume 1 trade per order
        if (
            "sell_trades.0.price" not in df.columns
            or "sell_trades.0.quantity" not in df.columns
            or "buy_trades.0.price" not in df.columns
            or "buy_trades.0.quantity" not in df.columns
        ):
            return {
                "Number of Bull Flag": n_bull_flag,
                "Number of Shooting Star": n_shooting_star,
                "Win Rate": "???%",
                "PnL": "???",
            }

        # Profit/Win Rate
        df["profit"] = (
            df["sell_trades.0.price"] * df["sell_trades.0.quantity"]
            - df["buy_trades.0.price"] * df["buy_trades.0.quantity"]
        )
        win_rate = len(df[df["profit"] > 0]) / len(df) * 100
        pnl = sum(df["profit"])
        return {
            "Number of Bull Flag": n_bull_flag,
            "Number of Shooting Star": n_shooting_star,
            "Number of Opportunities": len(df),
            "Win Rate": f"{win_rate}%",
            "PnL": pnl,
        }

    def get_volume(self):
        df = self.load_candlesticks("calculated_candlestick_feed")
        return df["volume"]

    # %% md
    def load_candlesticks(
        self, table_name: str = "calculated_candlestick_feed"
    ) -> pd.DataFrame:
        assert table_name, "Require a valid table name"

        # Read candlesticks from database
        df = pd.read_sql(f"SELECT * FROM {table_name}", con=self._conn)
        df["start_time"] = pd.to_datetime(
            df["start_time"], format="%Y-%m-%d %H:%M:%S%z"
        )
        df["end_time"] = pd.to_datetime(
            df["end_time"], format="%Y-%m-%d %H:%M:%S%z"
        )

        # Add Return Pct column
        df["return_pct"] = (df["close"] - df["open"]) / df["open"]

        # Add VWAP column
        typical_price = (df["low"] + df["close"] + df["high"]) / 3.0
        df = df.assign(
            vwap=(typical_price * df["volume"]).cumsum()
            / df["volume"].cumsum()
        )

        df.drop(columns=["index"], axis=1, inplace=True)

        return df

    def load_trades(
        self, table_name: str, market_side: MarketSide = None
    ) -> pd.DataFrame:
        assert table_name, "Require a valid table name"

        if self.table_exists(table_name):
            # Read candlesticks from database
            if market_side == None:
                df = pd.read_sql(
                    f"SELECT * FROM {table_name}",
                    con=self._conn,
                )
            else:
                df = pd.read_sql(
                    f"SELECT * FROM {table_name} WHERE side='{market_side.value}'",
                    con=self._conn,
                )
            df["transaction_time"] = pd.to_datetime(
                df["transaction_time"], format="ISO8601"
            )
            df.drop(columns=["index"], axis=1, inplace=True)

            return df
        else:
            return pd.DataFrame()

    def load_market_trades(
        self, table_name: str = "market_trade_feed"
    ) -> pd.DataFrame:
        assert table_name, "Require a valid table name"

        if self.table_exists(table_name):
            # Read candlesticks from database
            df = pd.read_sql(
                f"SELECT * FROM {table_name} ",
                con=self._conn,
            )
            df["transaction_time"] = pd.to_datetime(
                df["transaction_time"], format="ISO8601"
            )
            df = df.sort_values(by="transaction_time")
            df.drop(columns=["index"], axis=1, inplace=True)

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

    def load_bull_flag_pattern(self) -> pd.DataFrame:
        return self.load_table("bull_flag")

    def load_shooting_star_pattern(self) -> pd.DataFrame:
        return self.load_table("shooting_str")

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

    def load_table(self, table_name: str) -> pd.DataFrame:
        if not self.table_exists(table_name):
            return pd.DataFrame()

        df = pd.read_sql(f"select * from {table_name}", con=self._conn)
        return df

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
                lambda x: "rgba(0, 200, 0, 0.5)"
                if x == 1
                else "rgba(200, 0, 0, 0.5)"
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

    def draw_buy_trades(self) -> [go.Scatter]:
        df = self.load_trades("order_fill", MarketSide.BUY)
        if len(df) == 0:
            return []
        return [
            go.Scatter(
                x=df["transaction_time"],
                y=df["price"],
                mode="markers",
                marker=dict(color="darkgreen", size=15, symbol="triangle-up"),
                name="Buy Orders",
            )
        ]

    def draw_sell_trades(self) -> [go.Scatter]:
        df = self.load_trades("order_fill", MarketSide.SELL)
        if len(df) == 0:
            return []
        return [
            go.Scatter(
                x=df["transaction_time"],
                y=df["price"],
                mode="markers",
                marker=dict(color="red", size=15, symbol="triangle-down"),
                name="Sell Orders",
            )
        ]

    def draw_profit_and_stop_loss(self):
        df = self.load_trade_result()
        if len(df) == 0:
            return []
        return [
            go.Scatter(
                x=df["opportunity.bull_flag_pattern.bull_flag.start_time"],
                y=df["opportunity.profit_price"],
                mode="markers",
                marker=dict(color="green", size=10, symbol="line-ew-open"),
                name="Profit",
            ),
            go.Scatter(
                x=df["opportunity.bull_flag_pattern.bull_flag.start_time"],
                y=df["opportunity.stop_loss_price"],
                mode="markers",
                marker=dict(color="red", size=10, symbol="line-ew-open"),
                name="Stop Loss",
            ),
        ]

    def draw_bull_flag_pattern(self) -> [go.Scatter]:
        df = self.load_bull_flag_pattern()

        if len(df) == 0:
            return []
        else:
            df = df[df["result"] == "BULL_FLAG"]
            return [
                go.Scatter(
                    x=df["bull_flag.start_time"],
                    y=(df["bull_flag.open"] + df["bull_flag.close"]) / 2.0,
                    mode="markers",
                    marker=dict(color="orange", size=5, symbol="x-thin-open"),
                    name="Bull Flag",
                )
            ]

    def draw_shooting_star_pattern(self) -> [go.Scatter]:
        df = self.load_shooting_star_pattern()
        if len(df) == 0:
            return []
        return [
            go.Scatter(
                x=df["shooting_star.start_time"],
                y=(df["shooting_star.open"] + df["shooting_star.close"]) / 2.0,
                mode="markers",
                marker=dict(color="gold", size=5, symbol="asterisk-open"),
                name="Shooting Star",
            )
        ]

    def draw_vwap(self):
        df = self.load_market_trades()
        df["cumulative_cash_value"] = (df["price"] * df["quantity"]).cumsum()
        df["cumulative_quantity"] = df["quantity"].cumsum()
        df["vwap"] = df["cumulative_cash_value"] / df["cumulative_quantity"]
        return go.Scatter(
            x=df["transaction_time"],
            y=df["vwap"],
            mode="lines",
            name="VWAP",
            line=dict(color="black", width=1, dash="dash"),
        )

    def draw(self):
        layout = go.Layout(
            title="Candlesticks and Trades",
            xaxis=dict(title="Date (UTC)"),
            yaxis=dict(title="Price (Dollars)", fixedrange=False),
            yaxis2=dict(
                title="Volume",
                overlaying="y",
                side="right",
                range=[0, self.get_volume().max() * 3],
            ),
            width=2000,
            height=800,
        )
        fig = go.Figure(
            data=[
                self.draw_candlesticks(),
                self.draw_vwap(),
                self.draw_trade_volume(),
            ]
            + self.draw_profit_and_stop_loss()
            + self.draw_buy_trades()
            + self.draw_sell_trades()
            + self.draw_bull_flag_pattern()
            + self.draw_shooting_star_pattern(),
            layout=layout,
        )
        return fig

    def save_draw(self):
        fig = self.draw()
        opportunities = self.load_trade_result()
        for i in range(0, len(opportunities)):
            opportunity = opportunities.iloc[i]
            fig.update_xaxes(
                range=[
                    datetime.fromisoformat(
                        opportunity["opportunity.bull_flag_pattern.start"]
                    )
                    - timedelta(minutes=10),
                    datetime.fromisoformat(
                        opportunity["opportunity.bull_flag_pattern.end"]
                    )
                    + timedelta(minutes=10),
                ]
            )
            min_y = min(
                opportunity["buy_trades.0.price"],
                opportunity["sell_trades.0.price"],
                opportunity["opportunity.stop_loss_price"],
            )
            max_y = max(
                opportunity["buy_trades.0.price"],
                opportunity["sell_trades.0.price"],
                opportunity["opportunity.profit_price"],
            )
            fig.update_yaxes(
                range=[
                    min_y
                    - opportunity[
                        "opportunity.bull_flag_pattern.bull_flag_body"
                    ]
                    * 2,
                    max_y
                    + opportunity[
                        "opportunity.bull_flag_pattern.bull_flag_body"
                    ]
                    * 2,
                ]
            )

            if opportunity["profit"] > 0:
                directory_path = "/tmp/analysis/profit"
                if not os.path.exists(directory_path):
                    os.makedirs(directory_path)
                fig.write_image(f"{directory_path}/trade_{i}.png")
            else:
                directory_path = "/tmp/analysis/loss"
                if not os.path.exists(directory_path):
                    os.makedirs(directory_path)
                fig.write_image(f"{directory_path}/trade_{i}.png")

    def predict(self, predict_cutoff: float, drop_columns: list[str]):
        """
        Use linear regression model trying to predict whether
        an opportunity will profit

        Suggestion:
        Run a replay with the lowest opportunity score cut off to collect as
        much data as possible. Also consider running a multi day test instead
        of one single day.

        All data much be prepared inside "score_details" of the
        TradeOpportunity class. User has to make sure there is no strong
        correlation between features in "score_details"

        Returns:
        """
        df = self.load_trade_result()
        if len(df) == 0:
            return

        score_details = [
            col for col in df if col.startswith("opportunity.score_details")
        ]
        train_df = df[score_details].copy()
        train_df["is_profit"] = (df["profit"] > 0).astype(int)

        if len(drop_columns) > 0:
            train_df = train_df.drop(columns=drop_columns)
        # Find strong correlations above the threshold

        strong_correlation_threshold = 0.75
        correlation_matrix = train_df.corr()
        strong_correlations = (
            correlation_matrix.abs() > strong_correlation_threshold
        ) & (correlation_matrix < 1)

        # Print out the pairs with strong correlations
        if strong_correlations.any().any():
            print("WARNING: Strong Correlation:")

        for col in strong_correlations.columns:
            correlated_cols = strong_correlations.index[
                strong_correlations[col]
            ].tolist()
            for correlated_col in correlated_cols:
                correlation_value = correlation_matrix.loc[correlated_col, col]
                print(
                    f"  * {col} and {correlated_col}: "
                    f"{correlation_value:.2f}"
                )

        y = "is_profit"
        X = [x for x in train_df.columns if x != y]
        model = LinearRegression()
        model.fit(train_df[X], train_df[y])

        # Extract coefficients, intercept, and feature names
        coefficients = model.coef_
        intercept = model.intercept_
        feature_names = train_df[X].columns

        # Round coefficients and intercept to 0.01
        coefficients_rounded = np.round(coefficients, decimals=3)
        intercept_rounded = round(intercept, 3)

        # Print out the equation with rounded values
        equation = f"y = {intercept_rounded}"
        for i in range(0, len(feature_names)):
            equation += f" + {coefficients_rounded[i]} * {feature_names[i]}"
        print("Linear Regression Equation:")
        print(equation)

        # Combine train_df with predict
        train_df["predict"] = model.predict(train_df[X])

        # Print new win rate after prediction
        final = train_df[train_df["predict"] > predict_cutoff]
        win_rate = len(final[final["is_profit"] > 0]) / len(final)
        print(f"Win Rate (After Prediction Cutoff): {win_rate:.2f}")

        return train_df
