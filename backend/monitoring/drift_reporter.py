"""
Evidently drift reporter for the caption distribution.

Scheduled usage (cron or background thread)
-------------------------------------------
    python -m monitoring.drift_reporter          # one-shot
    # or import and call:
    from monitoring.drift_reporter import run_drift_report
    run_drift_report()

Database
--------
SQLite file: backend/monitoring/captions.db
Table: caption_log
  job_id           TEXT PRIMARY KEY
  caption          TEXT NOT NULL
  caption_embedding BLOB NOT NULL   (serialised numpy float32 array)
  created_at       TEXT NOT NULL    (ISO-8601 UTC)

Privacy note
------------
Only caption text and derived word count are stored.  No image bytes,
no child names, no PII of any kind.

Evidently version note
----------------------
This file targets evidently>=0.4.  The JSON schema changed significantly
between 0.3 and 0.4.  Always use report.as_dict() for programmatic access;
never parse the raw JSON by position.

Reports saved to
----------------
./reports/drift_{timestamp}.json  (relative to this file's parent directory)
"""

from __future__ import annotations

import json
import logging
import os
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
_MODULE_DIR = Path(__file__).parent
DB_PATH = _MODULE_DIR / "captions.db"
REPORTS_DIR = _MODULE_DIR / "reports"

# ---------------------------------------------------------------------------
# Minimum sample sizes
# ---------------------------------------------------------------------------
MIN_REFERENCE_ROWS = 10   # relaxed minimum for dev; prod should be 100
MIN_CURRENT_ROWS = 10


# ---------------------------------------------------------------------------
# Database helpers
# ---------------------------------------------------------------------------

def _ensure_schema(conn: sqlite3.Connection) -> None:
    """Create caption_log table if it doesn't exist."""
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS caption_log (
            job_id            TEXT PRIMARY KEY,
            caption           TEXT NOT NULL,
            caption_embedding BLOB,
            created_at        TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now'))
        )
        """
    )
    conn.commit()


def log_caption(job_id: str, caption: str, embedding: np.ndarray | None = None) -> None:
    """
    Persist a caption (and optionally its embedding) to the SQLite log.

    Called by app/tasks.py at task completion.

    Privacy: only caption text stored — no image bytes, no child names.
    """
    conn = sqlite3.connect(str(DB_PATH))
    try:
        _ensure_schema(conn)
        embedding_blob = embedding.tobytes() if embedding is not None else None
        conn.execute(
            """
            INSERT OR REPLACE INTO caption_log (job_id, caption, caption_embedding)
            VALUES (?, ?, ?)
            """,
            (job_id, caption, embedding_blob),
        )
        conn.commit()
        logger.debug("caption_log: written job_id=%s", job_id)
    finally:
        conn.close()


def _load_captions(conn: sqlite3.Connection, *, oldest_first: bool, limit: int) -> pd.DataFrame:
    """Load up to `limit` rows, sorted by created_at."""
    order = "ASC" if oldest_first else "DESC"
    rows = conn.execute(
        f"SELECT job_id, caption, caption_embedding, created_at "
        f"FROM caption_log ORDER BY created_at {order} LIMIT ?",
        (limit,),
    ).fetchall()

    records: list[dict[str, Any]] = []
    for job_id, caption, embedding_blob, created_at in rows:
        word_count = len(caption.split()) if caption else 0
        rec: dict[str, Any] = {
            "job_id": job_id,
            "caption": caption,
            "caption_word_count": float(word_count),
            "created_at": created_at,
        }
        if embedding_blob:
            try:
                emb = np.frombuffer(embedding_blob, dtype=np.float32)
                rec["caption_embedding"] = emb
            except Exception:  # noqa: BLE001
                rec["caption_embedding"] = None
        else:
            rec["caption_embedding"] = None
        records.append(rec)

    return pd.DataFrame(records)


# ---------------------------------------------------------------------------
# Embedding helpers
# ---------------------------------------------------------------------------

def _compute_mean_cosine_distance(
    ref_df: pd.DataFrame,
    cur_df: pd.DataFrame,
) -> float | None:
    """
    Compute the mean pairwise cosine distance between reference and current
    caption embeddings.

    Returns None if embeddings are unavailable or the computation fails.
    """
    try:
        ref_embs = ref_df["caption_embedding"].dropna().tolist()
        cur_embs = cur_df["caption_embedding"].dropna().tolist()

        if not ref_embs or not cur_embs:
            logger.debug("embedding distance: no embeddings available — skipped")
            return None

        ref_matrix = np.vstack(ref_embs).astype(np.float32)
        cur_matrix = np.vstack(cur_embs).astype(np.float32)

        # L2-normalise each row
        ref_norms = np.linalg.norm(ref_matrix, axis=1, keepdims=True)
        cur_norms = np.linalg.norm(cur_matrix, axis=1, keepdims=True)
        ref_normed = ref_matrix / np.maximum(ref_norms, 1e-8)
        cur_normed = cur_matrix / np.maximum(cur_norms, 1e-8)

        # Mean cosine similarity across all pairs
        sim_matrix = ref_normed @ cur_normed.T  # shape (|ref|, |cur|)
        mean_cosine_sim = float(sim_matrix.mean())
        mean_cosine_distance = 1.0 - mean_cosine_sim
        logger.debug("embedding distance: %.4f", mean_cosine_distance)
        return mean_cosine_distance
    except Exception as exc:  # noqa: BLE001
        logger.warning("embedding distance computation failed — %s", exc)
        return None


def _generate_embeddings_if_missing(df: pd.DataFrame) -> pd.DataFrame:
    """
    Compute sentence embeddings for rows that have no stored embedding.

    Uses all-MiniLM-L6-v2 (same model as RAG phase).  Only called when
    the DB rows lack pre-computed embeddings.
    """
    missing_mask = df["caption_embedding"].isna()
    if not missing_mask.any():
        return df

    try:
        from sentence_transformers import SentenceTransformer

        model = SentenceTransformer("all-MiniLM-L6-v2")
        captions_to_embed = df.loc[missing_mask, "caption"].tolist()
        embeddings = model.encode(captions_to_embed, show_progress_bar=False)
        df = df.copy()
        for idx, emb in zip(df.index[missing_mask], embeddings):
            df.at[idx, "caption_embedding"] = emb.astype(np.float32)
        logger.debug("generated embeddings for %d rows", int(missing_mask.sum()))
    except Exception as exc:  # noqa: BLE001
        logger.warning("embedding generation skipped — %s", exc)

    return df


# ---------------------------------------------------------------------------
# Main drift report function
# ---------------------------------------------------------------------------

def run_drift_report(
    db_path: Path | str | None = None,
    reports_dir: Path | str | None = None,
    reference_limit: int = 100,
    current_limit: int = 100,
) -> Path | None:
    """
    Load production captions, compare against the reference baseline, generate
    an Evidently DataDriftReport and save it as JSON.

    Parameters
    ----------
    db_path : Path or str, optional
        Override the default SQLite database path.
    reports_dir : Path or str, optional
        Override the default reports output directory.
    reference_limit : int
        Number of oldest captions to use as reference (baseline).
    current_limit : int
        Number of newest captions to use as current production window.

    Returns
    -------
    Path to the saved JSON report, or None if the run could not complete.
    """
    db_path = Path(db_path) if db_path else DB_PATH
    reports_dir = Path(reports_dir) if reports_dir else REPORTS_DIR
    reports_dir.mkdir(parents=True, exist_ok=True)

    # -----------------------------------------------------------------------
    # Load data
    # -----------------------------------------------------------------------
    if not db_path.exists():
        logger.warning("drift_reporter: DB not found at %s — skipping", db_path)
        return None

    conn = sqlite3.connect(str(db_path))
    try:
        _ensure_schema(conn)
        ref_df = _load_captions(conn, oldest_first=True, limit=reference_limit)
        cur_df = _load_captions(conn, oldest_first=False, limit=current_limit)
    finally:
        conn.close()

    if len(ref_df) < MIN_REFERENCE_ROWS:
        logger.warning(
            "drift_reporter: only %d reference rows (min %d) — skipping",
            len(ref_df),
            MIN_REFERENCE_ROWS,
        )
        return None

    if len(cur_df) < MIN_CURRENT_ROWS:
        logger.warning(
            "drift_reporter: only %d current rows (min %d) — skipping",
            len(cur_df),
            MIN_CURRENT_ROWS,
        )
        return None

    logger.info(
        "drift_reporter: reference=%d rows, current=%d rows",
        len(ref_df),
        len(cur_df),
    )

    # -----------------------------------------------------------------------
    # Generate embeddings where missing
    # -----------------------------------------------------------------------
    ref_df = _generate_embeddings_if_missing(ref_df)
    cur_df = _generate_embeddings_if_missing(cur_df)

    # -----------------------------------------------------------------------
    # Compute mean cosine distance (custom metric)
    # -----------------------------------------------------------------------
    mean_cosine_dist = _compute_mean_cosine_distance(ref_df, cur_df)

    # -----------------------------------------------------------------------
    # Evidently DataDriftReport on caption_word_count
    # -----------------------------------------------------------------------
    try:
        from evidently.report import Report
        from evidently.metric_preset import DataDriftPreset
        from evidently.metrics import ColumnDriftMetric

        # Work only with the numerical feature columns
        ref_features = ref_df[["caption_word_count"]].reset_index(drop=True)
        cur_features = cur_df[["caption_word_count"]].reset_index(drop=True)

        report = Report(metrics=[
            DataDriftPreset(),
            ColumnDriftMetric(column_name="caption_word_count"),
        ])
        report.run(reference_data=ref_features, current_data=cur_features)
        report_dict = report.as_dict()
    except Exception as exc:  # noqa: BLE001
        logger.error("drift_reporter: Evidently report failed — %s", exc)
        # Build a minimal fallback report so the exporter still has something to read
        report_dict = {
            "evidently_fallback": True,
            "error": str(exc),
        }

    # -----------------------------------------------------------------------
    # Augment with custom embedding distance metric
    # -----------------------------------------------------------------------
    report_dict["custom_metrics"] = {
        "caption_embedding_cosine_distance": {
            "mean": mean_cosine_dist,
            "reference_rows": len(ref_df),
            "current_rows": len(cur_df),
        }
    }

    # -----------------------------------------------------------------------
    # Save JSON report
    # -----------------------------------------------------------------------
    timestamp = datetime.now(tz=timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    report_path = reports_dir / f"drift_{timestamp}.json"
    report_path.write_text(json.dumps(report_dict, default=str), encoding="utf-8")
    logger.info("drift_reporter: saved report → %s", report_path)
    return report_path


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    path = run_drift_report()
    if path:
        print(f"Report saved: {path}")
    else:
        print("Report generation skipped — not enough data.")
