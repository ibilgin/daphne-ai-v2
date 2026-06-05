---
description: Run the model CI pipeline locally using act. Runs lint → test → eval → quality_gate → register → canary. Usage: /run-ci or /run-ci rollback
---

Run the GitHub Actions CI pipeline locally for the Sketch to Story project.

**Job to run**: $ARGUMENTS (default: `model-ci` if empty, `rollback` if "rollback" passed)

Pre-flight checks:
1. Verify Docker Desktop is running: `docker info > /dev/null 2>&1`
2. Verify `act` is installed: `act --version`
3. Verify `.secrets` file exists: `ls .secrets`
   - If missing, show the user: "Create .secrets from .secrets.example and fill in credentials: `cp .secrets.example .secrets`"
4. Verify `docker-compose.yml` services are up (MLflow + MinIO needed for CI):
   ```bash
   docker compose ps --format "table {{.Name}}\t{{.Status}}" 2>/dev/null | head -10
   ```
   If services are down, suggest: `docker compose up -d`

Run the pipeline:
```bash
# Default: model-ci
act -j model-ci --secret-file .secrets --verbose 2>&1 | tee /tmp/act-output.log

# Rollback test
act -j rollback --secret-file .secrets --verbose 2>&1 | tee /tmp/act-output.log
```

After completion:
- Show the last 50 lines of output
- Report: PASSED or FAILED with the failing step
- If `quality_gate` step failed: show the METEOR and BERTScore values vs thresholds (METEOR > 0.35, BERTScore F1 > 0.75)
- If `governance` step failed: show which `governance.yaml` checks did not pass
- If tests failed: show which test file and assertion failed

If act fails due to missing container image, suggest:
```bash
act --list    # see what images are needed
act -j model-ci --secret-file .secrets -P ubuntu-latest=catthehacker/ubuntu:act-latest
```
