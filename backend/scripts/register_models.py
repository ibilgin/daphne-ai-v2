"""
Register both Captioner and Storyteller models into the MLflow model registry.

Tags applied to every registered version:
  - dataset_hash : SHA-256 of the training/evaluation dataset manifest
  - eval_date    : ISO-8601 date of registration
  - model_type   : "captioner" | "storyteller"

Initial aliases:
  - New versions receive the "Staging" alias.
  - If a Production alias already exists it is NOT overwritten — use
    quality_gate.py to promote from Staging → Production.

Usage:
    python backend/scripts/register_models.py

Environment variables:
    MLFLOW_TRACKING_URI        (default: http://localhost:5001)
    MLFLOW_S3_ENDPOINT_URL     (default: http://localhost:9000)
    AWS_ACCESS_KEY_ID          (default: minioadmin)
    AWS_SECRET_ACCESS_KEY      (default: minioadmin)
    DATASET_HASH               (default: computed from fixture manifest)
"""

from __future__ import annotations

import hashlib
import logging
import os
import sys
from datetime import date
from pathlib import Path

import mlflow
import mlflow.pyfunc

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Configuration — all overridable via environment
# ---------------------------------------------------------------------------
MLFLOW_TRACKING_URI = os.environ.get("MLFLOW_TRACKING_URI", "http://localhost:5001")
MLFLOW_S3_ENDPOINT_URL = os.environ.get("MLFLOW_S3_ENDPOINT_URL", "http://localhost:9000")
AWS_ACCESS_KEY_ID = os.environ.get("AWS_ACCESS_KEY_ID", "minioadmin")
AWS_SECRET_ACCESS_KEY = os.environ.get("AWS_SECRET_ACCESS_KEY", "minioadmin")

CAPTIONER_REGISTERED_NAME = "sketch-to-story-captioner"
STORYTELLER_REGISTERED_NAME = "sketch-to-story-storyteller"
STAGING_ALIAS = "Staging"

# Paths relative to this script
BACKEND_DIR = Path(__file__).parents[1]
FIXTURES_DIR = BACKEND_DIR.parent / "tests" / "fixtures"


def _compute_dataset_hash() -> str:
    """
    Return a SHA-256 fingerprint of the fixture image manifest.
    Only file names and sizes are hashed — never raw image bytes.
    """
    env_hash = os.environ.get("DATASET_HASH")
    if env_hash:
        return env_hash

    manifest = []
    if FIXTURES_DIR.exists():
        for p in sorted(FIXTURES_DIR.iterdir()):
            if p.suffix.lower() in {".png", ".jpg", ".jpeg"}:
                manifest.append(f"{p.name}:{p.stat().st_size}")
    manifest_str = "\n".join(manifest) or "empty-fixture-set"
    return hashlib.sha256(manifest_str.encode()).hexdigest()[:16]


def _setup_env() -> None:
    os.environ.setdefault("MLFLOW_S3_ENDPOINT_URL", MLFLOW_S3_ENDPOINT_URL)
    os.environ.setdefault("AWS_ACCESS_KEY_ID", AWS_ACCESS_KEY_ID)
    os.environ.setdefault("AWS_SECRET_ACCESS_KEY", AWS_SECRET_ACCESS_KEY)
    mlflow.set_tracking_uri(MLFLOW_TRACKING_URI)


def register_captioner(dataset_hash: str, eval_date: str) -> str:
    """Log and register the CaptionerModel. Returns the new version string."""
    sys.path.insert(0, str(BACKEND_DIR))
    from models.captioner import CaptionerModel, _get_conda_env

    with mlflow.start_run(run_name="register-captioner") as run:
        mlflow.log_param("model_name", "salesforce/blip-image-captioning-base")
        mlflow.log_param("device", "mps-or-cpu")

        mlflow.pyfunc.log_model(
            artifact_path="captioner",
            python_model=CaptionerModel(),
            conda_env=_get_conda_env(),
            code_path=[str(BACKEND_DIR / "models" / "captioner.py")],
        )

        model_uri = f"runs:/{run.info.run_id}/captioner"

    logger.info("Registering captioner from run %s", run.info.run_id)
    mv = mlflow.register_model(
        model_uri=model_uri,
        name=CAPTIONER_REGISTERED_NAME,
        tags={
            "dataset_hash": dataset_hash,
            "eval_date": eval_date,
            "model_type": "captioner",
        },
    )

    client = mlflow.tracking.MlflowClient()
    client.set_registered_model_alias(
        name=CAPTIONER_REGISTERED_NAME,
        alias=STAGING_ALIAS,
        version=mv.version,
    )
    logger.info(
        "Captioner v%s registered with alias '%s'", mv.version, STAGING_ALIAS
    )
    return mv.version


def register_storyteller(dataset_hash: str, eval_date: str) -> str:
    """Log and register the StorytellerModel. Returns the new version string."""
    sys.path.insert(0, str(BACKEND_DIR))
    from models.storyteller import StorytellerModel, _get_conda_env

    with mlflow.start_run(run_name="register-storyteller") as run:
        mlflow.log_param("ollama_model", os.environ.get("OLLAMA_MODEL", "mistral"))
        mlflow.log_param("ollama_url", os.environ.get("OLLAMA_BASE_URL", "http://localhost:11434"))

        mlflow.pyfunc.log_model(
            artifact_path="storyteller",
            python_model=StorytellerModel(),
            conda_env=_get_conda_env(),
            code_path=[str(BACKEND_DIR / "models" / "storyteller.py")],
        )

        model_uri = f"runs:/{run.info.run_id}/storyteller"

    logger.info("Registering storyteller from run %s", run.info.run_id)
    mv = mlflow.register_model(
        model_uri=model_uri,
        name=STORYTELLER_REGISTERED_NAME,
        tags={
            "dataset_hash": dataset_hash,
            "eval_date": eval_date,
            "model_type": "storyteller",
        },
    )

    client = mlflow.tracking.MlflowClient()
    client.set_registered_model_alias(
        name=STORYTELLER_REGISTERED_NAME,
        alias=STAGING_ALIAS,
        version=mv.version,
    )
    logger.info(
        "Storyteller v%s registered with alias '%s'", mv.version, STAGING_ALIAS
    )
    return mv.version


def main() -> None:
    _setup_env()

    dataset_hash = _compute_dataset_hash()
    eval_date = date.today().isoformat()

    logger.info(
        "Starting model registration  dataset_hash=%s  eval_date=%s",
        dataset_hash,
        eval_date,
    )

    captioner_version = register_captioner(dataset_hash, eval_date)
    storyteller_version = register_storyteller(dataset_hash, eval_date)

    logger.info(
        "Registration complete — captioner v%s, storyteller v%s",
        captioner_version,
        storyteller_version,
    )


if __name__ == "__main__":
    main()
