---
description: Promote a model through the MLflow registry. Runs quality gate, registers, and sets Production alias. Usage: /model-promote captioner or /model-promote storyteller
---

Promote the specified model through the MLflow registry for the Sketch to Story project.

**Model to promote**: $ARGUMENTS (must be `captioner` or `storyteller`)

Steps:

1. **Verify the stack is running**:
   ```bash
   curl -s http://localhost:5001/health | python3 -c "import sys,json; d=json.load(sys.stdin); print('MLflow:', d.get('status','?'))"
   ```
   If MLflow is not running: `docker compose up -d && sleep 5`

2. **Check current registry state**:
   ```bash
   cd backend && python3 -c "
   import mlflow
   mlflow.set_tracking_uri('http://localhost:5001')
   client = mlflow.tracking.MlflowClient()
   name = '$ARGUMENTS'
   versions = client.search_model_versions(f\"name='{name}'\")
   for v in versions:
       print(f'  v{v.version}: {v.current_stage} | aliases: {v.aliases}')
   "
   ```

3. **Run quality gate**:
   ```bash
   cd backend && python eval/quality_gate.py --model $ARGUMENTS
   ```
   - If gate FAILS (exit non-zero): show the METEOR and BERTScore values. Do NOT promote. Suggest: investigate model or improve training data.
   - If gate PASSES: continue.

4. **Run governance gate**:
   ```bash
   cd backend && python governance/gate_runner.py
   ```
   If gate fails: list the failing checks. Do NOT promote until all required checks pass.

5. **Register and promote**:
   ```bash
   cd backend && python scripts/register_models.py --model $ARGUMENTS --promote
   ```

6. **Verify Production alias**:
   ```bash
   cd backend && python3 -c "
   import mlflow
   mlflow.set_tracking_uri('http://localhost:5001')
   client = mlflow.tracking.MlflowClient()
   mv = client.get_model_version_by_alias('$ARGUMENTS', 'Production')
   print(f'Production alias → v{mv.version} (run_id: {mv.run_id})')
   "
   ```

7. **Report**: Confirm the new Production version, the eval metrics that passed the gate, and the governance checks that were satisfied.
