# Sketch to Story — AI Platform Lab

> A local AI platform that transforms children's drawings into personalised comic books.
> Built on a MacBook Pro as a hands-on study project for the **AI Platform & Governance Architect** role.

---

## What This Project Is

A child uploads a hand-drawn sketch. The platform captions it with a vision model, retrieves matching narrative styles via RAG, generates a multi-panel comic story with an LLM, runs it through a child-safety gate, and delivers it as an interactive page-flipping comic book in the browser.

Every component is designed to exercise a real concept from the job description: model registry and lifecycle, CI/CD for ML, multimodal serving, drift monitoring, responsible AI governance, feature stores, and a production-quality frontend.

**The pipeline at a glance:**

```
Child's drawing (image upload)
        │
        ▼
  Input validation         ← reject blank/NSFW images, enforce size limits
        │
        ▼
  BLIP-2 Captioner         ← vision model, loaded from MLflow Production alias
        │
        ▼
  Style RAG Retriever      ← ChromaDB + sentence-transformers, top-3 narrative styles
        │
        ▼
  Mistral Story Generator  ← Ollama, structured JSON output (panels array)
        │
        ▼
  Safety Gate              ← Detoxify, toxicity < 0.1 required; retry or escalate
        │
        ▼
  Panel Assembler          ← structures ComicSchema (cover + pages + panels)
        │
        ▼
  Vue 3 Comic Viewer       ← StPageFlip animation, PrimeVue UI, Node.js BFF
```

---

## Repository Structure

```
sketch-to-story/
│
├── README.md                          ← this file
│
├── docker-compose.yml                 ← base stack: MLflow, MinIO, PostgreSQL, Redis
│
├── backend/                           ← Python FastAPI + Celery pipeline
│   ├── app/
│   │   ├── main.py                    ← FastAPI app, route registration
│   │   ├── tasks.py                   ← Celery tasks, LangGraph agent invocation
│   │   ├── schemas.py                 ← Pydantic v2: ComicSchema, PageSchema, PanelSchema
│   │   ├── model_loader.py            ← MLflow pyfunc singleton loader
│   │   ├── config.py                  ← settings from Vault + env vars
│   │   └── routes/
│   │       ├── comics.py              ← GET /api/comics/{id}
│   │       ├── jobs.py                ← POST /api/generate-comic, GET /api/jobs/{id}
│   │       ├── hooks.py               ← POST /hooks/retrain, POST /hooks/rollback
│   │       └── internal.py            ← platform-role-only endpoints
│   ├── models/
│   │   ├── captioner.py               ← mlflow.pyfunc wrapper for BLIP-2
│   │   └── storyteller.py             ← mlflow.pyfunc wrapper for Mistral via Ollama
│   ├── rag/
│   │   ├── style_library.json         ← 60 narrative style examples across 6 genres
│   │   ├── indexer.py                 ← embed + store in ChromaDB
│   │   ├── retriever.py               ← StyleRetriever with cross-encoder re-ranking
│   │   └── story_chain.py             ← LangChain chain: caption + styles → panels JSON
│   ├── agent/
│   │   ├── state.py                   ← TypedDict ComicState
│   │   ├── nodes.py                   ← one function per LangGraph node
│   │   ├── graph.py                   ← LangGraph StateGraph with conditional edges
│   │   └── tracing.py                 ← LangSmith local trace configuration
│   ├── security/
│   │   ├── safety_gate.py             ← Detoxify-based story safety checker
│   │   ├── input_validator.py         ← image validation (size, type, blank check)
│   │   ├── audit_log.py               ← SQLAlchemy async audit table (hashes only)
│   │   ├── auth.py                    ← JWT middleware, role definitions
│   │   └── vault_client.py            ← HashiCorp Vault secret injection
│   ├── explainability/
│   │   ├── attention_viz.py           ← BLIP-2 cross-attention heatmap overlays
│   │   ├── bertscorer.py              ← BERTScore wrapper for caption quality
│   │   ├── coherence_scorer.py        ← cross-panel character continuity (spaCy)
│   │   └── plagiarism_check.py        ← RAG chunk vs generated story similarity
│   ├── monitoring/
│   │   ├── metrics_exporter.py        ← FastAPI middleware: Prometheus histograms
│   │   ├── drift_reporter.py          ← Evidently hourly drift report job
│   │   └── evidently_exporter.py      ← Prometheus exporter for Evidently PSI scores
│   ├── eval/
│   │   └── quality_gate.py            ← METEOR + BERTScore gate, auto-promotes model
│   ├── governance/
│   │   ├── governance.yaml            ← machine-readable deployment checklist
│   │   ├── gate_runner.py             ← CI gate: reads YAML, exits non-zero on failure
│   │   ├── model_card_generator.py    ← auto-generates model cards from MLflow metadata
│   │   ├── bias_audit.py              ← Fairlearn-based caption quality parity check
│   │   ├── ai_act_classification.md   ← EU AI Act risk classification for this system
│   │   └── model_cards/               ← generated per model version
│   ├── feature_store/
│   │   ├── repo/                      ← Feast feature repo
│   │   │   ├── feature_store.yaml
│   │   │   ├── drawing_stats.py       ← feature view: edge density, brightness, etc.
│   │   │   └── session_prefs.py       ← feature view: user style preferences
│   │   └── quality/
│   │       └── expectations/          ← Great Expectations suites per feature view
│   ├── scripts/
│   │   ├── register_models.py         ← initial model registration into MLflow
│   │   └── canary_check.py            ← champion-challenger METEOR comparison
│   ├── Dockerfile
│   └── requirements.txt
│
├── bff/                               ← Node.js Express backend-for-frontend
│   ├── src/
│   │   └── index.js                   ← proxy to FastAPI, HTML export endpoint
│   └── package.json
│
├── frontend/                          ← Vue 3 + PrimeVue comic viewer
│   ├── src/
│   │   ├── main.js
│   │   ├── router/index.js
│   │   ├── stores/comic.js            ← Pinia store
│   │   ├── components/
│   │   │   ├── ComicBook.vue          ← StPageFlip wrapper
│   │   │   ├── ComicPanel.vue         ← panel: image + caption + speech bubble
│   │   │   ├── CoverPage.vue
│   │   │   ├── GenerateForm.vue       ← drawing upload + style selection
│   │   │   └── JobStatus.vue          ← live progress polling
│   │   └── views/
│   │       ├── LibraryView.vue        ← comic grid
│   │       ├── ReaderView.vue         ← full-screen page-flip reader
│   │       └── GenerateView.vue       ← upload stepper
│   └── package.json
│
├── helm/
│   └── comic-platform/                ← Helm chart for k3s deployment
│       ├── Chart.yaml
│       ├── values.yaml
│       └── templates/
│           ├── deployment-api.yaml
│           ├── deployment-worker.yaml
│           ├── service-api.yaml
│           ├── ingress.yaml
│           ├── configmap.yaml
│           ├── secret.yaml
│           ├── rbac.yaml
│           └── resourcequota.yaml
│
├── keda/
│   └── scaled-object.yaml             ← autoscale workers on Redis queue depth
│
├── monitoring/
│   ├── docker-compose-monitoring.yml  ← Prometheus + Grafana + Alertmanager
│   ├── alertmanager/config.yml
│   └── grafana/dashboard.json
│
├── docs/                              ← MkDocs documentation site
│   ├── mkdocs.yml
│   ├── index.md
│   ├── architecture/
│   │   └── decisions/                 ← ADR-001 through ADR-004
│   ├── runbooks/
│   │   ├── add-style-to-rag.md
│   │   ├── rollback-model.md
│   │   ├── read-audit-log.md
│   │   └── onboard-new-engineer.md
│   └── governance/
│       ├── checklist.md
│       └── ai-act-classification.md
│
├── cookiecutter-template/             ← scaffold for new multimodal AI projects
│
└── .github/
    └── workflows/
        ├── model-ci.yml               ← lint → test → eval → gate → register → canary
        └── rollback.yml               ← triggered by webhook, reverts Production alias
```

---

## Tech Stack

| Layer | Technology | Purpose |
|---|---|---|
| Vision model | BLIP-2 (HuggingFace) | Caption child drawings |
| Story LLM | Mistral 7B via Ollama | Generate comic panel narratives |
| Model registry | MLflow 2.x | Versioning, promotion, artifact store |
| Artifact store | MinIO (S3-compatible) | Model weights, eval plots, attention maps |
| Vector store | ChromaDB | Narrative style embeddings |
| Embeddings | all-MiniLM-L6-v2 | Local, no API key required |
| Orchestration | LangGraph | Stateful agent with safety retry loop |
| RAG framework | LangChain | Style retrieval chain |
| Task queue | Celery + Redis | Async job processing |
| Safety | Detoxify | Child-safe content gate |
| Serving | FastAPI + uvicorn | REST API, Prometheus metrics |
| Kubernetes | k3s via k3d | Local OpenShift substitute |
| Autoscaling | KEDA | Scale workers on Redis queue depth |
| Secrets | HashiCorp Vault (dev) | Credential injection at startup |
| Monitoring | Prometheus + Grafana | System and ML metrics |
| Drift detection | Evidently | Caption and story quality drift |
| Feature store | Feast | Drawing features + session preferences |
| Data quality | Great Expectations | Feature materialisation gate |
| Auth | JWT | Parent / admin / platform roles |
| Frontend | Vue 3 + PrimeVue 4 | Comic library and reader UI |
| Page animation | StPageFlip | Natural book page-turn effect |
| BFF | Node.js + Express 5 | API proxy, HTML export |
| CI/CD | GitHub Actions + act | Run pipelines locally |
| Docs | MkDocs + Material | Architecture, runbooks, ADRs |

---

## Phase Overview

### Phase 1 — MLOps Foundation

**Goal:** Stand up the model registry and CI/CD pipeline. Register both core models and build quality gates that block promotion on failing eval scores.

**Modules:**
- MLflow + MinIO stack (docker-compose, pyfunc wrappers, quality gate)
- CI/CD pipeline (GitHub Actions via act, champion-challenger, rollback workflow)

**Key concepts practiced:**
- `mlflow.pyfunc.PythonModel` wrapping for heterogeneous model types
- Model Registry staging → production promotion flow
- Champion-challenger evaluation pattern
- Automated rollback via alias reversion

**Deliverables:**
- MLflow UI running at `localhost:5001`
- MinIO console at `localhost:9001`
- CI pipeline runnable with `act` from the command line
- Both models registered with quality-gated promotion

---

### Phase 2 — Model Serving API

**Goal:** Build the async serving layer that orchestrates the full pipeline. Deploy on k3s with namespace isolation and autoscaling.

**Modules:**
- FastAPI multimodal server (async jobs, Celery, Prometheus metrics)
- k3s cluster deployment (Helm chart, RBAC, KEDA ScaledObject)

**Key concepts practiced:**
- Async job pattern: submit → poll → retrieve (vs synchronous blocking)
- Structured output enforcement via Pydantic v2
- Kubernetes RBAC namespace isolation (simulating OpenShift project model)
- KEDA autoscaling on custom metrics (Redis queue depth)
- Resource quotas as a governance mechanism

**Deliverables:**
- `POST /api/generate-comic` returning `job_id`
- `GET /api/jobs/{id}` with stage-level progress
- App running on k3s at `comics.local`
- Workers autoscaling when job queue grows

---

### Phase 3 — RAG & Agentic Pipeline

**Goal:** Give the story generator style memory via RAG. Rebuild the pipeline as a LangGraph agent with safety gates, retry logic, and full observability.

**Modules:**
- Comic style RAG pipeline (ChromaDB, re-ranking, retrieval eval)
- LangGraph story agent (conditional edges, safety retry, LangSmith tracing)

**Key concepts practiced:**
- Chunking and embedding strategy for short narrative examples
- Cross-encoder re-ranking for precision improvement
- RAG evaluation: precision@3 logged to MLflow
- LangGraph stateful agent: explicit typed state, conditional routing
- Safety gate as a graph node with bounded retry loop
- Agent observability: per-node trace with input/output/latency

**Deliverables:**
- RAG pipeline with precision@3 eval logged to MLflow
- LangGraph agent with conditional safety retry (max 2 attempts)
- Human review queue for jobs that fail safety twice
- Full LangSmith trace per job

---

### Phase 4 — Monitoring, Drift & Explainability

**Goal:** Build the observability stack. Detect caption and story quality drift, trigger automated retraining, and add explainability to every model output.

**Modules:**
- Generative pipeline monitoring (Evidently, Prometheus, Grafana, alert → retrain)
- Explainability and quality audit (attention maps, BERTScore, coherence scorer)

**Key concepts practiced:**
- PSI (Population Stability Index) as a drift metric for generative outputs
- Custom Prometheus exporter pattern for ML metrics
- Alertmanager webhook → CI pipeline trigger (closing the monitoring loop)
- BLIP-2 cross-attention visualisation as explainability artifact
- Story coherence scoring as an automated quality signal
- RAG plagiarism detection via cosine similarity

**Deliverables:**
- Grafana dashboard at `localhost:3000`
- Drift alert triggers `act` retraining pipeline automatically
- Attention heatmap overlays logged as MLflow artifacts
- Coherence score included in every comic job result

---

### Phase 5 — Governance, Safety & Responsible AI

**Goal:** Build the policy layer. Child safety gate, audit logging with data minimisation, JWT RBAC, Vault secrets, and a machine-readable governance spec that gates every deployment.

**Modules:**
- Child safety and audit layer (Detoxify, Postgres audit, JWT, Vault)
- Governance gate and RAI checklist (governance.yaml, gate runner, model cards, bias audit)

**Key concepts practiced:**
- Data minimisation: store hashes, never raw child images (GDPR/KVKK alignment)
- Role-based access: parent / admin / platform roles with different permissions
- Inference audit trail: every prediction traceable with full metadata
- Vault secret injection pattern for production-safe credential management
- Machine-readable governance spec as a CI gate artifact
- Automated model card generation from MLflow run metadata
- Fairness audit: demographic parity difference across proxy groups
- EU AI Act risk classification as a documentation artifact

**Deliverables:**
- Every story generation audited in Postgres (hashes only)
- Unsafe content blocked or escalated before reaching the client
- `governance.yaml` gate blocking CI promotion on failing checks
- Auto-generated model cards for both registered models

---

### Phase 6 — Vue 3 Comic Viewer & Platform Docs

**Goal:** Replace PDF output with a Node.js + Vue 3 + PrimeVue web application featuring StPageFlip page-turn animations. Produce the documentation a platform architect actually ships.

**Modules:**
- Vue 3 + PrimeVue frontend (comic viewer, library, upload flow)
- Node.js BFF + platform documentation (ADRs, MkDocs, Cookiecutter template)

**Key concepts practiced:**
- StPageFlip integration with Vue 3 lifecycle hooks
- Pinia store as the single source of truth for async job state
- Backend-for-frontend pattern: thin Node.js proxy separating frontend from Python backend
- Architecture Decision Records: documenting why, not just what
- Cookiecutter templates as a reusable component distribution mechanism
- MkDocs as living documentation for an ML platform

**Deliverables:**
- Comic viewer at `localhost:5173` with page-flip animation
- Library view, upload stepper, and live job progress polling
- Node.js BFF at `localhost:3001`
- MkDocs site with architecture diagrams, runbooks, and governance docs
- Cookiecutter template: one command scaffolds a new multimodal AI project

---

## Local Setup Prerequisites

```bash
# Package managers
brew install python@3.11 node nvm k3d act

# Python tooling
pip install uv   # fast dependency management

# Ollama (local LLM runtime)
brew install ollama
ollama pull mistral
ollama pull llava   # optional: alternative vision model

# Kubernetes tooling
brew install kubectl helm

# Vault (dev mode only)
brew install vault
```

---

## Quickstart

```bash
# 1. Clone and enter
git clone https://github.com/yourname/sketch-to-story.git
cd sketch-to-story

# 2. Start the base platform stack
docker compose up -d
# MLflow UI:   http://localhost:5001
# MinIO:       http://localhost:9001  (user: minioadmin / minioadmin)

# 3. Register models into MLflow
cd backend
uv pip install -r requirements.txt
python scripts/register_models.py

# 4. Start Ollama
ollama serve &

# 5. Index the style library into ChromaDB
python rag/indexer.py --rebuild

# 6. Start the FastAPI server + Celery worker
uvicorn app.main:app --reload --port 8000 &
celery -A app.tasks worker --loglevel=info &

# 7. Start the monitoring stack
docker compose -f monitoring/docker-compose-monitoring.yml up -d
# Grafana: http://localhost:3000  (admin / admin)

# 8. Start the frontend
cd ../bff && npm install && npm run dev &
cd ../frontend && npm install && npm run dev
# Comic viewer: http://localhost:5173
```

---

## Running the CI Pipeline Locally

```bash
# Install act (GitHub Actions local runner)
brew install act

# Create local secrets file (never commit this)
cp .secrets.example .secrets
# Edit .secrets with your MinIO and MLflow credentials

# Run the model CI pipeline
act -j model-ci --secret-file .secrets

# Trigger a rollback manually (simulates Alertmanager webhook)
act -j rollback --secret-file .secrets
```

---

## Deploying to k3s (Local Kubernetes)

```bash
# Create local cluster with port forwarding
k3d cluster create comics-lab --port "8080:80@loadbalancer"

# Add comics.local to /etc/hosts
echo "127.0.0.1 comics.local" | sudo tee -a /etc/hosts

# Install KEDA
helm repo add kedacore https://kedacore.github.io/charts
helm install keda kedacore/keda --namespace keda --create-namespace

# Deploy the platform
helm install comic-platform ./helm/comic-platform \
  --namespace team-comics \
  --create-namespace \
  --set minio.accessKey=minioadmin \
  --set minio.secretKey=minioadmin

# Apply KEDA ScaledObject
kubectl apply -f keda/scaled-object.yaml -n team-comics

# Verify
kubectl get pods -n team-comics
```

---

## Governance Checklist

Before any model is promoted to Production, the CI pipeline runs `governance/gate_runner.py` which verifies the following checks in `governance/governance.yaml`:

| Check | Required | Description |
|---|---|---|
| `child_safety_gate_present` | ✅ | Detoxify gate wired in LangGraph agent |
| `audit_log_enabled` | ✅ | Postgres audit table receiving writes |
| `data_minimisation_verified` | ✅ | No raw images stored, hashes only |
| `input_validation_present` | ✅ | Image size, type, blank check active |
| `model_card_generated` | ✅ | Model card artifact exists in MLflow |
| `bias_audit_complete` | ✅ | Demographic parity diff < 0.15 |
| `vault_secrets_confirmed` | ✅ | No hardcoded credentials in codebase |
| `rollback_tested` | ✅ | Rollback workflow executed successfully |

Any required check with status other than `pass` or last verified more than 30 days ago will block promotion.

---

## EU AI Act Classification

This system is classified as **Limited Risk** under the EU AI Act:

- It generates creative content (comic stories) rather than making consequential decisions
- It processes data relating to children, which triggers **additional transparency obligations**
- Mitigations in place: content safety gate, data minimisation, audit trail, human review queue for escalated cases

Full classification rationale is documented in `governance/ai_act_classification.md`.

---

## Architecture Decisions

| ADR | Decision | Rationale |
|---|---|---|
| ADR-001 | BLIP-2 over GPT-4V | On-prem privacy requirement; child data must not leave the machine |
| ADR-002 | StPageFlip over turn.js | Active maintenance, Vue 3 compatible, HTML content support |
| ADR-003 | Feast over custom feature store | Point-in-time correctness out of the box; avoids temporal leakage |
| ADR-004 | governance.yaml gate | Machine-readable spec enables automated CI enforcement, not just documentation |

Full ADRs in `docs/architecture/decisions/`.

---

## Interview Talking Points

Each phase maps directly to responsibilities in the AI Platform & Governance Architect job description:

| Job Requirement | Where It's Demonstrated |
|---|---|
| MLOps architecture and standards | Phase 1: MLflow registry, pyfunc wrappers, quality gates |
| Model lifecycle management | Phase 1–2: versioning, promotion, canary, rollback |
| LLM serving infrastructure | Phase 2–3: Ollama + FastAPI, async job queue |
| RAG architecture | Phase 3: ChromaDB, re-ranking, retrieval eval |
| Agentic AI | Phase 3: LangGraph agent, tool calling, trace logging |
| GPU/inference optimisation | Phase 2: resource quotas, KEDA scaling, latency profiling |
| Monitoring and observability | Phase 4: Evidently drift, Prometheus, Grafana, alert loop |
| Explainability | Phase 4: attention maps, BERTScore, coherence scoring |
| Responsible AI and governance | Phase 5: safety gate, audit log, governance.yaml, model cards |
| Security and access control | Phase 5: JWT RBAC, Vault, data minimisation |
| Reusable component standards | Phase 6: Cookiecutter template, packaged hooks |
| Technical documentation | Phase 6: ADRs, MkDocs, runbooks, onboarding guide |
| OpenShift / Kubernetes | Phase 2: k3s (same API surface), Helm, RBAC, resource quotas |

---

## Notes on MacBook Pro as a Lab

This project runs entirely locally. The only honest gap versus the full job description is multi-node GPU orchestration (tensor parallelism across a GPU cluster). Every architectural pattern — namespace isolation, resource quotas, RBAC, operator pattern, serving SLAs — translates directly to OpenShift.

Ollama runs Mistral 7B comfortably on Apple Silicon (M1/M2/M3) using Metal acceleration. BLIP-2 runs on CPU for development purposes; for faster iteration, the `blip-image-captioning-base` variant is significantly lighter than the full model.

If inference latency becomes a bottleneck during development, replace the BLIP-2 call with the Claude API (`claude-sonnet-4-20250514` with vision input) using the same `mlflow.pyfunc` interface — the rest of the pipeline is unchanged.