---
description: Trigger the model rollback workflow. Reverts Production alias to previous version if quality metrics degrade. Usage: /model-rollback or /model-rollback captioner
---

Trigger the model rollback workflow for the Sketch to Story project.

**Model** (optional): $ARGUMENTS — if empty, check both captioner and storyteller.

Steps:

1. **Check current Production metrics from MLflow**:
   ```bash
   cd backend && python3 -c "
   import mlflow
   mlflow.set_tracking_uri('http://localhost:5001')
   client = mlflow.tracking.MlflowClient()
   for name in ['captioner', 'storyteller']:
       try:
           mv = client.get_model_version_by_alias(name, 'Production')
           run = client.get_run(mv.run_id)
           metrics = run.data.metrics
           print(f'{name} v{mv.version}: METEOR={metrics.get(\"meteor\",\"N/A\"):.3f}, BERTScore={metrics.get(\"bertscore_f1\",\"N/A\"):.3f}, refusal_rate={metrics.get(\"refusal_rate\",0):.3f}')
       except Exception as e:
           print(f'{name}: {e}')
   "
   ```

2. **Evaluate rollback trigger conditions**:
   - If `refusal_rate > 0.05` → rollback storyteller
   - If `caption_meteor < 0.30` → rollback captioner
   - If neither condition is met, report "No rollback needed — current metrics are within thresholds" and stop.

3. **If rollback is needed, simulate the rollback webhook via act**:
   ```bash
   act -j rollback --secret-file .secrets --verbose
   ```

4. **Or perform direct rollback if act is not available**:
   ```bash
   cd backend && python3 -c "
   import mlflow
   mlflow.set_tracking_uri('http://localhost:5001')
   client = mlflow.tracking.MlflowClient()
   name = '$ARGUMENTS' or 'captioner'
   # Get all versions sorted by creation time
   versions = sorted(client.search_model_versions(f\"name='{name}'\"), key=lambda v: int(v.version))
   prod_version = client.get_model_version_by_alias(name, 'Production').version
   prev_versions = [v for v in versions if int(v.version) < int(prod_version)]
   if prev_versions:
       prev = prev_versions[-1]
       client.set_registered_model_alias(name, 'Production', prev.version)
       print(f'Rolled back {name} Production: v{prod_version} → v{prev.version}')
   else:
       print('No previous version to roll back to')
   "
   ```

5. **Log the rollback event** — write to the audit log or print a structured record:
   ```
   ROLLBACK EVENT: {timestamp} | model={name} | from=v{old} | to=v{new} | trigger={metric}: {value}
   ```

6. **Verify**: Check the Production alias now points to the previous version (step 1 again).

7. **Report**: Confirm the rollback completed, the old and new versions, and what triggered it.
