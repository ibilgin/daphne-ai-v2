"""
Async Audit Logger — Sketch to Story platform, Phase 5.

Records every comic generation job (including failures) to the ``comic_audit``
Postgres table using SQLAlchemy async (asyncpg driver).

Privacy rules (CLAUDE.md critical constraints):
  - Never store raw image bytes, caption text, story text, or child name.
  - Store SHA-256 hashes ONLY.
  - user_id is an opaque UUID — never email or name.

Table definition (auto-created on first use)::

    comic_audit (
        id              UUID PRIMARY KEY DEFAULT gen_random_uuid()
        user_id         TEXT NOT NULL
        image_hash      TEXT NOT NULL
        caption_hash    TEXT NOT NULL
        story_hash      TEXT NOT NULL
        safety_verdict  TEXT NOT NULL
        safety_scores   JSONB
        stage_timings   JSONB
        model_versions  JSONB
        created_at      TIMESTAMPTZ DEFAULT now()
    )
"""

from __future__ import annotations

import logging
from datetime import datetime

from sqlalchemy import Column, Index, String, Text, select, text
from sqlalchemy.dialects.postgresql import JSONB, TIMESTAMP
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

from app.config import get_settings

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# ORM base and model
# ---------------------------------------------------------------------------


class _Base(DeclarativeBase):
    pass


class _ComicAudit(_Base):
    __tablename__ = "comic_audit"

    id = Column(
        Text,
        primary_key=True,
        server_default=text("gen_random_uuid()::text"),
    )
    user_id = Column(Text, nullable=False)
    image_hash = Column(Text, nullable=False)
    caption_hash = Column(Text, nullable=False)
    story_hash = Column(Text, nullable=False)
    safety_verdict = Column(Text, nullable=False)
    safety_scores = Column(JSONB, nullable=True)
    stage_timings = Column(JSONB, nullable=True)
    model_versions = Column(JSONB, nullable=True)
    created_at = Column(
        TIMESTAMP(timezone=True),
        server_default=text("now()"),
        nullable=False,
    )

    __table_args__ = (
        Index("ix_comic_audit_user_id", "user_id"),
        Index("ix_comic_audit_safety_verdict", "safety_verdict"),
        Index("ix_comic_audit_created_at", "created_at"),
    )


# ---------------------------------------------------------------------------
# Engine / session factory helpers
# ---------------------------------------------------------------------------


def _make_async_db_url(sync_url: str) -> str:
    """
    Convert a sync psycopg2 DATABASE_URL to an asyncpg URL.

    ``postgresql://...`` → ``postgresql+asyncpg://...``
    ``postgresql+psycopg2://...`` → ``postgresql+asyncpg://...``
    """
    url = sync_url
    if url.startswith("postgresql+psycopg2://"):
        url = url.replace("postgresql+psycopg2://", "postgresql+asyncpg://", 1)
    elif url.startswith("postgresql://"):
        url = url.replace("postgresql://", "postgresql+asyncpg://", 1)
    return url


# ---------------------------------------------------------------------------
# AuditLogger
# ---------------------------------------------------------------------------


class AuditLogger:
    """
    Async audit logger backed by Postgres via SQLAlchemy async.

    Instantiate once and reuse (the engine is shared).  The first call to any
    method will initialise the engine and create the table if it does not exist.
    """

    def __init__(self, database_url: str | None = None) -> None:
        settings = get_settings()
        raw_url = database_url or settings.database_url
        async_url = _make_async_db_url(raw_url)
        self._engine = create_async_engine(async_url, echo=False, future=True)
        self._session_factory: async_sessionmaker[AsyncSession] = async_sessionmaker(
            self._engine, expire_on_commit=False
        )
        self._table_ready = False

    async def _ensure_table(self) -> None:
        if self._table_ready:
            return
        try:
            async with self._engine.begin() as conn:
                await conn.run_sync(_Base.metadata.create_all)
            self._table_ready = True
            logger.info("AuditLogger: comic_audit table ready")
        except Exception as exc:  # noqa: BLE001
            logger.error("AuditLogger: table creation failed — %s", exc)
            raise

    async def log_job(
        self,
        *,
        job_id: str,
        user_id: str,
        image_hash: str,
        caption_hash: str,
        story_hash: str,
        safety_verdict: str,
        safety_scores: dict | None = None,
        stage_timings: dict | None = None,
        model_versions: dict | None = None,
    ) -> None:
        """
        Persist one audit record.

        All hash parameters must be SHA-256 hex strings.
        Raw image bytes, caption text, story text, and child names must NOT
        be passed here — the caller is responsible for hashing before calling.

        This method is called even when the job fails (audit incomplete jobs too).
        """
        await self._ensure_table()
        record = _ComicAudit(
            id=job_id,
            user_id=user_id,
            image_hash=image_hash,
            caption_hash=caption_hash,
            story_hash=story_hash,
            safety_verdict=safety_verdict,
            safety_scores=safety_scores or {},
            stage_timings=stage_timings or {},
            model_versions=model_versions or {},
        )
        try:
            async with self._session_factory() as session:
                async with session:
                    session.add(record)
                    await session.commit()
            logger.info(
                "AuditLogger.log_job: job_id=%s user_id=%s verdict=%s",
                job_id,
                user_id,
                safety_verdict,
            )
        except Exception as exc:  # noqa: BLE001
            logger.error("AuditLogger.log_job: failed — %s", exc)
            raise

    async def query_by_user(
        self, user_id: str, limit: int = 50
    ) -> list[dict]:
        """
        Return up to ``limit`` audit records for the given user, newest first.

        Never returns raw image bytes or child names — hashes only.
        """
        await self._ensure_table()
        async with self._session_factory() as session:
            async with session:
                stmt = (
                    select(_ComicAudit)
                    .where(_ComicAudit.user_id == user_id)
                    .order_by(_ComicAudit.created_at.desc())
                    .limit(limit)
                )
                result = await session.execute(stmt)
                rows = result.scalars().all()
                return [_row_to_dict(r) for r in rows]

    async def query_flagged(self, since: datetime) -> list[dict]:
        """
        Return all FAIL-verdict audit records created after ``since``.

        Intended for admin review of escalated safety cases.
        """
        await self._ensure_table()
        async with self._session_factory() as session:
            async with session:
                stmt = (
                    select(_ComicAudit)
                    .where(_ComicAudit.safety_verdict == "FAIL")
                    .where(_ComicAudit.created_at >= since)
                    .order_by(_ComicAudit.created_at.desc())
                )
                result = await session.execute(stmt)
                rows = result.scalars().all()
                return [_row_to_dict(r) for r in rows]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _row_to_dict(row: _ComicAudit) -> dict:
    return {
        "id": row.id,
        "user_id": row.user_id,
        "image_hash": row.image_hash,
        "caption_hash": row.caption_hash,
        "story_hash": row.story_hash,
        "safety_verdict": row.safety_verdict,
        "safety_scores": row.safety_scores,
        "stage_timings": row.stage_timings,
        "model_versions": row.model_versions,
        "created_at": row.created_at.isoformat() if row.created_at else None,
    }


# ---------------------------------------------------------------------------
# Module-level singleton
# ---------------------------------------------------------------------------
_audit_logger: AuditLogger | None = None


def get_audit_logger() -> AuditLogger:
    """Return the module-level AuditLogger singleton."""
    global _audit_logger
    if _audit_logger is None:
        _audit_logger = AuditLogger()
    return _audit_logger
