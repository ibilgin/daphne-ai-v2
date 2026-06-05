# Sketch to Story — AI Platform Lab

A local AI platform that transforms children's drawings into personalised comic books.
Study project for the AI Platform & Governance Architect role, covering the full MLOps SDLC across 6 phases.

## Development Phases (implement in order)

| Phase | Focus | Key Modules |
|-------|-------|-------------|
| 1 | MLOps Foundation | MLflow, MinIO, pyfunc wrappers, quality gates, CI/CD |
| 2 | Model Serving API | FastAPI, Celery, Docker, k3s, Helm, KEDA |
| 3 | RAG & Agentic Pipeline | ChromaDB, LangChain, LangGraph, LangSmith |
| 4 | Monitoring & Drift | Prometheus, Evidently, Grafana, alert→retrain loop |
| 5 | Governance & Safety | Detoxify, JWT RBAC, Vault, audit log, governance.yaml |
| 6 | Frontend & Docs | Vue 3 + PrimeVue 4, Node.js BFF, MkDocs, Cookiecutter |

Phase docs live in `docs/phase{N}/`. Read them before implementing.

## Services & Ports

| Service | Port | Start command |
|---------|------|---------------|
| MLflow UI | 5001 | `docker compose up -d` |
| MinIO Console | 9001 | `docker compose up -d` (minioadmin/minioadmin) |
| PostgreSQL | 5432 | `docker compose up -d` |
| Redis | 6379 | `docker compose up -d` |
| FastAPI | 8000 | `cd backend && uvicorn app.main:app --reload --port 8000` |
| Celery worker | — | `cd backend && celery -A app.tasks worker --loglevel=info` |
| Ollama | 11434 | `ollama serve` |
| Grafana | 3000 | `docker compose -f monitoring/docker-compose-monitoring.yml up -d` |
| Prometheus | 9090 | same monitoring compose |
| Evidently exporter | 9101 | standalone process in monitoring/ |
| Node.js BFF | 3001 | `cd bff && npm run dev` |
| Vue frontend | 5173 | `cd frontend && npm run dev` |
| k3s ingress | 8080 | k3d cluster, comics.local |

## Python Environment

```bash
cd backend
uv pip install -r requirements.txt   # preferred
```

Python 3.11 required. All backend work happens inside `backend/`.

## Critical Constraints — Never Violate

1. **Child data privacy**: Store SHA-256 hashes only in audit log. Never persist raw image bytes to disk or DB.
2. **Safety gate**: Every generated story must pass Detoxify before reaching the client. Toxicity < 0.1, identity_attack < 0.05 per panel.
3. **Model quality**: Captioner promotion requires METEOR > 0.35 AND BERTScore F1 > 0.75.
4. **Governance gate**: `backend/governance/gate_runner.py` must exit 0 before any Production alias update.
5. **Secrets**: No hardcoded credentials anywhere. Use Vault (dev mode) via `vault_client.py`. Use `.secrets` for `act` — never commit it.
6. **EU AI Act**: This system is classified Limited Risk with additional transparency obligations (children's data). See `docs/governance/ai-act-classification.md`.

## Key Interfaces — Preserve Across All Phases

- `mlflow.pyfunc.PythonModel` — all model wrappers must implement this interface
- `ComicSchema / PageSchema / PanelSchema` — Pydantic v2 canonical schema in `backend/app/schemas.py`
- `ComicState` TypedDict — LangGraph agent state in `backend/agent/state.py`
- Job contract: `POST /api/generate-comic` → `{job_id}` → `GET /api/jobs/{id}` → `GET /api/comics/{id}`

## Testing

```bash
cd backend && pytest tests/ -v
pytest tests/test_captioner.py -v
pytest tests/test_storyteller.py -v
```

## Local CI with act

```bash
act -j model-ci --secret-file .secrets    # full model CI pipeline
act -j rollback --secret-file .secrets   # simulate rollback webhook
```

## GitHub Branching Strategy

- `main` — stable, always governance-checked
- `phase/1-mlops`, `phase/2-serving`, ... `phase/6-frontend` — one branch per phase
- Merge via PR after phase is complete and CI passes
- Never force-push `main`

## Useful Custom Commands

| Command | Purpose |
|---------|---------|
| `/phase-status` | Show what's built vs pending per phase |
| `/implement-phase N` | Scaffold and implement phase N |
| `/fix-bug <description>` | Diagnose, route to specialist, patch, test, commit |
| `/feature <description>` | Design, implement across all layers, open PR |
| `/work-issue N` | Fetch GitHub issue, implement it, open a closing PR |
| `/github-push` | Commit and push current work to GitHub |
| `/run-ci` | Run model-ci pipeline locally with act |
| `/model-promote` | Promote model through staging → production |
| `/model-rollback` | Trigger rollback workflow |
| `/governance-check` | Run governance gate runner |
| `/health-check` | Check all local services |
| `/deploy-local` | Full k3s deployment |
| `/rag-rebuild` | Rebuild ChromaDB index and run RAG eval |
