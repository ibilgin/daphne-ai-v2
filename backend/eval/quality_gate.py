"""
Captioner quality gate.

Loads the latest Staging captioner from the MLflow model registry,
runs it against a test set of 20 images from tests/fixtures/,
computes METEOR and BERTScore F1, and promotes to Production only if:

    METEOR > 0.35  AND  BERTScore F1 > 0.75  (model: roberta-large)

Exit codes:
    0 — quality gate PASSED, Production alias updated
    1 — quality gate FAILED (metrics below threshold)
"""

from __future__ import annotations

import base64
import hashlib
import logging
import os
import sys
from pathlib import Path

import mlflow
import pandas as pd

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
MLFLOW_TRACKING_URI = os.environ.get("MLFLOW_TRACKING_URI", "http://localhost:5001")
REGISTERED_MODEL_NAME = "sketch-to-story-captioner"
STAGING_ALIAS = "Staging"
PRODUCTION_ALIAS = "Production"

METEOR_THRESHOLD = 0.35
BERTSCORE_THRESHOLD = 0.75
BERTSCORE_MODEL = "roberta-large"

FIXTURES_DIR = Path(__file__).parents[2] / "tests" / "fixtures"

# Reference captions for the 20 test images (index-matched to sorted fixture list)
# In a real project these would live in a JSON/CSV sidecar file.
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


def load_fixture_images(fixtures_dir: Path, count: int = 20) -> list[str]:
    """
    Return up to `count` base64-encoded images from fixtures_dir.
    If fewer real images exist, generate simple grey placeholder PNGs.
    """
    import io

    from PIL import Image

    images_b64: list[str] = []

    # Real fixture images (sorted for reproducibility)
    image_files = sorted(
        p
        for p in fixtures_dir.iterdir()
        if p.suffix.lower() in {".png", ".jpg", ".jpeg"}
    )

    for img_path in image_files[:count]:
        with open(img_path, "rb") as f:
            images_b64.append(base64.b64encode(f.read()).decode())

    # Pad with generated grey squares if not enough real fixtures
    while len(images_b64) < count:
        idx = len(images_b64)
        img = Image.new("RGB", (64, 64), color=(200 - idx * 3, 200, 200))
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        images_b64.append(base64.b64encode(buf.getvalue()).decode())

    return images_b64


def run_quality_gate() -> None:
    mlflow.set_tracking_uri(MLFLOW_TRACKING_URI)

    # ------------------------------------------------------------------
    # 1. Load latest Staging model
    # ------------------------------------------------------------------
    logger.info("Loading model '%s' @ alias '%s'", REGISTERED_MODEL_NAME, STAGING_ALIAS)
    model_uri = f"models:/{REGISTERED_MODEL_NAME}@{STAGING_ALIAS}"
    try:
        model = mlflow.pyfunc.load_model(model_uri)
    except Exception as exc:
        logger.error("Failed to load model: %s", exc)
        sys.exit(1)

    # ------------------------------------------------------------------
    # 2. Collect test images
    # ------------------------------------------------------------------
    logger.info("Loading fixture images from %s", FIXTURES_DIR)
    images = load_fixture_images(FIXTURES_DIR, count=20)
    assert len(images) == 20, f"Expected 20 images, got {len(images)}"

    # ------------------------------------------------------------------
    # 3. Run inference — collect hypotheses
    # ------------------------------------------------------------------
    hypotheses: list[str] = []
    for i, img_b64 in enumerate(images):
        img_hash = hashlib.sha256(img_b64.encode()).hexdigest()
        logger.debug("Predicting image %d  hash=%s", i, img_hash)

        row = pd.DataFrame([{"image_bytes": img_b64}])
        result = model.predict(row)
        caption = result["caption"] if isinstance(result, dict) else result
        hypotheses.append(str(caption))
        logger.info("Image %02d: %s", i, caption)

    references: list[str] = REFERENCE_CAPTIONS[: len(hypotheses)]

    # ------------------------------------------------------------------
    # 4. Compute METEOR
    # ------------------------------------------------------------------
    logger.info("Computing METEOR …")
    from nltk.translate.meteor_score import meteor_score
    import nltk

    try:
        nltk.data.find("corpora/wordnet")
    except LookupError:
        nltk.download("wordnet", quiet=True)
    try:
        nltk.data.find("tokenizers/punkt")
    except LookupError:
        nltk.download("punkt", quiet=True)
    try:
        nltk.data.find("tokenizers/punkt_tab")
    except LookupError:
        nltk.download("punkt_tab", quiet=True)

    meteor_scores = [
        meteor_score([ref.split()], hyp.split())
        for ref, hyp in zip(references, hypotheses)
    ]
    avg_meteor = sum(meteor_scores) / len(meteor_scores)
    logger.info("METEOR (avg): %.4f  (threshold: %.2f)", avg_meteor, METEOR_THRESHOLD)

    # ------------------------------------------------------------------
    # 5. Compute BERTScore
    # ------------------------------------------------------------------
    logger.info("Computing BERTScore (model=%s) …", BERTSCORE_MODEL)
    from bert_score import score as bert_score

    P, R, F1 = bert_score(
        hypotheses, references, model_type=BERTSCORE_MODEL, verbose=False
    )
    avg_bertscore_f1 = float(F1.mean())
    logger.info(
        "BERTScore F1 (avg): %.4f  (threshold: %.2f)",
        avg_bertscore_f1,
        BERTSCORE_THRESHOLD,
    )

    # ------------------------------------------------------------------
    # 6. Log metrics to MLflow
    # ------------------------------------------------------------------
    with mlflow.start_run(run_name="quality_gate"):
        mlflow.log_metric("meteor", avg_meteor)
        mlflow.log_metric("bertscore_f1", avg_bertscore_f1)
        mlflow.log_metric("meteor_threshold", METEOR_THRESHOLD)
        mlflow.log_metric("bertscore_threshold", BERTSCORE_THRESHOLD)

    # ------------------------------------------------------------------
    # 7. Gate decision
    # ------------------------------------------------------------------
    passed = avg_meteor > METEOR_THRESHOLD and avg_bertscore_f1 > BERTSCORE_THRESHOLD

    summary = (
        f"METEOR={avg_meteor:.4f} (>{METEOR_THRESHOLD})  "
        f"BERTScore_F1={avg_bertscore_f1:.4f} (>{BERTSCORE_THRESHOLD})  "
        f"=> {'PASS' if passed else 'FAIL'}"
    )
    logger.info("Quality gate result: %s", summary)

    if not passed:
        logger.error("Quality gate FAILED — not promoting to Production")
        logger.error(summary)
        sys.exit(1)

    # ------------------------------------------------------------------
    # 8. Promote to Production
    # ------------------------------------------------------------------
    client = mlflow.tracking.MlflowClient()

    # Resolve the version currently at Staging
    mv = client.get_model_version_by_alias(REGISTERED_MODEL_NAME, STAGING_ALIAS)
    version = mv.version

    logger.info(
        "Promoting version %s of '%s' to alias '%s'",
        version,
        REGISTERED_MODEL_NAME,
        PRODUCTION_ALIAS,
    )
    client.set_registered_model_alias(
        name=REGISTERED_MODEL_NAME,
        alias=PRODUCTION_ALIAS,
        version=version,
    )
    logger.info("Quality gate PASSED — Production alias updated to version %s", version)


if __name__ == "__main__":
    run_quality_gate()
