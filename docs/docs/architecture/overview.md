# Architecture Overview

The Sketch to Story platform follows a microservices architecture with a clear separation between the frontend, BFF, API, and ML infrastructure layers.

## Request Flow

```mermaid
sequenceDiagram
    participant U as User
    participant FE as Vue Frontend
    participant BFF as Node.js BFF
    participant API as FastAPI
    participant CW as Celery Worker
    participant ML as MLflow / MinIO
    participant DB as PostgreSQL / Redis

    U->>FE: Upload drawing + metadata
    FE->>BFF: POST /api/generate-comic
    BFF->>API: proxy POST /api/generate-comic
    API->>DB: Enqueue job (Redis)
    API-->>BFF: {job_id, status: queued}
    BFF-->>FE: {job_id}

    loop Poll every 2s
        FE->>BFF: GET /api/jobs/{job_id}
        BFF->>API: proxy GET /api/jobs/{job_id}
        API->>DB: Read job status
        API-->>FE: {status, progress_pct, stage}
    end

    CW->>ML: Load captioner model
    CW->>CW: Caption drawing
    CW->>CW: Generate story (RAG)
    CW->>CW: Render comic panels
    CW->>CW: Safety gate (Detoxify)
    CW->>DB: Write comic to Postgres
    CW->>DB: Update job status=complete

    FE->>BFF: GET /api/comics/{id}
    BFF->>API: proxy GET /api/comics/{id}
    API-->>FE: ComicSchema JSON
    FE->>U: Render comic reader
```

## Component Responsibilities

| Component | Responsibility |
|-----------|---------------|
| **Vue Frontend** | Comic reader (StPageFlip), generation wizard, library view |
| **Node.js BFF** | CORS, proxy to FastAPI, HTML export, static file serving |
| **FastAPI** | REST API, job enqueueing, auth (JWT), audit logging |
| **Celery** | Async task execution: caption → story → render → safety |
| **MLflow** | Model registry, experiment tracking, pyfunc serving |
| **MinIO** | Artefact storage for model weights and generated assets |
| **ChromaDB** | Vector store for RAG style library |
| **Redis** | Job queue (Celery broker) and result backend |
| **PostgreSQL** | Comic storage, audit log, job metadata |
| **Prometheus + Grafana** | Metrics collection and alerting |
