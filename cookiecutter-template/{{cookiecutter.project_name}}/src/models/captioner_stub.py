"""
Captioner model stub — mlflow.pyfunc.PythonModel interface.

Replace the `predict` body with your actual image captioning logic.
Register with MLflow using:
    mlflow.pyfunc.log_model("captioner", python_model=CaptionerModel())
"""

from __future__ import annotations

import mlflow
import pandas as pd


class CaptionerModel(mlflow.pyfunc.PythonModel):
    """Wraps an image captioner as an MLflow pyfunc model.

    Input:  pd.DataFrame with a column 'image_bytes' (bytes, PNG/JPEG).
    Output: pd.DataFrame with a column 'caption' (str).
    """

    def load_context(self, context: mlflow.pyfunc.PythonModelContext) -> None:
        """Load model weights from the MLflow artefact store."""
        # Example (replace with your model loading logic):
        # import torch
        # from transformers import Blip2Processor, Blip2ForConditionalGeneration
        # self.processor = Blip2Processor.from_pretrained(context.artifacts["model_dir"])
        # self.model = Blip2ForConditionalGeneration.from_pretrained(context.artifacts["model_dir"])
        pass

    def predict(
        self,
        context: mlflow.pyfunc.PythonModelContext,
        model_input: pd.DataFrame,
        params: dict | None = None,
    ) -> pd.DataFrame:
        """Generate a caption for each input image.

        Args:
            context: MLflow context (unused after load_context).
            model_input: DataFrame with column 'image_bytes' (bytes).
            params: Optional inference parameters.

        Returns:
            DataFrame with column 'caption' (str).
        """
        # TODO: replace with real captioning logic
        captions = []
        for image_bytes in model_input["image_bytes"]:
            caption = "a colourful drawing"  # Replace with model inference
            captions.append(caption)

        return pd.DataFrame({"caption": captions})
