---
description: Fetch a GitHub issue, implement the fix or feature it describes, and open a PR that closes it. Usage: /work-issue <issue-number>
---

Work on GitHub issue #$ARGUMENTS for the Sketch to Story project.

## 1. Fetch the issue

```bash
gh issue view $ARGUMENTS --json number,title,body,labels,assignees,state
```

If `gh` is not authenticated:
```bash
gh auth status
```
If not logged in, ask the user to run `! gh auth login` in the prompt.

If the issue doesn't exist or the repo remote isn't set up, stop and report.

## 2. Parse the issue

From the issue body, determine:
- **Type**: bug (labels include `bug`, `fix`, title starts with "fix:") OR feature (labels include `enhancement`, `feature`)
- **Affected domain**: map issue content to the layer table below
- **Acceptance criteria**: what "done" looks like (from issue body or inferred)

| Domain keywords | Specialist agent |
|-----------------|-----------------|
| MLflow, model, registry, eval, canary, CI pipeline | mlops-engineer |
| API, endpoint, job, Celery, schema, Docker, Helm, k8s | api-serving-engineer |
| RAG, ChromaDB, retriever, LangGraph, agent, chain, trace | rag-agent-engineer |
| metrics, Prometheus, Grafana, drift, Evidently, alert | ml-observability |
| safety, Detoxify, audit, JWT, Vault, governance, bias | security-governance |
| Vue, frontend, PrimeVue, BFF, Express, MkDocs, comic viewer | frontend-engineer |

## 3. Create a branch named after the issue

```bash
git checkout main && git pull origin main

# Slugify the issue title (lowercase, hyphens)
ISSUE_TITLE=$(gh issue view $ARGUMENTS --json title -q .title | tr '[:upper:]' '[:lower:]' | sed 's/[^a-z0-9]/-/g' | sed 's/--*/-/g' | cut -c1-40)

# Bug → fix branch, feature → feat branch
BRANCH_TYPE="feat"   # change to "fix" if bug
git checkout -b ${BRANCH_TYPE}/issue-$ARGUMENTS-${ISSUE_TITLE}
```

## 4. Implement

For **bugs**: follow the `/fix-bug` process using the issue description as the bug description.
For **features**: follow the `/feature` process using the issue description as the feature description.

Key rule: the implementation must satisfy the acceptance criteria in the issue. If the issue has a checklist, use it as your definition of done.

## 5. Run tests

```bash
cd backend && pytest tests/ -v 2>&1 | tail -30
```

For frontend changes:
```bash
cd frontend && npm run build 2>&1 | tail -20
```

## 6. Commit referencing the issue

```bash
git add <changed files>
git commit -m "$(cat <<'EOF'
<type>(<scope>): <description>

Closes #$ARGUMENTS

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>
EOF
)"
```

`Closes #$ARGUMENTS` in the commit message will auto-close the issue when the PR merges.

## 7. Push and open PR

```bash
git push -u origin $(git branch --show-current)

gh pr create \
  --title "$(gh issue view $ARGUMENTS --json title -q .title)" \
  --body "$(cat <<'EOF'
Closes #$ARGUMENTS

## What was done
- <bullet points>

## How to verify
- <steps to manually test the change>

## Tests
- [ ] `pytest tests/ -v` passes
- [ ] Governance gate passes (if Phase 5 complete)

🤖 Generated with [Claude Code](https://claude.com/claude-code)
EOF
)"
```

## 8. Report

State:
- Issue #$ARGUMENTS title and what it required
- Files changed and what changed in each
- PR URL
- Whether any manual follow-up is needed (migrations, index rebuilds, service restarts)
