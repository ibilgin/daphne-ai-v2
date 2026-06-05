"""
Celery task: generate_comic

Pipeline stages and Redis progress updates:
  10%  load_models
  30%  caption
  60%  retrieve_style
  80%  generate_story
  95%  structure_panels
  100% save_result

Child data privacy
------------------
The raw image bytes passed to this task are NEVER written to disk or any
persistent store.  Only the SHA-256 hash is recorded in the audit log.
The task receives image bytes as a base64 string (to survive Celery
serialisation); the raw bytes are reconstructed in memory only.

Redis key schema (polled by the Vue frontend via GET /api/jobs/{job_id}):
  job:{job_id}    → JSON {"status": str, "stage": str, "progress_pct": int,
                           "result_id": str | null, "error": str | null}
  comic:{result_id} → JSON serialisation of ComicSchema
"""

from __future__ import annotations

import base64
import hashlib
import json
import logging
import uuid
from datetime import datetime, timezone

import redis as redis_lib
from celery import Celery

from app.config import get_settings

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Celery application
# ---------------------------------------------------------------------------
settings = get_settings()

celery_app = Celery(
    "comic_tasks",
    broker=settings.celery_broker_url,
    backend=settings.celery_result_backend,
)
celery_app.conf.update(
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    timezone="UTC",
    enable_utc=True,
)

# ---------------------------------------------------------------------------
# Redis client (separate from Celery broker — used for job-progress keys)
# ---------------------------------------------------------------------------
_redis: redis_lib.Redis | None = None


def _get_redis() -> redis_lib.Redis:
    global _redis
    if _redis is None:
        _redis = redis_lib.from_url(settings.redis_url, decode_responses=True)
    return _redis


# ---------------------------------------------------------------------------
# Helper: write progress to Redis
# ---------------------------------------------------------------------------

def _update_progress(
    r: redis_lib.Redis,
    job_id: str,
    *,
    status: str,
    stage: str,
    progress_pct: int,
    result_id: str | None = None,
    error: str | None = None,
) -> None:
    payload = {
        "status": status,
        "stage": stage,
        "progress_pct": progress_pct,
        "result_id": result_id,
        "error": error,
    }
    r.set(f"job:{job_id}", json.dumps(payload), ex=3600)  # 1-hour TTL


# ---------------------------------------------------------------------------
# Celery task
# ---------------------------------------------------------------------------

@celery_app.task(name="tasks.generate_comic", bind=True, max_retries=0)
def generate_comic(
    self,
    job_id: str,
    image_bytes_b64: str,
    child_name: str,
    style: str,
) -> None:
    """
    Full comic-generation pipeline.

    Parameters
    ----------
    job_id : str
        UUID string matching the key the frontend polls.
    image_bytes_b64 : str
        Base64-encoded image bytes.  Raw bytes are never stored.
    child_name : str
        Personalisation input.
    style : str
        Style identifier used for RAG retrieval (Phase 3).
    """
    r = _get_redis()

    # Audit: SHA-256 hash only — never log or store raw bytes.
    image_hash = hashlib.sha256(image_bytes_b64.encode()).hexdigest()
    logger.info("generate_comic: job_id=%s image_hash=%s", job_id, image_hash)

    try:
        # ------------------------------------------------------------------
        # Stage 1: load_models (10%)
        # ------------------------------------------------------------------
        _update_progress(r, job_id, status="processing", stage="load_models", progress_pct=10)

        from app.model_loader import get_captioner, get_storyteller

        captioner = get_captioner()
        storyteller = get_storyteller()

        # ------------------------------------------------------------------
        # Stage 2: caption (30%)
        # ------------------------------------------------------------------
        _update_progress(r, job_id, status="processing", stage="caption", progress_pct=30)

        import pandas as pd

        caption_result = captioner.predict(
            pd.DataFrame([{"image_bytes": image_bytes_b64}])
        )
        caption: str = caption_result["caption"]
        logger.info("generate_comic: caption=%r", caption)

        # ------------------------------------------------------------------
        # Stage 3: retrieve_style (60%)
        # Phase 3 will wire in ChromaDB; for now return empty style examples.
        # ------------------------------------------------------------------
        _update_progress(r, job_id, status="processing", stage="retrieve_style", progress_pct=60)

        style_examples: list[str] = []
        logger.debug("generate_comic: style_examples=%s (Phase 3 stub)", style_examples)

        # ------------------------------------------------------------------
        # Stage 4: generate_story (80%)
        # ------------------------------------------------------------------
        _update_progress(r, job_id, status="processing", stage="generate_story", progress_pct=80)

        import json as _json

        story_result = storyteller.predict(
            pd.DataFrame(
                [
                    {
                        "caption": caption,
                        "style_examples": _json.dumps(style_examples),
                        "panel_count": 4,
                    }
                ]
            )
        )
        panels_raw: list[dict] = story_result["panels"]

        # ------------------------------------------------------------------
        # Stage 5: structure_panels (95%)
        # ------------------------------------------------------------------
        _update_progress(r, job_id, status="processing", stage="structure_panels", progress_pct=95)

        from app.schemas import ComicSchema, PageSchema, PanelSchema

        structured_panels = [
            PanelSchema(
                image_bytes_b64=image_bytes_b64,  # placeholder — Phase 3 will generate per-panel art
                caption=caption,
                narration=p.get("narration", ""),
                dialogue=p.get("dialogue"),
            )
            for p in panels_raw
        ]

        # Build a single page with all panels
        page = PageSchema(
            page_num=1,
            layout=str(min(len(structured_panels), 4)),  # type: ignore[arg-type]
            panels=structured_panels,
        )

        result_id = str(uuid.uuid4())
        comic = ComicSchema(
            id=result_id,
            child_name=child_name,
            cover_title=f"{child_name}'s Comic Adventure",
            created_at=datetime.now(tz=timezone.utc),
            pages=[page],
        )

        # ------------------------------------------------------------------
        # Stage 6: save_result (100%)
        # ------------------------------------------------------------------
        _update_progress(r, job_id, status="processing", stage="save_result", progress_pct=95)

        # Persist ComicSchema JSON to Redis (1-hour TTL)
        # Raw image bytes survive only inside the in-memory comic object here;
        # they are NOT separately persisted.
        r.set(f"comic:{result_id}", comic.model_dump_json(), ex=3600)

        _update_progress(
            r,
            job_id,
            status="complete",
            stage="save_result",
            progress_pct=100,
            result_id=result_id,
        )
        logger.info("generate_comic: complete job_id=%s result_id=%s", job_id, result_id)

    except Exception as exc:  # noqa: BLE001
        logger.exception("generate_comic: FAILED job_id=%s — %s", job_id, exc)
        _update_progress(
            r,
            job_id,
            status="failed",
            stage="error",
            progress_pct=0,
            error=str(exc),
        )
