"""
BLIP-2 image captioner — mlflow.pyfunc.PythonModel wrapper.

Input:  pd.DataFrame with column "image_bytes" (base64-encoded PNG/JPEG str)
Output: dict {"caption": str, "latency_ms": float}

Child data privacy: image bytes are never persisted to disk or DB.
Only SHA-256 hashes are written to the audit log.
"""

from __future__ import annotations

import base64
import hashlib
import io
import logging
import time
from typing import Any

import mlflow.pyfunc
import pandas as pd

logger = logging.getLogger(__name__)

# Blocked words — must not appear in generated captions
BLOCKED_WORDS: list[str] = [
    "violent",
    "blood",
    "weapon",
    "gun",
    "knife",
    "nude",
    "naked",
    "sexual",
    "adult",
    "gore",
]

MODEL_NAME = "salesforce/blip-image-captioning-base"


class CaptionerModel(mlflow.pyfunc.PythonModel):
    """
    BLIP image captioner wrapped as an MLflow pyfunc model.

    load_context() downloads the HuggingFace model once and stores processor
    and model on self.  CPU is always available; MPS (Apple Silicon) is used
    when available.
    """

    def load_context(self, context: mlflow.pyfunc.PythonModelContext) -> None:
        """Load BLIP processor and model. Called once by MLflow at serve time."""
        import torch
        from PIL import Image  # noqa: F401 — validates pillow is importable
        from transformers import BlipForConditionalGeneration, BlipProcessor

        # Device selection: MPS > CPU
        if torch.backends.mps.is_available():
            self.device = "mps"
        else:
            self.device = "cpu"

        logger.info("CaptionerModel: loading %s on device=%s", MODEL_NAME, self.device)

        self.processor = BlipProcessor.from_pretrained(MODEL_NAME)
        self.model = BlipForConditionalGeneration.from_pretrained(MODEL_NAME).to(
            self.device
        )
        self.model.eval()
        logger.info("CaptionerModel: model loaded successfully")

    def predict(
        self, context: mlflow.pyfunc.PythonModelContext, model_input: pd.DataFrame
    ) -> dict[str, Any]:
        """
        Generate a caption for a single image.

        Parameters
        ----------
        model_input : pd.DataFrame
            Must contain column "image_bytes" with a single base64-encoded image string.

        Returns
        -------
        dict
            {"caption": str, "latency_ms": float}
        """
        import torch
        from PIL import Image

        if "image_bytes" not in model_input.columns:
            raise ValueError("model_input must contain column 'image_bytes'")

        row = model_input.iloc[0]
        image_b64: str = row["image_bytes"]

        # Audit: log SHA-256 hash only — never log raw bytes
        img_hash = hashlib.sha256(image_b64.encode()).hexdigest()
        logger.debug("CaptionerModel.predict: image_hash=%s", img_hash)

        # Decode base64 → PIL Image
        img_bytes = base64.b64decode(image_b64)
        image = Image.open(io.BytesIO(img_bytes)).convert("RGB")

        t0 = time.perf_counter()

        inputs = self.processor(images=image, return_tensors="pt").to(self.device)
        with torch.no_grad():
            output_ids = self.model.generate(**inputs, max_new_tokens=50)

        caption: str = self.processor.decode(output_ids[0], skip_special_tokens=True)
        latency_ms = (time.perf_counter() - t0) * 1000.0

        logger.info(
            "CaptionerModel.predict: caption=%r latency_ms=%.1f", caption, latency_ms
        )

        return {"caption": caption, "latency_ms": latency_ms}


def _get_conda_env() -> dict:
    """Return minimal conda environment spec for MLflow logging."""
    return {
        "name": "captioner-env",
        "channels": ["conda-forge", "defaults"],
        "dependencies": [
            "python=3.11",
            "pip",
            {
                "pip": [
                    "mlflow>=2.13",
                    "transformers>=4.40",
                    "torch>=2.2",
                    "Pillow>=10.0",
                    "pandas>=2.0",
                    "accelerate>=0.27",
                ]
            },
        ],
    }


def log_model(run: "mlflow.ActiveRun", artifact_path: str = "captioner") -> None:
    """Log this model to an active MLflow run."""
    mlflow.pyfunc.log_model(
        artifact_path=artifact_path,
        python_model=CaptionerModel(),
        conda_env=_get_conda_env(),
        code_path=[__file__],
    )
