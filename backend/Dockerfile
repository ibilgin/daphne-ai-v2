# ============================================================
# Sketch to Story — backend Dockerfile (multi-stage)
# ============================================================
# Stage 1 (builder): install Python dependencies into a venv
# Stage 2 (runtime): copy venv + source, run as non-root user
#
# Both the FastAPI server and the Celery worker use this image.
# Override CMD in docker-compose / Kubernetes to start the worker:
#   celery -A app.tasks.celery_app worker --loglevel=info
# ============================================================

# ---------------------------------------------------------------------------
# Stage 1 — builder
# ---------------------------------------------------------------------------
FROM python:3.11-slim AS builder

WORKDIR /build

# Install uv (fast pip replacement)
RUN pip install --no-cache-dir uv

# Copy dependency manifest first to exploit Docker layer caching.
COPY requirements.txt .

# Create a venv and install all dependencies into it.
RUN uv venv /opt/venv && \
    . /opt/venv/bin/activate && \
    uv pip install --no-cache -r requirements.txt

# ---------------------------------------------------------------------------
# Stage 2 — runtime
# ---------------------------------------------------------------------------
FROM python:3.11-slim AS runtime

# Non-root user for security.
RUN groupadd --gid 1001 appgroup && \
    useradd --uid 1001 --gid appgroup --shell /bin/bash --create-home appuser

# Copy the venv from the builder stage.
COPY --from=builder /opt/venv /opt/venv

# Make the venv the active Python environment.
ENV PATH="/opt/venv/bin:$PATH" \
    PYTHONPATH=/app \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

# Copy application source.
COPY . .

# Pre-create writable directories for non-root user.
RUN mkdir -p /app/chroma_db && chown -R appuser:appgroup /app/chroma_db

# Switch to non-root user.
USER appuser

EXPOSE 8000

# Default: run the FastAPI server.
# Override CMD in docker-compose / Kubernetes for the Celery worker.
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
