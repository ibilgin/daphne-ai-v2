Build a GitHub Actions CI/CD pipeline for a multimodal ML project, runnable locally with act.

Create:
1. .github/workflows/model-ci.yml — stages: lint (ruff), test (pytest), eval (run captioner on test set), quality_gate (call quality_gate.py, fail if thresholds not met), register (mlflow register if gate passes), canary (update Staging alias, run 10% traffic split check).

2. .github/workflows/rollback.yml — triggered by webhook POST to /hooks/rollback. Reads current Production model metrics from MLflow, and if LLM refusal_rate > 0.05 or caption_meteor < 0.30, reverts the Production alias to the previous version and posts a Slack-style log to a local webhook.

3. tests/test_captioner.py — pytest suite with 10 fixture images. Asserts: caption is str, 5–50 words, does not contain blocked words list, returns in < 5 seconds.

4. tests/test_storyteller.py — pytest suite. Asserts: returns valid JSON with panels list, each panel has narration (str) and dialogue (str or null), panel count matches requested count.

5. scripts/canary_check.py — calls both Champion and Challenger model versions on the same 20-image batch, computes METEOR for each, logs both to MLflow under a comparison experiment, returns the winner alias.

Include a .actrc file and .secrets.example for local act configuration.