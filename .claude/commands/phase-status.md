---
description: Show build status for all 6 phases — what files exist vs what's expected per phase
---

Check the status of all 6 development phases for the Sketch to Story project. For each phase, look for the key deliverable files and report whether they exist.

Run these checks and report a clear status table:

**Phase 1 — MLOps Foundation**
Check for: `docker-compose.yml`, `backend/models/captioner.py`, `backend/models/storyteller.py`, `backend/eval/quality_gate.py`, `backend/scripts/register_models.py`, `.github/workflows/model-ci.yml`, `.github/workflows/rollback.yml`

**Phase 2 — Model Serving API**
Check for: `backend/app/main.py`, `backend/app/tasks.py`, `backend/app/schemas.py`, `backend/app/model_loader.py`, `backend/Dockerfile`, `helm/comic-platform/Chart.yaml`, `keda/scaled-object.yaml`

**Phase 3 — RAG & Agentic Pipeline**
Check for: `backend/rag/style_library.json`, `backend/rag/indexer.py`, `backend/rag/retriever.py`, `backend/rag/story_chain.py`, `backend/agent/state.py`, `backend/agent/nodes.py`, `backend/agent/graph.py`, `backend/agent/tracing.py`

**Phase 4 — Monitoring & Drift**
Check for: `backend/monitoring/metrics_exporter.py`, `backend/monitoring/drift_reporter.py`, `backend/monitoring/evidently_exporter.py`, `monitoring/docker-compose-monitoring.yml`, `monitoring/grafana/dashboard.json`, `monitoring/alertmanager/config.yml`, `backend/app/routes/hooks.py`

**Phase 5 — Governance & Safety**
Check for: `backend/security/safety_gate.py`, `backend/security/input_validator.py`, `backend/security/audit_log.py`, `backend/security/auth.py`, `backend/security/vault_client.py`, `backend/governance/governance.yaml`, `backend/governance/gate_runner.py`, `backend/governance/model_card_generator.py`, `backend/governance/bias_audit.py`

**Phase 6 — Frontend & Docs**
Check for: `frontend/src/main.js`, `frontend/src/stores/comic.js`, `frontend/src/components/ComicBook.vue`, `frontend/src/views/ReaderView.vue`, `bff/src/index.js`, `docs/mkdocs.yml`, `cookiecutter-template/cookiecutter.json`

For each phase, report:
- **Status**: ✅ Complete / ⚠️ Partial (list missing files) / ❌ Not started
- **Missing files**: list any expected files that don't exist yet

End with a summary of how many phases are complete and which phase to implement next.
