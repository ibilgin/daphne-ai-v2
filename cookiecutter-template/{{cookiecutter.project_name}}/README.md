# {{ cookiecutter.project_name }}

A multimodal AI platform generated from the **Sketch to Story** Cookiecutter template.

**Author**: {{ cookiecutter.author }}  
**Python**: {{ cookiecutter.python_version }}

---

## Architecture

```
Vue 3 Frontend → Node.js BFF → FastAPI (port {{ cookiecutter.fastapi_port }}) → Celery Workers
                                      ↓
                         MLflow (port {{ cookiecutter.mlflow_port }}) + MinIO + Redis + PostgreSQL
```

## Quick Start

### 1. Start infrastructure

```bash
docker compose up -d
```

Services started:
- MLflow UI: http://localhost:{{ cookiecutter.mlflow_port }}
- MinIO Console: http://localhost:9001 (minioadmin / minioadmin)
- PostgreSQL: localhost:5432
- Redis: localhost:6379

### 2. Set up Python environment

```bash
python{{ cookiecutter.python_version }} -m venv .venv
source .venv/bin/activate
pip install uv
uv pip install -r requirements.txt
cp .env.example .env
```

### 3. Start the API

```bash
uvicorn src.main:app --reload --port {{ cookiecutter.fastapi_port }}
```

API docs: http://localhost:{{ cookiecutter.fastapi_port }}/docs

### 4. Start a Celery worker

```bash
celery -A src.tasks worker --loglevel=info
```

### 5. Start the frontend

```bash
cd frontend
npm install
npm run dev
```

Frontend: http://localhost:5173

---

## Model Development

### Implement the captioner

Edit `src/models/captioner_stub.py` — replace the `predict` stub with your model.

### Implement the storyteller

Edit `src/models/storyteller_stub.py` — replace the `predict` stub with your model.

### Run the quality gate

```bash
python3 governance/gate_runner.py
```

All checks in `governance/governance.yaml` with `required: true` must have `status: pass` before promoting a model to Production.

### Register a model

```bash
python3 scripts/register_model.py
```

---

## Governance

Governance checks are defined in `governance/governance.yaml`. All required checks default to `status: pending` — update each to `status: pass` after implementing and verifying the corresponding control.

See the [Governance Checklist](docs/governance/checklist.md) for descriptions of each check.

---

## Running CI Locally

```bash
# Install act (GitHub Actions local runner)
brew install act  # macOS

# Run the model CI pipeline
act -j model-ci --secret-file .secrets
```

---

## Project Structure

```
{{ cookiecutter.project_name }}/
├── docker-compose.yml          # MLflow, MinIO, Postgres, Redis
├── src/
│   ├── models/
│   │   ├── captioner_stub.py   # mlflow.pyfunc captioner stub
│   │   └── storyteller_stub.py # mlflow.pyfunc storyteller stub
│   ├── eval/                   # Quality evaluation scripts
│   ├── security/               # Safety gate
│   └── main.py                 # FastAPI application
├── governance/
│   ├── governance.yaml         # Machine-readable governance checklist
│   └── gate_runner.py          # CI gate runner
├── monitoring/
│   └── prometheus.yml          # Prometheus scrape config
├── frontend/
│   └── src/main.js             # Vue 3 + PrimeVue Aura entry point
├── .github/
│   └── workflows/
│       └── model-ci.yml        # CI/CD pipeline with governance gate
└── README.md
```
