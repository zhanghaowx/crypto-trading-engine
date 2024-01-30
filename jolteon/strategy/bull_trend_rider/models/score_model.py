import os

import joblib
import pandas as pd


class ScoreModel:
    """
    Loads a model file for scoring an opportunity
    """

    def __init__(self, model_name: str):
        # Load the model file into class
        script_directory = os.path.dirname(os.path.abspath(__file__))
        self._model = joblib.load(f"{script_directory}/{model_name}")

    def score(self, score_details: dict):
        """
        Generates a score based on the model file

        Args:
            score_details:
        Returns:

        """
        X_predict = pd.DataFrame([score_details])
        y_predict = self._model.predict(X_predict)
        return y_predict[0]


def score_model(instance=ScoreModel("random_forest_model-2024-01-29.joblib")):
    return instance
