"""
Canonical Pydantic v2 schemas for the Sketch to Story platform.

These schemas are shared across FastAPI routes, Celery tasks, and the
Vue frontend via the job contract:
  POST /api/generate-comic → {job_id} → GET /api/jobs/{id} → GET /api/comics/{id}

Do NOT change the shape of ComicSchema, PageSchema, or PanelSchema — they are
pinned interfaces across all phases.
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict


class PanelSchema(BaseModel):
    model_config = ConfigDict(frozen=True)

    image_bytes_b64: str
    caption: str
    narration: str
    dialogue: str | None


class PageSchema(BaseModel):
    model_config = ConfigDict(frozen=True)

    page_num: int
    layout: Literal["1", "2", "3", "4"]
    panels: list[PanelSchema]


class ComicSchema(BaseModel):
    model_config = ConfigDict(frozen=True)

    id: str
    child_name: str
    cover_title: str
    created_at: datetime
    pages: list[PageSchema]


class JobStatusSchema(BaseModel):
    """Response shape for GET /api/jobs/{job_id} — polled by the Vue frontend."""

    model_config = ConfigDict(frozen=True)

    status: Literal["queued", "processing", "complete", "failed"]
    progress_pct: int
    stage: str
    result_id: str | None = None
    error: str | None = None


class EnqueueResponseSchema(BaseModel):
    """Response shape for POST /api/generate-comic."""

    model_config = ConfigDict(frozen=True)

    job_id: str
    status: Literal["queued"] = "queued"
