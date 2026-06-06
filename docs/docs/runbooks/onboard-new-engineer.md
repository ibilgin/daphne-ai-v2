# Runbook: Onboard a New Engineer

**Purpose**: Get a new team member from zero to a running local development environment with all services healthy and tests passing.

**Prerequisites**:
- macOS or Linux workstation
- Docker Desktop (or Colima on macOS)
- Python 3.11
- Node.js 20+
- `git`, `uv` (Python package manager), `act` (for local CI)

Estimated time: 30–45 minutes.

---

## Steps

### 1. Clone the repository

```bash
git clone https://github.com/<org>/sketch-to-story.git
cd sketch-to-story
```

### 2. Start the infrastructure containers

```bash
docker compose up -d
```

Wait ~30 seconds for all services to initialise. Verify:

```bash
docker compose ps
```

All services should show `running`. Key services: `mlflow`, `minio`, `postgres`, `redis`.

### 3. Set up the Python environment

```bash
cd backend
python3.11 -m venv .venv
source .venv/bin/activate
uv pip install -r requirements.txt
```

Copy the environment file:

```bash
cp .env.example .env
# No changes needed for local dev defaults
```

### 4. Run the backend tests

```bash
cd backend
pytest tests/ -v
```

All tests should pass. If any fail, check that Docker services are running and that `.env` is correctly configured.

### 5. Start FastAPI and Celery

In two separate terminal tabs:

```bash
# Tab 1: FastAPI
cd backend
uvicorn app.main:app --reload --port 8000
```

```bash
# Tab 2: Celery worker
cd backend
celery -A app.tasks worker --loglevel=info
```

Verify FastAPI is up: `curl http://localhost:8000/health`

### 6. Install and start the BFF

```bash
cd bff
npm install
npm run dev
```

Verify BFF is up: `curl http://localhost:3001/health`

### 7. Install and start the Vue frontend

```bash
cd frontend
npm install
npm run dev
```

Open [http://localhost:5173](http://localhost:5173) in your browser. You should see the Comic Library with an empty state and a "Create your first comic" CTA.

### 8. Access service UIs

| Service | URL | Credentials |
|---------|-----|-------------|
| Vue Frontend | http://localhost:5173 | — |
| FastAPI Swagger | http://localhost:8000/docs | — |
| MLflow UI | http://localhost:5001 | — |
| MinIO Console | http://localhost:9001 | minioadmin / minioadmin |
| Grafana | http://localhost:3000 | admin / admin |
| Prometheus | http://localhost:9090 | — |

### 9. Generate a test comic (optional smoke test)

Use the UI at `http://localhost:5173/generate` to:
1. Upload any small image from `backend/tests/fixtures/`.
2. Enter a child name and age group.
3. Select a style.
4. Watch the job progress and confirm the comic reader opens.

### 10. Run the local CI pipeline

```bash
cp .secrets.example .secrets
# Fill in any required values (see .secrets.example comments)
act -j model-ci --secret-file .secrets
```

---

## Verification

A successful onboarding session has:
- All `docker compose ps` services in `running` state.
- `pytest tests/ -v` all green.
- `curl http://localhost:8000/health` returning `{"status": "ok"}`.
- `curl http://localhost:3001/health` returning `{"status": "ok", "upstream": true}`.
- The Vue frontend loading at `http://localhost:5173`.

---

## Common Issues

| Problem | Solution |
|---------|----------|
| `docker compose up -d` fails with port conflict | Check for existing services on ports 5432, 6379, 5001, 9001. Stop them or change ports in `docker-compose.yml`. |
| `uv pip install` fails | Ensure Python 3.11 is active: `python --version`. |
| `celery` worker exits immediately | Check Redis is running: `docker compose ps redis`. |
| Frontend shows blank page | Check BFF is running on 3001 and `VITE_API_URL` in `frontend/.env` is set correctly. |
| MLflow UI unreachable | Run `docker compose logs mlflow` to diagnose. |
