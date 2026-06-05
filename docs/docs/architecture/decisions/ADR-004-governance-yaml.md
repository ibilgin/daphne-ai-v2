# ADR-004: Use governance.yaml as Machine-Readable Governance Checklist

**Status**: Accepted  
**Date**: 2026-04-01  
**Deciders**: Platform team

---

## Context

The platform must enforce governance requirements before any model can be promoted to the Production alias in MLflow. These requirements include:

- Child safety gate (Detoxify toxicity thresholds).
- Model quality metrics (METEOR, BERTScore).
- Bias audit (Fairlearn demographic parity).
- Data privacy compliance (hash-only audit log, GDPR minimisation).
- Human review queue for escalated cases.
- Transparency notice to parents before use.
- Audit trail completeness.

The team needed a format for these requirements that is:
1. **Machine-readable** — parseable by CI/CD pipelines without regex scraping.
2. **Human-readable** — understandable by non-engineers (compliance officers, auditors).
3. **Version-controlled** — tracked in Git alongside code, not stored in a database.
4. **Extensible** — new checks should be addable without breaking existing automation.

---

## Decision

We define a **`governance/governance.yaml`** file that is the single source of truth for all governance checks. Each check has:

```yaml
checks:
  check_name:
    name: Human-readable name
    type: boolean | metric
    required: true | false
    status: pending | pass | fail
    description: >
      Explanation of what this check validates.
    last_verified: "YYYY-MM-DD"
    # For type: metric only:
    thresholds:
      metric_name_max: 0.1
      metric_name_min: 0.35
```

The CI/CD pipeline runs `backend/governance/gate_runner.py`, which:
1. Loads `governance.yaml`.
2. For each check with `required: true`, asserts `status: pass`.
3. For `type: metric` checks, re-runs the metric computation and compares against thresholds.
4. Exits with code 0 (pass) or 1 (fail).

The gate runner is invoked as a step in `.github/workflows/model-ci.yml` before any MLflow Production alias update.

---

## Alternatives Considered

### Governance stored in MLflow model tags
- **Pros**: Co-located with model artefacts.
- **Cons**: Not human-readable without the MLflow UI. Not version-controlled. Tags are mutable without audit trail. Cannot be reviewed in a pull request.

### JSON schema file
- **Pros**: Stricter validation with JSON Schema tooling.
- **Cons**: JSON does not support multi-line strings or comments. The description fields for compliance officers require readable prose — YAML's `>` block scalars are significantly more readable.

### Database-backed governance checks (e.g. in Postgres)
- **Pros**: Queryable, UI-friendly.
- **Cons**: Requires a running database to evaluate governance status. CI/CD pipelines cannot inspect it without a live connection. Eliminates pull-request-based governance review.

---

## Consequences

**Positive**:
- Governance status is visible in every pull request diff. Reviewers can see if a check has been changed from `pass` to `pending` before merging.
- The gate runner is a plain Python script — no platform dependencies. It runs in any environment with `pyyaml` installed.
- The YAML format is readable by compliance officers and maps directly to the human-readable [Governance Checklist](../governance/checklist.md).
- EU AI Act auditors can inspect the governance history via Git blame.

**Negative**:
- Manual status updates (`status: pass`) require a human to run the evaluation and commit the result. This introduces the risk of a human marking a check as `pass` without actually running the evaluation.
- **Mitigation**: The CI pipeline re-runs metric checks programmatically and will fail even if `status: pass` is manually set but the metric does not actually pass the threshold.
