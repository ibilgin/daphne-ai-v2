---
description: Full issue-to-merge bug fix cycle. Diagnoses the bug, routes to the right specialist agent, patches code, runs tests, commits, and pushes. Usage: /fix-bug <description of the bug>
---

Fix the following bug in the Sketch to Story project: $ARGUMENTS

Follow this full cycle:

## 1. Diagnose — find the code

Search the codebase for the relevant files:
```bash
# Search for related code based on the bug description keywords
grep -r "<keywords from bug description>" backend/ frontend/ bff/ --include="*.py" --include="*.js" --include="*.vue" -l
```

Read the files most likely to contain the bug. Check recent git changes to related files:
```bash
git log --oneline -10 -- <relevant file>
git diff HEAD~3 -- <relevant file>
```

## 2. Route to the right specialist

Determine which domain owns this bug and apply that agent's expertise:

| Keywords in bug | Specialist agent to use |
|-----------------|------------------------|
| MLflow, model registry, pyfunc, METEOR, BERTScore, canary | mlops-engineer |
| FastAPI, Celery, Redis, job, schema, Pydantic, Docker, Helm, k8s | api-serving-engineer |
| ChromaDB, RAG, retriever, LangGraph, LangChain, LangSmith, agent, node, state | rag-agent-engineer |
| Prometheus, Grafana, Evidently, drift, PSI, alert, metrics, exporter | ml-observability |
| safety, Detoxify, JWT, Vault, audit, governance, bias, model card | security-governance |
| Vue, PrimeVue, Pinia, StPageFlip, BFF, Express, MkDocs | frontend-engineer |

## 3. Understand the bug before touching code

- Read the full function/class that contains the bug
- Identify the root cause — not just the symptom
- Check if the bug affects multiple files or just one
- Check if there are existing tests that should have caught this

## 4. Fix

Apply the minimal correct fix. Do not refactor unrelated code. Do not add features. Fix the specific bug.

Critical constraints to preserve:
- Child data: never store raw images, hashes only
- Safety gate: toxicity < 0.1 and identity_attack < 0.05 thresholds must not be relaxed
- pyfunc interface: predict() signature must not change
- ComicSchema / ComicState: field names and types must not change
- JWT roles: parent/admin/platform permissions must not be weakened

## 5. Run relevant tests

```bash
cd backend && pytest tests/ -v -k "<relevant test name or file>" 2>&1 | tail -30
```

If no test covers this bug, write a minimal regression test first, then fix.

## 6. Verify the fix doesn't break adjacent code

```bash
cd backend && python -m py_compile <fixed file>
cd backend && pytest tests/ -v 2>&1 | tail -20
```

For frontend fixes:
```bash
cd frontend && npm run build 2>&1 | tail -20
```

## 7. Commit

```bash
git add <changed files>
git commit -m "$(cat <<'EOF'
fix(<scope>): <concise description of what was wrong and what the fix does>

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>
EOF
)"
```

Scope = phase1/phase2/.../phase6 or the module name (safety, rag, agent, monitoring, etc.)

## 8. Report

State:
- Root cause of the bug
- Files changed and what changed in each
- Test that now covers it
- Whether a push to GitHub is needed (suggest `/github-push` if yes)
