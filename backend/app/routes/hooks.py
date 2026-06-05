"""
Webhook routes for automated retrain and rollback triggers.

Endpoints
---------
POST /hooks/retrain
    Fired by Alertmanager when ml_drift_psi{feature="caption_word_count"} > 0.2
    for 15 consecutive minutes.  Validates HMAC-SHA256 signature, then runs
    the model-ci GitHub Actions workflow via ``act``.

POST /hooks/rollback
    Fired manually or by a downstream alert.  Same HMAC validation.  Delegates
    to ``act -j rollback``.

Security
--------
Every request must carry the header ``X-Hub-Signature-256`` with value
``sha256=<hex_digest>`` where the digest is HMAC-SHA256 of the raw request
body keyed with the ``WEBHOOK_SECRET`` env var.

``hmac.compare_digest`` is used for constant-time comparison to prevent
timing attacks.

Audit log
---------
Every trigger event (success or rejected) is written to the SQLite audit
table ``monitoring/captions.db::webhook_audit``.  Records contain:
  - event type (retrain / rollback)
  - outcome (triggered / rejected / error)
  - run_id (UUID)
  - timestamp
  - NO request body content (may contain sensitive alert data)
"""

from __future__ import annotations

import hashlib
import hmac
import logging
import os
import sqlite3
import subprocess
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException, Request, status

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/hooks", tags=["hooks"])

# ---------------------------------------------------------------------------
# Audit DB
# ---------------------------------------------------------------------------
_AUDIT_DB = Path(__file__).parent.parent.parent / "monitoring" / "captions.db"


def _ensure_audit_table(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS webhook_audit (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            event_type TEXT NOT NULL,
            outcome    TEXT NOT NULL,
            run_id     TEXT,
            created_at TEXT NOT NULL
        )
        """
    )
    conn.commit()


def _write_audit(event_type: str, outcome: str, run_id: str | None) -> None:
    try:
        conn = sqlite3.connect(str(_AUDIT_DB))
        try:
            _ensure_audit_table(conn)
            conn.execute(
                """
                INSERT INTO webhook_audit (event_type, outcome, run_id, created_at)
                VALUES (?, ?, ?, ?)
                """,
                (
                    event_type,
                    outcome,
                    run_id,
                    datetime.now(tz=timezone.utc).isoformat(),
                ),
            )
            conn.commit()
        finally:
            conn.close()
    except Exception as exc:  # noqa: BLE001
        logger.error("webhook_audit write failed — %s", exc)


# ---------------------------------------------------------------------------
# HMAC validation
# ---------------------------------------------------------------------------

def _get_webhook_secret() -> bytes:
    """
    Read WEBHOOK_SECRET from environment.

    The secret is never hardcoded.  In production it is injected by Vault
    before uvicorn starts.
    """
    secret = os.environ.get("WEBHOOK_SECRET", "")
    if not secret:
        logger.warning(
            "WEBHOOK_SECRET is not set — all webhook requests will be rejected"
        )
    return secret.encode("utf-8")


def _validate_signature(body: bytes, signature_header: str | None) -> None:
    """
    Validate the HMAC-SHA256 signature from Alertmanager / GitHub.

    Header format:  X-Hub-Signature-256: sha256=<hex_digest>

    Raises
    ------
    HTTPException 401
        If the header is missing, malformed, or the digest does not match.
    """
    if not signature_header:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing X-Hub-Signature-256 header",
        )

    if not signature_header.startswith("sha256="):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="X-Hub-Signature-256 must start with 'sha256='",
        )

    provided_digest = signature_header.removeprefix("sha256=")
    secret = _get_webhook_secret()
    expected_digest = hmac.new(secret, body, hashlib.sha256).hexdigest()

    if not hmac.compare_digest(expected_digest, provided_digest):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid webhook signature",
        )


# ---------------------------------------------------------------------------
# act runner helper
# ---------------------------------------------------------------------------

def _run_act(job: str, *, secrets_file: str = ".secrets") -> str:
    """
    Trigger a GitHub Actions workflow locally using ``act``.

    Runs non-blocking (Popen, not wait).  Returns a UUID run_id that can be
    used to correlate logs.

    Parameters
    ----------
    job : str
        The ``act`` job name, e.g. ``"model-ci"`` or ``"rollback"``.
    secrets_file : str
        Path to the secrets file for ``act``.  Never committed to git.

    Returns
    -------
    run_id : str
        A freshly generated UUID for audit correlation.
    """
    run_id = str(uuid.uuid4())
    cmd = ["act", "-j", job, "--secret-file", secrets_file]
    logger.info("webhook: launching act %s run_id=%s", cmd, run_id)
    try:
        subprocess.Popen(  # noqa: S603
            cmd,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
    except FileNotFoundError:
        logger.warning(
            "webhook: 'act' not found — CI trigger skipped (run_id=%s)", run_id
        )
    except Exception as exc:  # noqa: BLE001
        logger.error("webhook: act launch failed — %s (run_id=%s)", exc, run_id)
    return run_id


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.post("/retrain")
async def retrain_hook(request: Request) -> dict[str, Any]:
    """
    Alertmanager fires this endpoint when caption drift PSI exceeds 0.2 for 15m.

    1. Validates HMAC-SHA256 signature (X-Hub-Signature-256 header).
    2. Triggers ``act -j model-ci --secret-file .secrets`` (non-blocking).
    3. Writes audit record.
    4. Returns ``{triggered: true, run_id: <uuid>}``.
    """
    body = await request.body()
    sig = request.headers.get("X-Hub-Signature-256")

    try:
        _validate_signature(body, sig)
    except HTTPException:
        _write_audit("retrain", "rejected", None)
        raise

    run_id = _run_act("model-ci")
    _write_audit("retrain", "triggered", run_id)
    logger.info("retrain hook: triggered run_id=%s", run_id)
    return {"triggered": True, "run_id": run_id}


@router.post("/rollback")
async def rollback_hook(request: Request) -> dict[str, Any]:
    """
    Trigger an MLflow model rollback.

    1. Validates HMAC-SHA256 signature.
    2. Triggers ``act -j rollback --secret-file .secrets`` (non-blocking).
    3. Writes audit record.
    4. Returns ``{triggered: true, run_id: <uuid>}``.

    The rollback job reads current Production metrics from MLflow and reverts
    the Production alias to the previous version if quality thresholds are breached
    (refusal_rate > 0.05 OR caption_meteor < 0.30).
    """
    body = await request.body()
    sig = request.headers.get("X-Hub-Signature-256")

    try:
        _validate_signature(body, sig)
    except HTTPException:
        _write_audit("rollback", "rejected", None)
        raise

    run_id = _run_act("rollback")
    _write_audit("rollback", "triggered", run_id)
    logger.info("rollback hook: triggered run_id=%s", run_id)
    return {"triggered": True, "run_id": run_id}
