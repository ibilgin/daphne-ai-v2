Build an async FastAPI comic generation backend with Celery task queue.

Create:
1. app/main.py — FastAPI app with routes:
   - POST /api/generate-comic: accepts multipart/form-data (file: image, child_name: str, style: str). Validates image (type, size < 5MB, not blank via std deviation check). Enqueues Celery task, returns {job_id: uuid, status: "queued"}.
   - GET /api/jobs/{job_id}: returns {status: queued|processing|complete|failed, progress_pct: int, stage: str, result_id?: str}.
   - GET /api/comics/{comic_id}: returns full ComicSchema JSON.
   - GET /metrics: Prometheus exposition format with counters/histograms for: pipeline_duration_seconds (labelled by stage), jobs_total (labelled by status), queue_depth_gauge.

2. app/tasks.py — Celery task generate_comic(job_id, image_bytes, child_name, style). Stages with progress updates: (10%) load_models → (30%) caption → (60%) retrieve_style → (80%) generate_story → (95%) structure_panels → (100%) save_result. Updates Redis with stage + progress_pct at each step.

3. app/schemas.py — Pydantic v2 models: ComicSchema {id, child_name, cover_title, created_at, pages: list[PageSchema]}. PageSchema {page_num, layout: "1"|"2"|"3"|"4", panels: list[PanelSchema]}. PanelSchema {image_bytes_b64: str, caption: str, narration: str, dialogue: str | None}.

4. app/model_loader.py — singleton that loads mlflow.pyfunc models from Production alias at startup, with retry logic.

5. docker-compose.yml extension adding: fastapi (port 8000), celery-worker (2 replicas), redis (port 6379).

Include Dockerfile with multi-stage build.