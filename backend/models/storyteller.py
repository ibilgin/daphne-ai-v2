"""
Mistral-via-Ollama story generator — mlflow.pyfunc.PythonModel wrapper.

Input:  pd.DataFrame with columns:
          "caption"        (str)
          "style_examples" (list[str] — serialised as JSON string in DataFrame)
          "panel_count"    (int)

Output: dict {"panels": [{"panel": int, "narration": str, "dialogue": str}]}

Ollama endpoint: http://localhost:11434  (configurable via env OLLAMA_BASE_URL)
Model:           mistral (or OLLAMA_MODEL env var)

Retries up to 2× on JSON parse failure before raising.
"""

from __future__ import annotations

import json
import logging
import os
from typing import Any

import mlflow.pyfunc
import pandas as pd
import requests

logger = logging.getLogger(__name__)

DEFAULT_OLLAMA_URL = "http://localhost:11434"
DEFAULT_MODEL = "mistral"

_SYSTEM_PROMPT = (
    "You are a creative children's comic book writer. "
    "Given an image caption and optional style examples, produce exactly {panel_count} "
    "comic panels. Each panel must have a 'narration' (descriptive text) and a "
    "'dialogue' (character speech, or null if none). "
    "Respond ONLY with a JSON object matching: "
    '{"panels": [{"panel": 1, "narration": "...", "dialogue": "..."}, ...]}'
)


class StorytellerModel(mlflow.pyfunc.PythonModel):
    """
    Mistral storyteller via Ollama HTTP API, wrapped as an MLflow pyfunc model.

    load_context() reads the Ollama URL and model name from environment variables
    so that no credentials are hardcoded.
    """

    def load_context(self, context: mlflow.pyfunc.PythonModelContext) -> None:
        """Read Ollama connection settings. Called once by MLflow at serve time."""
        self.ollama_url = os.environ.get("OLLAMA_BASE_URL", DEFAULT_OLLAMA_URL)
        self.model_name = os.environ.get("OLLAMA_MODEL", DEFAULT_MODEL)
        logger.info(
            "StorytellerModel: ollama_url=%s model=%s", self.ollama_url, self.model_name
        )

    def predict(
        self, context: mlflow.pyfunc.PythonModelContext, model_input: pd.DataFrame
    ) -> dict[str, Any]:
        """
        Generate comic panels from a caption.

        Parameters
        ----------
        model_input : pd.DataFrame
            Row 0 must contain: caption (str), style_examples (list[str] or JSON str),
            panel_count (int).

        Returns
        -------
        dict
            {"panels": [{"panel": int, "narration": str, "dialogue": str}]}
        """
        required = {"caption", "style_examples", "panel_count"}
        missing = required - set(model_input.columns)
        if missing:
            raise ValueError(f"model_input missing columns: {missing}")

        row = model_input.iloc[0]
        caption: str = str(row["caption"])
        panel_count: int = int(row["panel_count"])

        # style_examples may arrive as a JSON string (DataFrame serialisation)
        style_raw = row["style_examples"]
        if isinstance(style_raw, str):
            style_examples: list[str] = json.loads(style_raw)
        else:
            style_examples = list(style_raw)

        user_prompt = self._build_prompt(caption, style_examples, panel_count)
        system_prompt = _SYSTEM_PROMPT.format(panel_count=panel_count)

        panels = self._call_ollama_with_retry(system_prompt, user_prompt, panel_count)
        return {"panels": panels}

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _build_prompt(
        self, caption: str, style_examples: list[str], panel_count: int
    ) -> str:
        lines = [f"Caption: {caption}", f"Requested panels: {panel_count}"]
        if style_examples:
            lines.append("Style examples:")
            for ex in style_examples:
                lines.append(f"  - {ex}")
        return "\n".join(lines)

    def _call_ollama_with_retry(
        self, system_prompt: str, user_prompt: str, panel_count: int, max_retries: int = 2
    ) -> list[dict]:
        """Call Ollama and retry on JSON parse failure (up to max_retries)."""
        payload = {
            "model": self.model_name,
            "format": "json",
            "stream": False,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
        }

        last_error: Exception | None = None
        for attempt in range(max_retries + 1):
            try:
                response = requests.post(
                    f"{self.ollama_url}/api/chat",
                    json=payload,
                    timeout=120,
                )
                response.raise_for_status()
                raw_content: str = response.json()["message"]["content"]
                parsed = json.loads(raw_content)
                panels = self._validate_panels(parsed, panel_count)
                return panels
            except (json.JSONDecodeError, KeyError, ValueError) as exc:
                last_error = exc
                logger.warning(
                    "StorytellerModel: attempt %d/%d failed — %s",
                    attempt + 1,
                    max_retries + 1,
                    exc,
                )

        raise RuntimeError(
            f"StorytellerModel: all {max_retries + 1} attempts failed. "
            f"Last error: {last_error}"
        )

    @staticmethod
    def _validate_panels(parsed: dict, panel_count: int) -> list[dict]:
        """Ensure the Ollama response matches the expected panel schema."""
        if "panels" not in parsed:
            raise ValueError("Response missing 'panels' key")
        panels: list = parsed["panels"]
        if not isinstance(panels, list):
            raise ValueError("'panels' must be a list")
        validated = []
        for i, p in enumerate(panels[:panel_count]):
            narration = p.get("narration")
            dialogue = p.get("dialogue")  # may be null / None
            if not isinstance(narration, str):
                raise ValueError(f"Panel {i} 'narration' must be str, got {type(narration)}")
            validated.append(
                {
                    "panel": p.get("panel", i + 1),
                    "narration": narration,
                    "dialogue": dialogue,
                }
            )
        if len(validated) < panel_count:
            raise ValueError(
                f"Expected {panel_count} panels, got {len(validated)}"
            )
        return validated


def _get_conda_env() -> dict:
    """Return minimal conda environment spec for MLflow logging."""
    return {
        "name": "storyteller-env",
        "channels": ["conda-forge", "defaults"],
        "dependencies": [
            "python=3.11",
            "pip",
            {
                "pip": [
                    "mlflow>=2.13",
                    "requests>=2.31",
                    "pandas>=2.0",
                ]
            },
        ],
    }


def log_model(run: "mlflow.ActiveRun", artifact_path: str = "storyteller") -> None:
    """Log this model to an active MLflow run."""
    mlflow.pyfunc.log_model(
        artifact_path=artifact_path,
        python_model=StorytellerModel(),
        conda_env=_get_conda_env(),
        code_path=[__file__],
    )
