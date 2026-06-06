# Runbook: Roll Back a Model to the Previous Version

**Purpose**: Revert the MLflow Production alias for a model to its previous version when quality metrics degrade or a safety incident is detected.

**Prerequisites**:
- MLflow UI accessible at `http://localhost:5001`
- `MLFLOW_TRACKING_URI=http://localhost:5001` set in your shell
- Python environment active with `mlflow` installed
- Access to the GitHub Actions rollback webhook (or the `act` CLI for local simulation)

---

## Steps

### Option A: Automated rollback via GitHub Actions

1. **Trigger the rollback workflow**

   ```bash
   # Using GitHub CLI
   gh workflow run rollback.yml \
     --field model_name=captioner \
     --field reason="METEOR score dropped below 0.35 in canary"
   ```

   Or, for local simulation with `act`:

   ```bash
   act -j rollback --secret-file .secrets \
     --eventpath tests/fixtures/rollback_event.json
   ```

2. **Monitor the workflow**

   The workflow will:
   - Identify the current Production version.
   - Find the most recent previous version with `status=READY`.
   - Set the Production alias to that version.
   - Run the quality gate against the reverted version.
   - Post a Slack notification (if configured).

3. **Confirm the workflow completed successfully** (green checkmark in GitHub Actions or `act` output).

---

### Option B: Manual rollback via MLflow Python client

1. **List recent model versions**

   ```python
   import mlflow
   client = mlflow.tracking.MlflowClient()

   versions = client.search_model_versions("name='captioner'")
   for v in sorted(versions, key=lambda x: int(x.version), reverse=True)[:5]:
       print(f"v{v.version} — {v.aliases} — {v.status} — {v.run_id}")
   ```

2. **Identify the target version to revert to**

   Note the version number of the last known-good version (the one before the current Production).

3. **Set the Production alias to the target version**

   ```python
   client.set_registered_model_alias(
       name="captioner",
       alias="Production",
       version="<target_version_number>",
   )
   print("Production alias updated.")
   ```

4. **Verify the alias is correct**

   ```python
   prod = client.get_model_version_by_alias("captioner", "Production")
   print(f"Production is now v{prod.version} (run_id={prod.run_id})")
   ```

5. **Restart the Celery worker** to pick up the new Production model

   ```bash
   pkill -f "celery -A app.tasks"
   cd backend && celery -A app.tasks worker --loglevel=info &
   ```

---

## Verification

After rollback, run a smoke test inference:

```bash
cd backend
python3 -c "
import mlflow
mlflow.set_tracking_uri('http://localhost:5001')
model = mlflow.pyfunc.load_model('models:/captioner@Production')
print('Model loaded:', model)
"
```

Then trigger a full end-to-end test comic generation to confirm the reverted model produces acceptable output.

---

## Rollback of Rollback

If the previous version also has problems, repeat the process, targeting the version before it. Keep going back until you find a stable version. If no stable version exists, consider disabling the model endpoint (`GET /api/health` will report `upstream: false`) until a fix is deployed.
