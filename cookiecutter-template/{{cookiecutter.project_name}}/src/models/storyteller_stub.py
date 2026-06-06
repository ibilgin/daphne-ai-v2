"""
Storyteller model stub — mlflow.pyfunc.PythonModel interface.

Replace the `predict` body with your actual story generation logic.
Register with MLflow using:
    mlflow.pyfunc.log_model("storyteller", python_model=StorytellerModel())
"""

from __future__ import annotations

import mlflow
import pandas as pd


class StorytellerModel(mlflow.pyfunc.PythonModel):
    """Wraps a story generator as an MLflow pyfunc model.

    Input:  pd.DataFrame with columns:
              - 'caption' (str): image caption from the captioner
              - 'style'   (str): narrative style (e.g. 'adventure')
              - 'age_group' (str): target age group ('4-6', '7-9', '10-12')
    Output: pd.DataFrame with columns:
              - 'narration' (str): panel narration text
              - 'dialogue'  (str | None): speech bubble text
    """

    def load_context(self, context: mlflow.pyfunc.PythonModelContext) -> None:
        """Load model weights and RAG index from the MLflow artefact store."""
        # Example (replace with your loading logic):
        # from langchain_community.vectorstores import Chroma
        # self.vectorstore = Chroma(persist_directory=context.artifacts["chroma_dir"])
        # self.llm = ...  # load your LLM here
        pass

    def predict(
        self,
        context: mlflow.pyfunc.PythonModelContext,
        model_input: pd.DataFrame,
        params: dict | None = None,
    ) -> pd.DataFrame:
        """Generate narration and dialogue for each input caption.

        Args:
            context: MLflow context (unused after load_context).
            model_input: DataFrame with columns 'caption', 'style', 'age_group'.
            params: Optional inference parameters.

        Returns:
            DataFrame with columns 'narration' (str) and 'dialogue' (str | None).
        """
        # TODO: replace with real story generation logic
        rows = []
        for _, row in model_input.iterrows():
            caption = row["caption"]
            style = row.get("style", "adventure")
            # Generate narration and dialogue based on caption + style
            narration = f"Once upon a time, {caption}."  # Replace with LLM call
            dialogue = None  # Replace with dialogue generation
            rows.append({"narration": narration, "dialogue": dialogue})

        return pd.DataFrame(rows)
