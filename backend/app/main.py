"""
FastAPI application — Sketch to Story serving layer.

Routes
------
POST /api/generate-comic   multipart/form-data: file, child_name, style
GET  /api/jobs/{job_id}    progress polling
GET  /api/comics/{id}      full ComicSchema JSON
GET  /metrics              Prometheus exposition
GET  /health               liveness / readiness

Image validation (POST /api/generate-comic)
------------------------------------------
1. MIME type must be image/jpeg or image/png.
2. File size must be < MAX_IMAGE_BYTES (default 5 MB).
3. Image must not be blank: pixel standard deviation > MIN_STD_DEVIATION.

Child data privacy
------------------
Raw image bytes are forwarded to the Celery task as a base64 string and are
NEVER written to disk or the database.  Only the SHA-256 hash is logged here.
"""

from __future__ import annotations

import base64
import hashlib
import io
import json
import logging
import uuid
from typing import Any

import redis as redis_lib
from fastapi import Depends, FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import PlainTextResponse
from prometheus_client import (
    CONTENT_TYPE_LATEST,
    generate_latest,
)

from app.config import get_settings
from app.schemas import ComicSchema, EnqueueResponseSchema, JobStatusSchema
from monitoring.metrics_exporter import (
    jobs_total,
    queue_depth,
    update_queue_depth,
)
from security.auth import TokenPayload, create_token, require_role

logger = logging.getLogger(__name__)

# queue_depth_gauge alias kept for backward compat with any direct references
queue_depth_gauge = queue_depth

# ---------------------------------------------------------------------------
# FastAPI application
# ---------------------------------------------------------------------------
app = FastAPI(
    title="Sketch to Story API",
    description="Transforms children's drawings into personalised comic books.",
    version="1.0.0",
)

settings = get_settings()

# ---------------------------------------------------------------------------
# Routers
# ---------------------------------------------------------------------------
from app.routes.hooks import router as hooks_router  # noqa: E402

app.include_router(hooks_router)


@app.on_event("startup")
async def startup_event() -> None:
    """Load ML models at startup so the first request is not slow."""
    try:
        from app.model_loader import load_all_models

        load_all_models()
        logger.info("startup: ML models loaded")
    except Exception as exc:  # noqa: BLE001
        # Log but do not crash — the service can still serve /health while
        # models are unavailable (e.g. MLflow not yet reachable).
        logger.warning("startup: model loading failed — %s", exc)


# ---------------------------------------------------------------------------
# CORS
# ---------------------------------------------------------------------------
origins = [o.strip() for o in settings.cors_origins.split(",") if o.strip()]
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins or ["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---------------------------------------------------------------------------
# Redis client (shared — module-level singleton)
# ---------------------------------------------------------------------------
_redis: redis_lib.Redis | None = None


def _get_redis() -> redis_lib.Redis:
    global _redis
    if _redis is None:
        _redis = redis_lib.from_url(settings.redis_url, decode_responses=True)
    return _redis


# ---------------------------------------------------------------------------
# Image validation helpers
# ---------------------------------------------------------------------------
_ALLOWED_CONTENT_TYPES = {"image/jpeg", "image/png"}


def _validate_image(file_bytes: bytes, content_type: str | None) -> None:
    """Raise HTTPException if the image fails any validation check."""
    # 1. Content-type check
    if content_type not in _ALLOWED_CONTENT_TYPES:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported image type '{content_type}'. Use JPEG or PNG.",
        )

    # 2. Size check
    if len(file_bytes) > settings.max_image_bytes:
        mb = settings.max_image_bytes // (1024 * 1024)
        raise HTTPException(
            status_code=400,
            detail=f"Image exceeds maximum allowed size of {mb} MB.",
        )

    # 3. Blank image check via pixel standard deviation
    try:
        import numpy as np
        from PIL import Image

        img = Image.open(io.BytesIO(file_bytes)).convert("L")  # greyscale
        std = float(np.array(img).std())
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=400, detail=f"Could not decode image: {exc}") from exc

    if std < settings.min_std_deviation:
        raise HTTPException(
            status_code=400,
            detail=(
                f"Image appears blank (pixel std={std:.2f} < {settings.min_std_deviation}). "
                "Please upload a drawing with visible content."
            ),
        )


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------


@app.post("/api/auth/token")
async def dev_token() -> dict[str, str]:
    """Issue a short-lived parent-role JWT for local dev (ENABLE_TOKEN_CREATION=true only)."""
    import os
    if os.environ.get("ENABLE_TOKEN_CREATION", "").lower() not in {"1", "true", "yes"}:
        raise HTTPException(status_code=403, detail="Token creation is disabled.")
    from security.auth import _get_jwt_secret
    token = create_token("dev-user", "parent", _get_jwt_secret(), expires_hours=24)
    return {"access_token": token, "token_type": "bearer"}


@app.post("/api/generate-comic", response_model=EnqueueResponseSchema, status_code=202)
async def generate_comic(
    file: UploadFile = File(..., description="Child's drawing (JPEG or PNG, max 5 MB)"),
    child_name: str = Form(..., description="Child's first name"),
    style: str = Form(..., description="Art style for the comic"),
    age_group: str = Form(default="7-9", description="Child's age group: 4-6, 7-9, or 10-12"),
    _token: TokenPayload = require_role("parent"),
) -> Any:
    """
    Validate the uploaded drawing and enqueue a Celery comic-generation job.

    Returns
    -------
    {job_id, status: "queued"}
    """
    file_bytes = await file.read()
    content_type = file.content_type

    # Audit log: hash only — never store raw bytes.
    img_hash = hashlib.sha256(file_bytes).hexdigest()
    logger.info(
        "generate_comic: child_name=%r style=%r image_hash=%s size=%d",
        child_name,
        style,
        img_hash,
        len(file_bytes),
    )

    _validate_image(file_bytes, content_type)

    job_id = str(uuid.uuid4())

    # Write initial status to Redis before enqueueing so GET /api/jobs/{job_id}
    # returns "queued" immediately.
    r = _get_redis()
    r.set(
        f"job:{job_id}",
        json.dumps(
            {
                "status": "queued",
                "stage": "queued",
                "progress_pct": 0,
                "result_id": None,
                "error": None,
            }
        ),
        ex=3600,
    )

    # Enqueue — pass image as base64 string (JSON-safe).
    image_bytes_b64 = base64.b64encode(file_bytes).decode()

    from app.tasks import generate_comic as celery_generate_comic

    celery_generate_comic.delay(job_id, image_bytes_b64, child_name, style, age_group)

    jobs_total.labels(status="queued").inc()
    queue_depth_gauge.inc()

    return EnqueueResponseSchema(job_id=job_id)


@app.get("/api/jobs/{job_id}", response_model=JobStatusSchema)
async def get_job_status(job_id: str) -> Any:
    """
    Poll comic-generation progress.

    Returns
    -------
    {status, progress_pct, stage, result_id?, error?}
    """
    r = _get_redis()
    raw = r.get(f"job:{job_id}")
    if raw is None:
        raise HTTPException(status_code=404, detail=f"Job '{job_id}' not found.")

    data = json.loads(raw)
    return JobStatusSchema(
        status=data["status"],
        progress_pct=data.get("progress_pct", 0),
        stage=data.get("stage", ""),
        result_id=data.get("result_id"),
        error=data.get("error"),
    )


@app.get("/api/comics", response_model=list[ComicSchema])
async def list_comics() -> Any:
    r = _get_redis()
    comic_ids = r.lrange("comic_index", 0, 49)
    comics = []
    for cid in comic_ids:
        raw = r.get(f"comic:{cid}")
        if raw:
            try:
                comics.append(ComicSchema.model_validate_json(raw))
            except Exception:
                pass
    return comics


@app.get("/api/comics/{comic_id}", response_model=ComicSchema)
async def get_comic(comic_id: str) -> Any:
    """
    Retrieve a completed comic by its result ID.

    Returns
    -------
    ComicSchema (full JSON)
    """
    r = _get_redis()
    raw = r.get(f"comic:{comic_id}")
    if raw is None:
        raise HTTPException(status_code=404, detail=f"Comic '{comic_id}' not found.")

    return ComicSchema.model_validate_json(raw)


@app.get("/api/audit")
async def get_audit(
    since: str | None = None,
    _token: TokenPayload = require_role("admin"),
) -> Any:
    """
    Return flagged (FAIL verdict) audit records since the given ISO timestamp.

    Requires admin role.  Returns hashes only — never raw image bytes or
    child names.

    Parameters
    ----------
    since:
        ISO 8601 datetime string (e.g. ``2026-01-01T00:00:00Z``).
        Defaults to the last 7 days if not provided.
    """
    from datetime import datetime, timedelta, timezone

    from security.audit_log import get_audit_logger

    if since:
        try:
            since_dt = datetime.fromisoformat(since.replace("Z", "+00:00"))
        except ValueError as exc:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid 'since' datetime format: {exc}",
            ) from exc
    else:
        since_dt = datetime.now(tz=timezone.utc) - timedelta(days=7)

    audit = get_audit_logger()
    try:
        records = await audit.query_flagged(since_dt)
    except Exception as exc:  # noqa: BLE001
        logger.error("get_audit: query_flagged failed — %s", exc)
        raise HTTPException(status_code=503, detail="Audit log unavailable.") from exc

    return {"count": len(records), "records": records}


@app.get("/metrics", response_class=PlainTextResponse)
async def metrics() -> PlainTextResponse:
    """Prometheus exposition endpoint."""
    # Refresh queue-depth gauge from Redis list length.
    try:
        update_queue_depth(_get_redis())
    except Exception:  # noqa: BLE001
        pass

    return PlainTextResponse(
        content=generate_latest().decode("utf-8"),
        media_type=CONTENT_TYPE_LATEST,
    )


@app.get("/health")
async def health() -> dict[str, str]:
    """Liveness and readiness probe endpoint."""
    return {"status": "ok"}
