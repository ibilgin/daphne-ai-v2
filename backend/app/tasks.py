"""
Celery task: generate_comic

Pipeline is now driven by the LangGraph agent (Phase 3).
Progress stages and Redis key schema remain identical to Phase 2 for
API compatibility with GET /api/jobs/{job_id}.

Stage           Progress  Node
-----------     --------  ----
load_models        10%    (pre-agent, model warm-up)
caption            20%    analyse_drawing
retrieve_style     40%    retrieve_style
generate_story     60%    generate_panels
check_safety       75%    check_safety
structure_panels   90%    assemble
save_result       100%    assemble (Redis persist)

Child data privacy
------------------
Raw image bytes are never written to disk or any persistent store.
Only the SHA-256 hash is recorded in the audit log.
The task receives image bytes as a base64 string (Celery JSON serialisation).

Redis key schema (polled by GET /api/jobs/{job_id}):
  job:{job_id}       → JSON {"status", "stage", "progress_pct", "result_id", "error"}
  comic:{result_id}  → JSON serialisation of ComicSchema
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import uuid

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
# Helper: fire-and-forget audit log write
# ---------------------------------------------------------------------------


def _audit_job(
    *,
    job_id: str,
    image_hash: str,
    panels: list,
    caption: str,
    comic_json: str,
    safety_verdict: str,
    safety_scores: dict,
    stage_timings: dict,
) -> None:
    """
    Write one record to the comic_audit table via AuditLogger.

    Runs the async call in a new event loop so it can be called from
    the synchronous Celery task.

    Privacy: only SHA-256 hashes are passed to AuditLogger.
    Raw image bytes, caption text, story text, and child names are
    hashed here and the originals are never stored.
    """
    caption_hash = hashlib.sha256(caption.encode()).hexdigest()
    story_hash = hashlib.sha256(comic_json.encode()).hexdigest()

    # Derive a stable user_id from the job_id (placeholder until JWT user_id
    # is threaded through the task signature).
    user_id = f"job-user:{job_id}"

    try:
        from security.audit_log import get_audit_logger

        audit = get_audit_logger()
        asyncio.run(
            audit.log_job(
                job_id=job_id,
                user_id=user_id,
                image_hash=image_hash,
                caption_hash=caption_hash,
                story_hash=story_hash,
                safety_verdict=safety_verdict,
                safety_scores=safety_scores,
                stage_timings=stage_timings,
                model_versions={},
            )
        )
        logger.info("_audit_job: logged job_id=%s verdict=%s", job_id, safety_verdict)
    except Exception as exc:  # noqa: BLE001
        # Never let audit failure crash the job result delivery.
        logger.error("_audit_job: FAILED for job_id=%s — %s", job_id, exc)


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
    age_group: str = "7-9",
) -> None:
    """
    Full comic-generation pipeline — driven by the LangGraph agent.

    Parameters
    ----------
    job_id : str
        UUID string matching the key the frontend polls.
    image_bytes_b64 : str
        Base64-encoded image bytes.  Raw bytes are never stored.
    child_name : str
        Personalisation input — used in story generation.
    style : str
        Style preference hint passed to the RAG retriever.
    age_group : str
        One of "4-6", "7-9", "10-12". Defaults to "7-9".
    """
    r = _get_redis()

    # Audit: SHA-256 hash only — never log or store raw bytes.
    image_hash = hashlib.sha256(image_bytes_b64.encode()).hexdigest()
    logger.info("generate_comic: job_id=%s image_hash=%s", job_id, image_hash)

    try:
        # ------------------------------------------------------------------
        # Stage 1: load_models (10%)
        # Warm up the captioner singleton before handing off to the agent.
        # ------------------------------------------------------------------
        _update_progress(r, job_id, status="processing", stage="load_models", progress_pct=10)

        from app.model_loader import get_captioner
        get_captioner()  # ensures the model is loaded; agent nodes use the same singleton

        # ------------------------------------------------------------------
        # Build initial agent state
        # ------------------------------------------------------------------
        from agent.state import ComicState

        initial_state: ComicState = {
            "job_id": job_id,
            "image_bytes": image_bytes_b64,
            "child_name": child_name,
            "age_group": age_group,
            "style_pref": style,
            "caption": None,
            "style_examples": [],
            "panels": [],
            "safety_verdict": None,
            "safety_failure_reason": None,
            "retry_count": 0,
            "final_comic": None,
            "error": None,
        }

        # ------------------------------------------------------------------
        # Run the LangGraph agent (stages 2-6 are managed by node callbacks)
        # ------------------------------------------------------------------
        from agent.tracing import run_agent

        final_state = run_agent(initial_state)

        # ------------------------------------------------------------------
        # Post-agent: propagate result or error to the caller
        # ------------------------------------------------------------------
        if final_state.get("error") == "escalated_to_review":
            _update_progress(
                r,
                job_id,
                status="failed",
                stage="human_review",
                progress_pct=0,
                error="Content could not be made safe — escalated to human review.",
            )
            logger.warning("generate_comic: job_id=%s escalated to human review", job_id)
            return

        if final_state.get("final_comic") is None:
            raise RuntimeError("Agent completed but final_comic is None")

        # The assemble node already wrote comic:{result_id} to Redis.
        # Retrieve the result_id from the completed job key.
        raw = r.get(f"job:{job_id}")
        if raw:
            job_data = json.loads(raw)
            result_id = job_data.get("result_id")
        else:
            result_id = None

        if not result_id:
            # Fallback: write comic directly if assemble skipped Redis write
            result_id = str(uuid.uuid4())
            comic_json = json.dumps(final_state["final_comic"])
            r.set(f"comic:{result_id}", comic_json, ex=3600)

        _update_progress(
            r,
            job_id,
            status="complete",
            stage="save_result",
            progress_pct=100,
            result_id=result_id,
        )

        # ------------------------------------------------------------------
        # Audit log (save_result stage)
        # Hash all sensitive content — never store raw bytes or child name.
        # ------------------------------------------------------------------
        _audit_job(
            job_id=job_id,
            image_hash=image_hash,
            panels=final_state.get("panels") or [],
            caption=final_state.get("caption") or "",
            comic_json=json.dumps(final_state.get("final_comic") or {}),
            safety_verdict=final_state.get("safety_verdict") or "UNKNOWN",
            safety_scores={},
            stage_timings={},
        )

        logger.info(
            "generate_comic: complete job_id=%s result_id=%s", job_id, result_id
        )

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
        # Audit even failed jobs — pass "UNKNOWN" verdict and empty hashes
        # so the audit table has a complete record for every job attempt.
        _audit_job(
            job_id=job_id,
            image_hash=image_hash,
            panels=[],
            caption="",
            comic_json="{}",
            safety_verdict="FAIL",
            safety_scores={},
            stage_timings={},
        )
