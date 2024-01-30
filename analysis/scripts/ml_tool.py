import os
from datetime import datetime
from typing import Literal

import joblib
import pandas as pd
from sklearn.ensemble import RandomForestClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import confusion_matrix
from sklearn.model_selection import GridSearchCV

from analysis.scripts.database_tool import DatabaseTool


class MLTool(object):
    def __init__(self, db_tool: DatabaseTool) -> None:
        self._db_tool = db_tool

    def get_summary(self):
        df = self._db_tool.load_trade_result()
        # Tables
        n_bull_flag = len(self._db_tool.load_table("bull_flag"))
        n_shooting_star = len(self._db_tool.load_table("shooting_str"))

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
            - df["buy_trades.0.fee"]
            - df["sell_trades.0.fee"]
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

    def train(
        self,
        method: Literal["random_forest", "linear"],
        drop_columns: list[str],
    ):
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
        df = self._db_tool.load_trade_result()
        if len(df) == 0:
            return

        train_df = self.wrangle(df, drop_columns)
        self._check_strong_correlation(train_df)

        # ----- Start training -----#
        if method == "random_forest":
            (best_model, cm) = self.train_random_forest_model(train_df)
        elif method == "linear":
            (best_model, cm) = self.train_linear_model(train_df)
        else:
            raise NotImplementedError(f"Unknown method: {method}")

        # ----- Save result -----#
        self._save_model(best_model)

        return (best_model, cm)

    @staticmethod
    def predict(database_name: str, model: object, drop_columns: list[str]):
        """
        Load opportunities from another run and use the specified model to
        predict whether an opportunity is profitable or not
        """
        db_tool = DatabaseTool(database_name)
        test_trade_result = db_tool.load_trade_result()
        test_df = MLTool.wrangle(test_trade_result, drop_columns=[])
        test_df["prediction"] = model.predict(
            test_df.drop(columns=["is_profit"])
        )
        test_df["profit"] = test_trade_result["profit"]

        predict_profit_df = test_df[test_df["prediction"] > 0]
        predict_profit_accuracy = len(
            predict_profit_df[predict_profit_df["profit"] > 0]
        ) / len(predict_profit_df)

        base_line = len(test_df[test_df["profit"] > 0]) / len(test_df)

        print(f"Base Line: {base_line * 100:.2f}% ({len(test_df)})")
        print(
            f"Model Accuracy: {predict_profit_accuracy * 100:.2f}% "
            f"({len(predict_profit_df)})"
        )

        return test_df

    @staticmethod
    def wrangle(df, drop_columns=None):
        # ----- Prepare the training data -----#
        if drop_columns is None:
            drop_columns = []
        score_details = [
            col for col in df if col.startswith("opportunity.score_details.")
        ]
        train_df = df[score_details].copy()
        train_df = train_df.rename(
            columns=lambda x: x.replace("opportunity.score_details.", "")
        )
        train_df["is_profit"] = (df["profit"] > 0).astype(int)
        if len(drop_columns) > 0:
            train_df = train_df.drop(columns=drop_columns)
        return train_df

    @staticmethod
    def train_random_forest_model(train_df):
        y = "is_profit"
        X = [x for x in train_df.columns if x != y]
        print(f"Features: {X}")
        print(f"X: {train_df[X].shape}")
        print(f"y: {train_df[y].shape}")
        # Use grid search to find the best hyperparameters
        model = RandomForestClassifier()
        grid_search = GridSearchCV(
            model,
            param_grid={
                "n_estimators": range(1, 100),
                "max_depth": range(1, len(X) * 2),
            },
        )
        grid_search.fit(train_df[X], train_df[y])
        print("Best hyperparameters:", grid_search.best_params_)

        # Combine train_df with predict
        train_df["predict"] = grid_search.predict(train_df[X])

        # Print new win rate after prediction
        MLTool._check_prediction(train_df)

        cm = confusion_matrix(train_df[y], train_df["predict"])
        return grid_search.best_estimator_, cm

    @staticmethod
    def train_linear_model(train_df):
        y = "is_profit"
        X = [x for x in train_df.columns if x != y]
        print(f"Features: {X}")
        print(f"X: {train_df[X].shape}")
        print(f"y: {train_df[y].shape}")

        model = LogisticRegression()
        model.fit(train_df[X], train_df[y])

        # Combine train_df with predict
        train_df["predict"] = model.predict(train_df[X])

        # Print new win rate after prediction
        MLTool._check_prediction(train_df)

        cm = confusion_matrix(train_df[y], train_df["predict"])
        return model, cm

    @staticmethod
    def _save_model(best_model):
        script_directory = os.path.dirname(os.path.abspath(__file__))
        repo_directory = os.path.dirname(os.path.dirname(script_directory))
        model_filename = (
            f"random_forest_model-{datetime.now().strftime('%Y-%m-%d')}.joblib"
        )
        save_path = (
            f"{repo_directory}/jolteon/strategy/bull_trend_rider/"
            f"models/{model_filename}"
        )
        joblib.dump(best_model, save_path)
        print(f"Saved model to {save_path}")
        return best_model

    @staticmethod
    def _check_strong_correlation(
        train_df: pd.DataFrame, threshold: float = 0.75
    ):
        # Find strong correlations above the threshold and warn users
        correlation_matrix = train_df.corr()
        strong_correlations = (correlation_matrix.abs() > threshold) & (
            correlation_matrix < 1
        )

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

    @staticmethod
    def _check_prediction(train_df):
        final = train_df[train_df["predict"] == 1]
        success_count = len(final[final["is_profit"] > 0])
        total_count = len(final)
        win_rate = success_count / max(1e-10, total_count)
        print(
            f"Win Rate (After Prediction Cutoff): {win_rate * 100:.2f}% "
            f"with {success_count}/{total_count} opportunities"
        )
