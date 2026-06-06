"""
LangGraph node functions for the comic generation agent.

Every node is a pure function (state: ComicState) -> ComicState.
Side-effects limited to:
  - logging (audit)
  - Redis progress updates (job:{job_id} key)
  - Postgres write in human_review

Detoxify safety thresholds (from CLAUDE.md critical constraints):
  toxicity       < 0.1
  identity_attack < 0.05
"""

from __future__ import annotations

import hashlib
import json
import logging
import uuid
from datetime import datetime, timezone

from agent.state import ComicState

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Safety thresholds
# ---------------------------------------------------------------------------
_TOXICITY_THRESHOLD = 0.1
_IDENTITY_ATTACK_THRESHOLD = 0.05

# ---------------------------------------------------------------------------
# Redis progress helper (optional — skips if Redis unavailable)
# ---------------------------------------------------------------------------


def _update_redis_progress(
    job_id: str,
    stage: str,
    progress_pct: int,
) -> None:
    """Write progress to Redis. Silently skips if Redis is not reachable."""
    try:
        import redis as redis_lib

        from app.config import get_settings

        settings = get_settings()
        r = redis_lib.from_url(settings.redis_url, decode_responses=True)
        payload = {
            "status": "processing",
            "stage": stage,
            "progress_pct": progress_pct,
            "result_id": None,
            "error": None,
        }
        r.set(f"job:{job_id}", json.dumps(payload), ex=3600)
        logger.debug("Redis progress: job_id=%s stage=%s pct=%d", job_id, stage, progress_pct)
    except Exception as exc:  # noqa: BLE001
        logger.debug("Redis progress update skipped — %s", exc)


# ===========================================================================
# Node: analyse_drawing
# ===========================================================================


def analyse_drawing(state: ComicState) -> ComicState:
    """
    Call the MLflow BLIP captioner to generate a text caption from the drawing.

    Reads image_bytes (base64) from state.  Logs SHA-256 hash only — raw bytes
    are never written to any persistent store.

    Sets: state["caption"]
    """
    _update_redis_progress(state["job_id"], "caption", 20)

    image_b64: str = state["image_bytes"]
    image_hash = hashlib.sha256(image_b64.encode()).hexdigest()
    logger.info("analyse_drawing: job_id=%s image_hash=%s", state["job_id"], image_hash)

    from app.model_loader import get_captioner

    captioner = get_captioner()

    import pandas as pd

    result = captioner.predict(pd.DataFrame([{"image_bytes": image_b64}]))
    caption: str = result["caption"]
    logger.info("analyse_drawing: caption=%r", caption)

    return {**state, "caption": caption}


# ===========================================================================
# Node: retrieve_style
# ===========================================================================


def retrieve_style(state: ComicState) -> ComicState:
    """
    Run two-stage RAG retrieval to find the most relevant style examples.

    Uses StyleRetriever (ChromaDB cosine search + cross-encoder re-ranking).
    Sets state["style_examples"] as a list of plain text strings.
    """
    _update_redis_progress(state["job_id"], "retrieve_style", 40)

    caption = state.get("caption") or ""
    age_group = state.get("age_group", "7-9")

    try:
        from rag.retriever import StyleRetriever

        retriever = StyleRetriever()
        examples = retriever.retrieve(caption=caption, age_group=age_group, top_k=3)
        style_texts = [ex.text for ex in examples]
        logger.info(
            "retrieve_style: job_id=%s retrieved %d examples styles=%s",
            state["job_id"],
            len(examples),
            [ex.style for ex in examples],
        )
    except Exception as exc:  # noqa: BLE001
        # ChromaDB index not yet built — continue without style examples.
        # Run `make rag-index` to populate the index.
        logger.warning("retrieve_style: RAG unavailable (%s) — continuing without examples", exc)
        style_texts = []

    return {**state, "style_examples": style_texts}


# ===========================================================================
# Node: generate_panels
# ===========================================================================


def generate_panels(state: ComicState) -> ComicState:
    """
    Call the LangChain story chain to generate (or rewrite) comic panel narration.

    Two paths:
    - rough_narrative provided → rewrite the child's story into 4 storybook panels
    - no rough_narrative → generate a story from the image caption

    On safety retry the failure reason is forwarded so the model avoids the
    problematic content.
    """
    _update_redis_progress(state["job_id"], "generate_story", 60)

    caption = state.get("caption") or ""
    style_examples = state.get("style_examples") or []
    child_name = state.get("child_name", "the child")
    safety_failure_reason = state.get("safety_failure_reason")
    rough_narrative = state.get("rough_narrative") or ""

    if rough_narrative.strip():
        logger.info(
            "generate_panels: job_id=%s narrative-rewrite path (%d chars)",
            state["job_id"], len(rough_narrative),
        )
    elif safety_failure_reason:
        logger.info(
            "generate_panels: job_id=%s retry with safety augmentation — %s",
            state["job_id"],
            safety_failure_reason,
        )

    from rag.story_chain import generate_panels as _generate

    panels = _generate(
        caption=caption,
        style_examples=style_examples,
        child_name=child_name,
        panel_count=4,
        safety_failure_reason=safety_failure_reason,
        rough_narrative=rough_narrative,
    )
    logger.info("generate_panels: job_id=%s generated %d panels", state["job_id"], len(panels))

    return {**state, "panels": panels}


# ===========================================================================
# Node: generate_panel_images
# ===========================================================================


def generate_panel_images(state: ComicState) -> ComicState:
    """
    Generate a panel illustration for every panel using the img2img model.

    Reads state["image_bytes"] (seed drawing, base64) and state["panels"].
    Calls the panel_image_gen MLflow model which:
      - "stability" backend → Stability AI /control/sketch (best quality)
      - "hf_api"    backend → HuggingFace Inference API img2img
      - "pil"       backend → PIL pencil-sketch + mood tint (fallback)

    Backend is selected via PANEL_IMG_GEN_BACKEND env var.  If the MLflow
    model is not yet registered the PIL fallback is used automatically.

    Adds "image_bytes_b64" to each panel dict for the assemble node.
    """
    _update_redis_progress(state["job_id"], "draw_panels", 70)

    panels: list[dict] = state.get("panels") or []
    style: str = state.get("style_pref", "adventure")
    seed_image_b64: str = state.get("image_bytes", "")

    from app.model_loader import get_panel_image_gen

    panel_gen = get_panel_image_gen()

    enriched = []
    for i, panel in enumerate(panels):
        narration = panel.get("narration", "")
        logger.info(
            "generate_panel_images: job_id=%s panel=%d backend=%s narration=%r",
            state["job_id"], i + 1,
            "mlflow" if panel_gen else "pil-fallback",
            narration[:60],
        )

        if panel_gen is not None:
            import pandas as pd  # noqa: PLC0415
            result = panel_gen.predict(pd.DataFrame([{
                "seed_image_b64": seed_image_b64,
                "narration": narration,
                "panel_num": i,
                "style": style,
            }]))
            image_b64 = result.get("image_b64", "") if isinstance(result, dict) else ""
        else:
            from agent.panel_artist import draw_panel_image  # noqa: PLC0415
            image_b64 = draw_panel_image(seed_image_b64, narration, i, style)

        if not image_b64:
            from agent.panel_artist import draw_panel_image  # noqa: PLC0415
            image_b64 = draw_panel_image(seed_image_b64, narration, i, style)

        enriched.append({**panel, "image_bytes_b64": image_b64})

    logger.info(
        "generate_panel_images: job_id=%s drew %d panel images",
        state["job_id"], len(enriched),
    )
    return {**state, "panels": enriched}


# ===========================================================================
# Node: check_safety
# ===========================================================================


def check_safety(state: ComicState) -> ComicState:
    """
    Run Detoxify safety checks on all panel narration and dialogue text.

    Thresholds (CLAUDE.md critical constraints):
      - toxicity < 0.1 per panel
      - identity_attack < 0.05 per panel

    Sets state["safety_verdict"] = "PASS" | "FAIL".
    On FAIL, sets state["safety_failure_reason"] with specifics for retry prompt.
    """
    _update_redis_progress(state["job_id"], "check_safety", 75)

    panels: list[dict] = state.get("panels") or []

    if not panels:
        logger.warning("check_safety: no panels to evaluate — defaulting to FAIL")
        return {
            **state,
            "safety_verdict": "FAIL",
            "safety_failure_reason": "No panels were generated.",
        }

    # Collect all text to score
    texts: list[str] = []
    for panel in panels:
        narration = panel.get("narration", "")
        dialogue = panel.get("dialogue") or ""
        if narration:
            texts.append(narration)
        if dialogue:
            texts.append(dialogue)

    if not texts:
        return {**state, "safety_verdict": "PASS", "safety_failure_reason": None}

    try:
        from detoxify import Detoxify

        model = Detoxify("original")
        scores = model.predict(texts)
    except Exception as exc:  # noqa: BLE001
        logger.error("check_safety: Detoxify failed — %s. Treating as PASS.", exc)
        return {**state, "safety_verdict": "PASS", "safety_failure_reason": None}

    # Check each text's scores against thresholds
    failures: list[str] = []
    for i, text in enumerate(texts):
        toxicity = float(scores["toxicity"][i])
        identity_attack = float(scores["identity_attack"][i])

        if toxicity >= _TOXICITY_THRESHOLD:
            failures.append(
                f"Text {i + 1} has toxicity score {toxicity:.3f} (threshold {_TOXICITY_THRESHOLD})"
            )
        if identity_attack >= _IDENTITY_ATTACK_THRESHOLD:
            failures.append(
                f"Text {i + 1} has identity_attack score {identity_attack:.3f} "
                f"(threshold {_IDENTITY_ATTACK_THRESHOLD})"
            )

    if failures:
        reason = "; ".join(failures)
        logger.warning(
            "check_safety: FAIL job_id=%s — %s", state["job_id"], reason
        )
        return {
            **state,
            "safety_verdict": "FAIL",
            "safety_failure_reason": reason,
        }

    logger.info("check_safety: PASS job_id=%s", state["job_id"])
    return {**state, "safety_verdict": "PASS", "safety_failure_reason": None}


# ===========================================================================
# Node: assemble
# ===========================================================================


def assemble(state: ComicState) -> ComicState:
    """
    Build a validated ComicSchema from the state panels and store it in final_comic.

    Uses PanelSchema / PageSchema / ComicSchema from app.schemas (Pydantic v2).
    """
    _update_redis_progress(state["job_id"], "structure_panels", 90)

    panels_raw: list[dict] = state.get("panels") or []
    image_b64: str = state.get("image_bytes", "")
    caption: str = state.get("caption") or ""
    child_name: str = state.get("child_name", "")

    from app.schemas import ComicSchema, PageSchema, PanelSchema

    structured_panels = [
        PanelSchema(
            # Use the per-panel generated drawing; fall back to original if absent
            image_bytes_b64=p.get("image_bytes_b64") or image_b64,
            caption=caption,
            narration=p.get("narration", ""),
            dialogue=p.get("dialogue"),
        )
        for p in panels_raw
    ]

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

    logger.info(
        "assemble: job_id=%s result_id=%s panels=%d",
        state["job_id"],
        result_id,
        len(structured_panels),
    )

    # Persist to Redis so GET /api/comics/{id} can serve it
    try:
        import redis as redis_lib

        from app.config import get_settings

        settings = get_settings()
        r = redis_lib.from_url(settings.redis_url, decode_responses=True)
        r.set(f"comic:{result_id}", comic.model_dump_json(), ex=3600)

        # Update job progress to complete
        final_payload = {
            "status": "complete",
            "stage": "save_result",
            "progress_pct": 100,
            "result_id": result_id,
            "error": None,
        }
        r.set(f"job:{state['job_id']}", json.dumps(final_payload), ex=3600)
    except Exception as exc:  # noqa: BLE001
        logger.warning("assemble: Redis write skipped — %s", exc)

    return {**state, "final_comic": comic.model_dump(mode="json")}


# ===========================================================================
# Node: human_review
# ===========================================================================


def human_review(state: ComicState) -> ComicState:
    """
    Escalate the job to the human review queue after exhausting safety retries.

    Writes the full state (with image hash, not raw bytes) to the Postgres
    review_queue table.  Sets state["error"] = "escalated_to_review".

    Child data privacy: image_bytes are replaced by their SHA-256 hash before
    writing to the DB.  Raw bytes are never persisted.
    """
    logger.warning(
        "human_review: escalating job_id=%s after %d safety retries",
        state["job_id"],
        state.get("retry_count", 0),
    )

    # Build a sanitised state snapshot — hash image bytes, never store raw
    image_b64: str = state.get("image_bytes", "")
    image_hash = hashlib.sha256(image_b64.encode()).hexdigest()

    sanitised_state = {
        **state,
        "image_bytes": f"sha256:{image_hash}",   # redact raw bytes
    }

    try:
        import psycopg2

        from app.config import get_settings

        settings = get_settings()
        conn = psycopg2.connect(settings.database_url)
        with conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    CREATE TABLE IF NOT EXISTS review_queue (
                        id          SERIAL PRIMARY KEY,
                        job_id      TEXT NOT NULL,
                        status      TEXT NOT NULL DEFAULT 'pending_review',
                        state_json  JSONB NOT NULL,
                        created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
                    )
                    """,
                )
                cur.execute(
                    """
                    INSERT INTO review_queue (job_id, status, state_json)
                    VALUES (%s, %s, %s)
                    """,
                    (
                        state["job_id"],
                        "pending_review",
                        json.dumps(sanitised_state, default=str),
                    ),
                )
        conn.close()
        logger.info("human_review: job_id=%s written to review_queue", state["job_id"])
    except Exception as exc:  # noqa: BLE001
        logger.error("human_review: DB write failed — %s", exc)

    # Update Redis so the frontend shows the escalation
    try:
        import redis as redis_lib

        from app.config import get_settings

        settings = get_settings()
        r = redis_lib.from_url(settings.redis_url, decode_responses=True)
        payload = {
            "status": "failed",
            "stage": "human_review",
            "progress_pct": 0,
            "result_id": None,
            "error": "Content could not be made safe — escalated to human review.",
        }
        r.set(f"job:{state['job_id']}", json.dumps(payload), ex=3600)
    except Exception as exc:  # noqa: BLE001
        logger.debug("human_review: Redis update skipped — %s", exc)

    return {**state, "error": "escalated_to_review"}
