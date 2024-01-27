import os
from datetime import datetime, timedelta

import pandas as pd
import plotly.graph_objects as go

from analysis.scripts.database_tool import DatabaseTool
from jolteon.core.side import MarketSide


class VisualizationTool:
    def __init__(self, db_tool: DatabaseTool) -> None:
        self._db_tool = db_tool

    def draw_candlesticks(self) -> go.Candlestick:
        df = self._db_tool.load_candlesticks("calculated_candlestick_feed")
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
        df = self._db_tool.load_candlesticks("calculated_candlestick_feed")
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
        df = self._db_tool.load_trades("order_fill", MarketSide.BUY)
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
        df = self._db_tool.load_trades("order_fill", MarketSide.SELL)
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
        df = self._db_tool.load_trade_result()
        if len(df) == 0:
            return []
        return [
            go.Scatter(
                x=pd.to_datetime(
                    df["opportunity.bull_flag_pattern.bull_flag.start_time"],
                    unit="s",
                ),
                y=df["opportunity.profit_price"],
                mode="markers",
                marker=dict(color="green", size=10, symbol="line-ew-open"),
                name="Profit",
            ),
            go.Scatter(
                x=pd.to_datetime(
                    df["opportunity.bull_flag_pattern.bull_flag.start_time"],
                    unit="s",
                ),
                y=df["opportunity.stop_loss_price"],
                mode="markers",
                marker=dict(color="red", size=10, symbol="line-ew-open"),
                name="Stop Loss",
            ),
        ]

    def draw_bull_flag_pattern(self) -> [go.Scatter]:
        df = self._db_tool.load_table("bull_flag")

        if len(df) == 0:
            return []
        else:
            df = df[df["result"] == "BULL_FLAG"]
            return [
                go.Scatter(
                    x=pd.to_datetime(df["bull_flag.start_time"], unit="s"),
                    y=(df["bull_flag.open"] + df["bull_flag.close"]) / 2.0,
                    mode="markers",
                    marker=dict(color="orange", size=5, symbol="x-thin-open"),
                    name="Bull Flag",
                )
            ]

    def draw_shooting_star_pattern(self) -> [go.Scatter]:
        df = self._db_tool.load_table("shooting_star")
        if len(df) == 0:
            return []
        return [
            go.Scatter(
                x=pd.to_datetime(df["shooting_star.start_time"], unit="s"),
                y=(df["shooting_star.open"] + df["shooting_star.close"]) / 2.0,
                mode="markers",
                marker=dict(color="gold", size=5, symbol="asterisk-open"),
                name="Shooting Star",
            )
        ]

    def draw_vwap(self):
        df = self._db_tool.load_market_trades()
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
        volumes = self._db_tool.load_candlesticks()["volume"]
        layout = go.Layout(
            title="Candlesticks and Trades",
            xaxis=dict(title="Date (UTC)"),
            yaxis=dict(title="Price (Dollars)", fixedrange=False),
            yaxis2=dict(
                title="Volume",
                overlaying="y",
                side="right",
                range=[0, volumes.max() * 3],
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
        opportunities = self._db_tool.load_trade_result()
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
