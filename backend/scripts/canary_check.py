"""
Champion-Challenger canary check.

Runs both Champion (Production alias) and Challenger (Staging alias) captioner
models on the same 20-image batch, computes METEOR for each, logs both to
MLflow under the "champion-challenger" experiment, and prints the winner alias.

Exit codes:
    0 — completed successfully (winner printed to stdout)
    1 — error during evaluation

Usage:
    python backend/scripts/canary_check.py

Environment variables:
    MLFLOW_TRACKING_URI        (default: http://localhost:5001)
    MLFLOW_S3_ENDPOINT_URL     (default: http://localhost:9000)
    AWS_ACCESS_KEY_ID
    AWS_SECRET_ACCESS_KEY
"""

from __future__ import annotations

import base64
import hashlib
import io
import logging
import os
import sys
from pathlib import Path

import mlflow
import mlflow.pyfunc
import nltk
import pandas as pd
from nltk.translate.meteor_score import meteor_score

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
MLFLOW_TRACKING_URI = os.environ.get("MLFLOW_TRACKING_URI", "http://localhost:5001")
MLFLOW_S3_ENDPOINT_URL = os.environ.get("MLFLOW_S3_ENDPOINT_URL", "http://localhost:9000")
AWS_ACCESS_KEY_ID = os.environ.get("AWS_ACCESS_KEY_ID", "minioadmin")
AWS_SECRET_ACCESS_KEY = os.environ.get("AWS_SECRET_ACCESS_KEY", "minioadmin")

REGISTERED_MODEL_NAME = "sketch-to-story-captioner"
CHAMPION_ALIAS = "Production"
CHALLENGER_ALIAS = "Staging"
EXPERIMENT_NAME = "champion-challenger"

BACKEND_DIR = Path(__file__).parents[1]
FIXTURES_DIR = BACKEND_DIR.parent / "tests" / "fixtures"

REFERENCE_CAPTIONS: list[str] = [
    "a child's drawing of a smiling sun above a green hill",
    "a crayon sketch of a cat sitting on a red mat",
    "a pencil drawing of a rocket flying through space",
    "a colourful drawing of a house with a garden",
    "a child's drawing of a dragon breathing fire",
    "a sketch of a fish swimming in a blue ocean",
    "a drawing of a princess wearing a crown",
    "a crayon picture of a dog chasing a ball",
    "a child's art of a rainbow over the mountains",
    "a drawing of a robot waving hello",
    "a sketch of a butterfly landing on a flower",
    "a child's drawing of a car driving on a road",
    "a crayon picture of a tree with birds on branches",
    "a drawing of a superhero flying through the clouds",
    "a child's sketch of a boat on the sea",
    "a colourful drawing of a birthday cake with candles",
    "a pencil drawing of a train on the tracks",
    "a child's art of a lion in the jungle",
    "a crayon sketch of a fairy with wings",
    "a drawing of a family standing in front of their home",
]


def _setup_env() -> None:
    os.environ.setdefault("MLFLOW_S3_ENDPOINT_URL", MLFLOW_S3_ENDPOINT_URL)
    os.environ.setdefault("AWS_ACCESS_KEY_ID", AWS_ACCESS_KEY_ID)
    os.environ.setdefault("AWS_SECRET_ACCESS_KEY", AWS_SECRET_ACCESS_KEY)
    mlflow.set_tracking_uri(MLFLOW_TRACKING_URI)


def _ensure_nltk_data() -> None:
    for resource, path in [
        ("wordnet", "corpora/wordnet"),
        ("punkt", "tokenizers/punkt"),
        ("punkt_tab", "tokenizers/punkt_tab"),
    ]:
        try:
            nltk.data.find(path)
        except LookupError:
            nltk.download(resource, quiet=True)


def load_fixture_images(count: int = 20) -> list[str]:
    """Return `count` base64-encoded images; pad with grey placeholders if needed."""
    from PIL import Image

    images_b64: list[str] = []
    image_files = sorted(
        p
        for p in FIXTURES_DIR.iterdir()
        if p.suffix.lower() in {".png", ".jpg", ".jpeg"}
    ) if FIXTURES_DIR.exists() else []

    for img_path in image_files[:count]:
        with open(img_path, "rb") as f:
            images_b64.append(base64.b64encode(f.read()).decode())

    while len(images_b64) < count:
        idx = len(images_b64)
        img = Image.new("RGB", (64, 64), color=(200 - idx * 3, 200, 200))
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        images_b64.append(base64.b64encode(buf.getvalue()).decode())

    return images_b64


def evaluate_model(model: mlflow.pyfunc.PyFuncModel, images: list[str]) -> tuple[float, list[str]]:
    """Run model on images and return (avg_meteor, hypotheses)."""
    _ensure_nltk_data()

    hypotheses: list[str] = []
    for img_b64 in images:
        img_hash = hashlib.sha256(img_b64.encode()).hexdigest()
        logger.debug("predict  hash=%s", img_hash)
        row = pd.DataFrame([{"image_bytes": img_b64}])
        result = model.predict(row)
        caption = result["caption"] if isinstance(result, dict) else str(result)
        hypotheses.append(caption)

    references = REFERENCE_CAPTIONS[: len(hypotheses)]
    scores = [
        meteor_score([ref.split()], hyp.split())
        for ref, hyp in zip(references, hypotheses)
    ]
    avg_meteor = sum(scores) / len(scores)
    return avg_meteor, hypotheses


def main() -> None:
    _setup_env()

    # ------------------------------------------------------------------
    # 1. Load images
    # ------------------------------------------------------------------
    logger.info("Loading 20 fixture images")
    images = load_fixture_images(count=20)

    # ------------------------------------------------------------------
    # 2. Load Champion and Challenger
    # ------------------------------------------------------------------
    champion_uri = f"models:/{REGISTERED_MODEL_NAME}@{CHAMPION_ALIAS}"
    challenger_uri = f"models:/{REGISTERED_MODEL_NAME}@{CHALLENGER_ALIAS}"

    logger.info("Loading Champion (%s)", champion_uri)
    try:
        champion_model = mlflow.pyfunc.load_model(champion_uri)
    except Exception as exc:
        logger.error("Could not load Champion model: %s", exc)
        sys.exit(1)

    logger.info("Loading Challenger (%s)", challenger_uri)
    try:
        challenger_model = mlflow.pyfunc.load_model(challenger_uri)
    except Exception as exc:
        logger.error("Could not load Challenger model: %s", exc)
        sys.exit(1)

    # ------------------------------------------------------------------
    # 3. Evaluate both models
    # ------------------------------------------------------------------
    logger.info("Evaluating Champion …")
    champion_meteor, _ = evaluate_model(champion_model, images)
    logger.info("Champion METEOR: %.4f", champion_meteor)

    logger.info("Evaluating Challenger …")
    challenger_meteor, _ = evaluate_model(challenger_model, images)
    logger.info("Challenger METEOR: %.4f", challenger_meteor)

    # ------------------------------------------------------------------
    # 4. Log to MLflow
    # ------------------------------------------------------------------
    mlflow.set_experiment(EXPERIMENT_NAME)
    with mlflow.start_run(run_name="canary-comparison"):
        mlflow.log_metric("champion_meteor", champion_meteor)
        mlflow.log_metric("challenger_meteor", challenger_meteor)
        mlflow.log_metric("delta_meteor", challenger_meteor - champion_meteor)
        mlflow.log_param("champion_alias", CHAMPION_ALIAS)
        mlflow.log_param("challenger_alias", CHALLENGER_ALIAS)
        mlflow.log_param("image_count", len(images))

    # ------------------------------------------------------------------
    # 5. Return winner
    # ------------------------------------------------------------------
    if challenger_meteor > champion_meteor:
        winner = CHALLENGER_ALIAS
    else:
        winner = CHAMPION_ALIAS

    logger.info(
        "Winner: %s  (champion=%.4f  challenger=%.4f)",
        winner,
        champion_meteor,
        challenger_meteor,
    )
    print(winner)


if __name__ == "__main__":
    main()
