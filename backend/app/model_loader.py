"""
Singleton model loader for MLflow pyfunc models.

Loads the captioner and storyteller from the Production alias at application
startup.  Retries up to 3 times with exponential backoff so that a transient
MLflow / MinIO blip does not prevent the server from starting.

Usage
-----
from app.model_loader import get_captioner, get_storyteller

captioner  = get_captioner()   # mlflow.pyfunc.PyFuncModel
storyteller = get_storyteller()
"""

from __future__ import annotations

import logging
import time
from typing import Any

import mlflow.pyfunc

from app.config import get_settings

logger = logging.getLogger(__name__)

_captioner: Any = None
_storyteller: Any = None


def _load_with_retry(model_name: str, alias: str, max_retries: int = 3) -> Any:
    """Load an MLflow pyfunc model by registered-model alias, retrying on failure."""
    settings = get_settings()
    mlflow.set_tracking_uri(settings.mlflow_tracking_uri)

    uri = f"models:/{model_name}@{alias}"
    last_exc: Exception | None = None

    for attempt in range(1, max_retries + 1):
        try:
            logger.info(
                "model_loader: loading %s (attempt %d/%d)", uri, attempt, max_retries
            )
            model = mlflow.pyfunc.load_model(uri)
            logger.info("model_loader: %s loaded successfully", uri)
            return model
        except Exception as exc:  # noqa: BLE001
            last_exc = exc
            wait = 2 ** attempt  # 2 s, 4 s, 8 s
            logger.warning(
                "model_loader: attempt %d failed for %s — %s. Retrying in %ds.",
                attempt,
                uri,
                exc,
                wait,
            )
            if attempt < max_retries:
                time.sleep(wait)

    raise RuntimeError(
        f"model_loader: could not load {uri} after {max_retries} attempts. "
        f"Last error: {last_exc}"
    ) from last_exc


def load_all_models() -> None:
    """Load both models into module-level singletons.  Call once at startup."""
    global _captioner, _storyteller
    settings = get_settings()
    alias = settings.model_alias

    _captioner = _load_with_retry(settings.captioner_model_name, alias)
    _storyteller = _load_with_retry(settings.storyteller_model_name, alias)
    logger.info("model_loader: all models ready")


def get_captioner() -> Any:
    """Return the captioner singleton, loading it on first call if needed."""
    global _captioner
    if _captioner is None:
        load_all_models()
    return _captioner


def get_storyteller() -> Any:
    """Return the storyteller singleton, loading it on first call if needed."""
    global _storyteller
    if _storyteller is None:
        load_all_models()
    return _storyteller
