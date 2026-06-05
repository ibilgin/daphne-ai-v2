Build a Node.js BFF, MkDocs documentation site, and Cookiecutter project template for the Sketch to Story platform.

Create:
1. bff/src/index.js — Express 5 server (port 3001). Routes:
   - GET/POST /api/* → http-proxy-middleware to FASTAPI_URL (env var, default http://localhost:8000).
   - GET /api/comics/:id/export-html → fetches comic JSON from FastAPI, assembles a self-contained HTML file (inline CSS, base64 images, no external deps) and streams it as attachment download.
   - Static serve: in production (NODE_ENV=production), serve ../frontend/dist.
   - Health: GET /health → {status: ok, upstream: bool (result of pinging FastAPI /health)}.
   CORS: allow localhost:5173 in development.

2. bff/package.json — dependencies: express@5, http-proxy-middleware, cors, node-fetch. Include start and dev (nodemon) scripts.

3. docs/ — MkDocs project (mkdocs.yml with material theme).
   - docs/index.md: project overview, architecture diagram in Mermaid (components: Vue Frontend → Node BFF → FastAPI → Celery Workers → MLflow + MinIO + ChromaDB + Redis + Postgres).
   - docs/architecture/decisions/: ADR-001-blip2-captioner.md, ADR-002-stpageflip.md, ADR-003-feast-feature-store.md, ADR-004-governance-yaml.md. Each ADR: Context, Decision, Alternatives Considered, Consequences.
   - docs/runbooks/: add-style-to-rag.md, rollback-model.md, read-audit-log.md, onboard-new-engineer.md.
   - docs/governance/: checklist.md (mirrors governance.yaml in readable form), ai-act-classification.md.
   - docs/api/: reference generated from OpenAPI spec at http://localhost:8000/openapi.json.

4. cookiecutter-template/ — Cookiecutter template directory structure that, when run, generates a new multimodal AI project with: docker-compose.yml (MLflow + MinIO + Postgres + Redis), src/models/ with pyfunc stubs, governance/governance.yaml (all checks set to pending), .github/workflows/model-ci.yml with gate_runner step, monitoring/ with Evidently + Prometheus stubs, frontend/ Vue 3 + PrimeVue scaffold, README.md with quickstart.
   Include cookiecutter.json with prompts: project_name, child_name_placeholder, mlflow_port, fastapi_port, author.