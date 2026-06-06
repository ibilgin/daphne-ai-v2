# Sketch to Story — Architecture & How It Works

## What the system does

A child uploads a drawing. The platform turns it into a personalised 4-panel comic book:
caption the drawing → retrieve style examples → write the story → check safety → render the comic.

---

## Services at a glance

| Service | Role | Port |
|---|---|---|
| **Vue 3 Frontend** | Upload form, comic reader, library | 5173 |
| **Node.js BFF** | Proxy + HTML export | 3001 |
| **FastAPI** | REST API, job enqueueing, auth | 8000 |
| **Celery Worker** | Runs the LangGraph agent pipeline | — |
| **Redis** | Celery broker + job/comic state store | 6379 |
| **MLflow** | Model registry + experiment tracking | 5001 |
| **MinIO** | Artifact storage for MLflow | 9000/9001 |
| **PostgreSQL** | MLflow backend + audit log | 5432 |
| **Ollama** | Runs Mistral LLM on the host | 11434 |
| **ChromaDB** | Vector store for style library (RAG) | — (in-process) |

---

## The two registered models

### 1. Captioner — `salesforce/blip-image-captioning-base`

Wrapped in `backend/models/captioner.py` as an `mlflow.pyfunc.PythonModel`.

| | |
|---|---|
| **Input** | `pd.DataFrame` with column `image_bytes` (base64 string) |
| **Output** | `{"caption": str, "latency_ms": float}` |
| **Inference** | BLIP `BlipProcessor` + `BlipForConditionalGeneration`, up to 50 new tokens |
| **Device** | MPS on Apple Silicon, CPU elsewhere |
| **Dev stub** | Returns `"A child's colorful drawing showing a cheerful scene..."` |

### 2. Storyteller — `mistral` via Ollama

Wrapped in `backend/models/storyteller.py` as an `mlflow.pyfunc.PythonModel`.

| | |
|---|---|
| **Input** | `pd.DataFrame` with `caption`, `style_examples` (JSON), `panel_count` |
| **Output** | `{"panels": [{"panel": int, "narration": str, "dialogue": str\|null}]}` |
| **Inference** | HTTP POST to `http://host.docker.internal:11434/api/chat` (Ollama REST) |
| **Dev stub** | Returns 4 pre-written mock panels without calling Ollama |

Both models are registered in MLflow under the **`Production`** alias. The app only ever loads the `Production` alias — it never picks up a `Staging` model at runtime.

---

## How MLflow is used

```mermaid
sequenceDiagram
    participant Dev as Developer
    participant Script as register_models.py
    participant MLflow as MLflow Registry
    participant MinIO as MinIO (S3)
    participant Gate as quality_gate.py
    participant App as FastAPI / Celery

    Dev->>Script: python scripts/register_models.py
    Script->>MLflow: mlflow.start_run()
    Script->>MLflow: mlflow.pyfunc.log_model(captioner / storyteller)
    MLflow->>MinIO: store model artifacts in s3://mlflow-artifacts/
    Script->>MLflow: set alias → "Staging"

    Dev->>Gate: python eval/quality_gate.py
    Gate->>MLflow: load model @ Staging alias
    Gate->>Gate: run METEOR + BERTScore F1 evaluation
    alt METEOR > 0.35 AND BERTScore F1 > 0.75
        Gate->>MLflow: set alias → "Production"
        Gate-->>Dev: exit 0 ✓
    else below threshold
        Gate-->>Dev: exit 1 ✗
    end

    App->>MLflow: load_model("models:/captioner@Production")
    MLflow->>MinIO: download artifacts
    MLflow-->>App: pyfunc model instance
```

**Key MLflow concepts used:**

- **Run**: every `register_models.py` call starts a run, logs params (`model_type`, `stub`), and logs the model artifact.
- **Registered model**: named `captioner` and `storyteller` in the registry.
- **Alias**: `Staging` → under evaluation; `Production` → what the app serves. The quality gate promotes Staging → Production.
- **`mlflow.pyfunc.load_model("models:/captioner@Production")`**: the lazy-loading singleton in `model_loader.py` calls this on first use in each process.

---

## End-to-end comic generation

```mermaid
sequenceDiagram
    actor User
    participant FE as Vue Frontend
    participant BFF as Node.js BFF
    participant API as FastAPI
    participant Redis
    participant Celery as Celery Worker
    participant MLflow
    participant Chroma as ChromaDB
    participant Ollama
    participant Detox as Detoxify

    User->>FE: upload drawing + child name + style
    FE->>BFF: POST /api/generate-comic (multipart)
    BFF->>API: proxy → POST /api/generate-comic
    API->>API: validate JWT (parent role required)
    API->>API: validate image (PIL magic bytes, size, not blank)
    API->>API: hash image SHA-256 (never store raw bytes)
    API->>Redis: SET job:{id} = {status: queued}
    API->>Celery: generate_comic.delay(job_id, image_b64, ...)
    API-->>FE: 202 {job_id}

    loop Poll every 2 s
        FE->>API: GET /api/jobs/{job_id}
        API->>Redis: GET job:{id}
        API-->>FE: {status, stage, progress_pct}
    end

    Note over Celery: LangGraph agent starts

    Celery->>Redis: progress 10% — load_models
    Celery->>MLflow: get_captioner() → load Production model (lazy, once per process)

    Celery->>Redis: progress 20% — caption
    Celery->>MLflow: captioner.predict(image_b64)
    MLflow-->>Celery: {caption: "..."}

    Celery->>Redis: progress 40% — retrieve_style
    Celery->>Chroma: embed caption, cosine search top-10
    Chroma-->>Celery: candidate style examples
    Celery->>Celery: cross-encoder rerank → top-3 examples

    Celery->>Redis: progress 60% — generate_story
    Celery->>Ollama: POST /api/generate (mistral, format=json)
    Ollama-->>Celery: {panels: [{narration, dialogue}, ...]}

    Celery->>Redis: progress 75% — check_safety
    Celery->>Detox: Detoxify("original").predict(all panel texts)
    alt toxicity < 0.1 AND identity_attack < 0.05
        Detox-->>Celery: PASS
        Celery->>Redis: progress 90% — structure_panels
        Celery->>Redis: SET comic:{result_id} = ComicSchema JSON
        Celery->>Redis: progress 100% — complete, result_id=...
        FE->>API: GET /api/comics/{result_id}
        API-->>FE: ComicSchema JSON
        FE->>User: render page-flip comic book
    else fails threshold (up to 2 retries)
        Detox-->>Celery: FAIL
        Celery->>Ollama: regenerate with safety augmentation in prompt
    else exhausted 2 retries
        Celery->>Redis: status=failed, stage=human_review
        FE-->>User: "escalated to human review"
    end
```

---

## LangGraph agent topology

```mermaid
flowchart TD
    START([START]) --> A[analyse_drawing\ncaption image with BLIP]
    A --> B[retrieve_style\nChromaDB cosine + cross-encoder rerank]
    B --> C[generate_panels\nOllama Mistral → JSON panels]
    C --> D{check_safety\nDetoxify per panel}
    D -->|PASS| E[assemble\nbuild ComicSchema, write to Redis]
    D -->|FAIL + retry_count < 2| C
    D -->|FAIL + retry_count ≥ 2| F[human_review\nescalate, write to review_queue table]
    E --> END_A([END])
    F --> END_B([END])
```

---

## RAG pipeline (retrieve_style node)

```mermaid
sequenceDiagram
    participant Node as retrieve_style node
    participant ST as SentenceTransformer\nall-MiniLM-L6-v2
    participant Chroma as ChromaDB\nnarrative_styles collection
    participant CE as CrossEncoder\nms-marco-MiniLM-L-6-v2

    Node->>ST: encode(caption)
    ST-->>Node: 384-dim embedding
    Node->>Chroma: query(embedding, where={age_group: ...}, n_results=10)
    Chroma-->>Node: 10 candidate style texts + metadata
    Node->>CE: predict([(caption, text) for each candidate])
    CE-->>Node: relevance scores
    Node->>Node: sort by score, take top-3
    Node-->>Node: state.style_examples = [text, text, text]
```

The style library lives in `backend/rag/style_library.json` — 30+ narrative style examples tagged with `style`, `age_group`, and `tone`. Build the index once with `make rag-index`.

---

## Model promotion quality gate

```mermaid
flowchart LR
    A[New model trained\nregistered @ Staging] --> B{quality_gate.py}
    B --> C[Load Staging model from MLflow]
    C --> D[Run on 20 test images]
    D --> E{METEOR > 0.35\nAND BERTScore F1 > 0.75?}
    E -->|Yes| F[Set Production alias\nexit 0]
    E -->|No| G[Log failing metrics\nexit 1 — no promotion]
```

The CI workflow (`.github/workflows/model-ci.yml`) runs this gate automatically on every push to a phase branch. Only models that pass can receive the `Production` alias.

---

## Data privacy rules (enforced in code)

| Rule | Where enforced |
|---|---|
| Raw image bytes never written to disk or DB | `main.py` hashes on arrival; `tasks.py` passes only base64 over Celery |
| Only SHA-256 hashes in audit log | `_audit_job()` in `tasks.py`, `human_review` node |
| Safety gate on every panel | `check_safety` node — toxicity < 0.1, identity_attack < 0.05 |
| JWT required for every generation request | `require_role("parent")` on `POST /api/generate-comic` |
| Governance gate before Production promotion | `gate_runner.py` must exit 0 |

---

## Developer quick-start

```bash
# 1. Start everything
make up

# 2. Register stub models (no real weights needed)
make seed

# 3. Build the RAG index (once)
make rag-index

# 4. Open the UI
open http://localhost:5173
```

To use real models, pull Mistral and register the real wrappers:

```bash
ollama pull mistral
cd backend && python scripts/register_models.py
python eval/quality_gate.py   # promotes to Production if metrics pass
```
