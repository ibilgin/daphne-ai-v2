.PHONY: up up-full down build rebuild logs ps restart shell help

SHELL := /bin/zsh -l

# ── Target: default ────────────────────────────────────────────────────────────
.DEFAULT_GOAL := help

# ── Start ──────────────────────────────────────────────────────────────────────

up: ## Start the full dev stack (infra + app + frontend)
	docker compose up -d
	@echo ""
	@echo "  Frontend  → http://localhost:5173"
	@echo "  BFF       → http://localhost:3001"
	@echo "  FastAPI   → http://localhost:8000/docs"
	@echo "  MLflow    → http://localhost:5001"
	@echo "  MinIO     → http://localhost:9001  (minioadmin / minioadmin)"
	@echo ""
	@echo "Run 'make logs' to follow all logs, or 'make logs s=fastapi' for one service."

up-full: ## Start everything including Prometheus + Grafana monitoring
	docker compose --profile monitoring up -d
	@echo ""
	@echo "  Frontend  → http://localhost:5173"
	@echo "  BFF       → http://localhost:3001"
	@echo "  FastAPI   → http://localhost:8000/docs"
	@echo "  MLflow    → http://localhost:5001"
	@echo "  MinIO     → http://localhost:9001"
	@echo "  Grafana   → http://localhost:3000  (admin / admin)"
	@echo "  Prometheus→ http://localhost:9090"
	@echo ""

# ── Stop ───────────────────────────────────────────────────────────────────────

down: ## Stop and remove all containers (data volumes are preserved)
	docker compose --profile monitoring down

down-all: ## Stop containers AND delete all data volumes (full reset)
	docker compose --profile monitoring down -v
	@echo "All volumes deleted — next 'make up' starts fresh."

# ── Build ──────────────────────────────────────────────────────────────────────

build: ## Build backend, BFF, and frontend images
	docker compose build fastapi celery-worker bff frontend

rebuild: ## Force rebuild without cache
	docker compose build --no-cache fastapi celery-worker bff frontend

# ── Observe ────────────────────────────────────────────────────────────────────

logs: ## Follow logs — all services, or one: make logs s=fastapi
	docker compose logs -f $(s)

ps: ## List all running containers and their status
	docker compose ps

# ── Manage ─────────────────────────────────────────────────────────────────────

restart: ## Restart a service: make restart s=fastapi
	docker compose restart $(s)

shell: ## Open a shell in a container: make shell s=fastapi
	docker compose exec $(s) sh

seed: ## Register stub pyfunc models in MLflow so the UI works without real weights
	docker cp backend/scripts/seed_dev_models.py daphne-fastapi:/app/scripts/seed_dev_models.py
	docker compose exec \
		-e AWS_ACCESS_KEY_ID=$${MINIO_ACCESS_KEY:-minioadmin} \
		-e AWS_SECRET_ACCESS_KEY=$${MINIO_SECRET_KEY:-minioadmin} \
		-e MLFLOW_S3_ENDPOINT_URL=http://minio:9000 \
		fastapi python scripts/seed_dev_models.py
	docker compose restart fastapi celery-worker

# ── Help ───────────────────────────────────────────────────────────────────────

help: ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) \
	  | awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-14s\033[0m %s\n", $$1, $$2}'
