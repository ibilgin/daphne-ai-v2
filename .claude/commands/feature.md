---
description: Implement a new feature end-to-end. Plans which layers are affected, routes to the right specialist agents, implements across all layers, and opens a PR. Usage: /feature <feature description>
---

Implement the following feature for the Sketch to Story project: $ARGUMENTS

Follow this full design-to-PR cycle:

## 1. Design — identify affected layers

Read the feature description and determine which layers need changes:

| Layer | Files | Agent |
|-------|-------|-------|
| MLflow / model registry | `backend/models/`, `backend/eval/`, `backend/scripts/` | mlops-engineer |
| API endpoints / job flow | `backend/app/routes/`, `backend/app/tasks.py`, `backend/app/schemas.py` | api-serving-engineer |
| RAG / agent pipeline | `backend/rag/`, `backend/agent/` | rag-agent-engineer |
| Monitoring / metrics | `backend/monitoring/`, `monitoring/` | ml-observability |
| Safety / governance | `backend/security/`, `backend/governance/` | security-governance |
| Frontend / BFF | `frontend/src/`, `bff/src/` | frontend-engineer |
| k8s / Helm | `helm/`, `keda/` | api-serving-engineer |
| Docs | `docs/` | frontend-engineer |
| CI/CD | `.github/workflows/` | mlops-engineer |

Write out: "This feature touches: [list of layers]" before writing any code.

## 2. Check for conflicts with existing interfaces

Before implementing, verify the feature does not break:
- `ComicSchema / PageSchema / PanelSchema` — if changed, ALL layers must be updated together
- `ComicState` TypedDict — LangGraph node signatures depend on this
- `POST /api/generate-comic` → job_id → poll → retrieve contract — frontend depends on this
- pyfunc `predict()` signatures — model_loader.py and CI depend on these

If the feature changes a shared interface, list every file that must change before starting.

## 3. Create a feature branch

```bash
git checkout main && git pull origin main
# Branch name: feat/<short-slug>
git checkout -b feat/<slug-from-feature-description>
```

## 4. Implement — layer by layer

Apply each specialist agent's expertise for its domain. Work bottom-up: data layer → backend → API → frontend. This order prevents writing frontend code against an API contract that doesn't exist yet.

For each layer:
- Read the existing code in that area first
- Make the minimal changes required
- Do not refactor unrelated code
- Do not add features beyond what was requested

Critical constraints that apply to ALL features:
- Child data: never add storage of raw images or text with PII
- Safety: any new content generation must pass through the safety gate
- New secrets: must go through Vault, never hardcoded
- New endpoints: must have appropriate `require_role()` dependency
- New models or eval changes: must update `governance.yaml` if they affect a governance check

## 5. Write or update tests

For backend changes: add/update `backend/tests/`
For schema changes: update fixture data in tests
For new API endpoints: add at least one happy-path and one error-case test

```bash
cd backend && pytest tests/ -v 2>&1 | tail -30
```

## 6. Update docs if needed

If the feature adds a new API endpoint → update OpenAPI description in the route docstring
If the feature changes a runbook workflow → update `docs/runbooks/`
If the feature changes governance → update `governance/governance.yaml` and `docs/governance/checklist.md`

## 7. Run governance check if Phase 5 exists

```bash
cd backend && python governance/gate_runner.py 2>/dev/null && echo "Governance: PASS" || echo "Governance: needs update"
```

## 8. Commit

```bash
git add <all changed files>
git commit -m "$(cat <<'EOF'
feat(<scope>): <description of what the feature does and why>

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>
EOF
)"
```

## 9. Push and open PR

```bash
git push -u origin $(git branch --show-current)
gh pr create \
  --title "feat: <feature title>" \
  --body "$(cat <<'EOF'
## Summary
- <bullet points of what was built>

## Layers changed
- <list of layers/files affected>

## Test plan
- [ ] Unit tests pass (`pytest tests/ -v`)
- [ ] Governance gate passes (`python governance/gate_runner.py`)
- [ ] Manual test: <describe how to manually verify this feature>

## Breaking changes
<none / or describe if any shared interface changed>

🤖 Generated with [Claude Code](https://claude.com/claude-code)
EOF
)"
```

## 10. Report

State:
- What was built and in which files
- Any shared interfaces that changed (so user knows what to re-test)
- PR URL
- Any manual steps needed (e.g. `python rag/indexer.py --rebuild` if RAG style library changed)
