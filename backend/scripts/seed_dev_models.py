"""
Seed the local MLflow registry with stub pyfunc models.

Use this in development to make the full UI flow work without downloading
BLIP-2 weights or running Ollama. Both stubs return plausible mock data.

Usage (from the repo root):
    docker compose exec fastapi python scripts/seed_dev_models.py

Or via Makefile:
    make seed
"""

from __future__ import annotations

import json
import os
import sys

import mlflow
import mlflow.pyfunc
import pandas as pd

MLFLOW_URI = os.environ.get("MLFLOW_TRACKING_URI", "http://localhost:5001")
mlflow.set_tracking_uri(MLFLOW_URI)


# ---------------------------------------------------------------------------
# Stub model definitions
# ---------------------------------------------------------------------------

class _StubCaptioner(mlflow.pyfunc.PythonModel):
    """Returns a plausible caption without running BLIP-2."""

    def predict(self, context, model_input, params=None):  # noqa: ARG002
        if isinstance(model_input, pd.DataFrame):
            rows = model_input.to_dict(orient="records")
        elif isinstance(model_input, dict):
            rows = [model_input]
        else:
            rows = list(model_input)

        results = []
        for _ in rows:
            results.append({
                "caption": (
                    "A child's colorful drawing showing a cheerful scene "
                    "with bright colours and playful shapes"
                ),
                "latency_ms": 42.0,
            })
        return results[0] if len(results) == 1 else results


class _StubStoryteller(mlflow.pyfunc.PythonModel):
    """Returns plausible comic panels without calling Ollama."""

    def predict(self, context, model_input, params=None):  # noqa: ARG002
        if isinstance(model_input, pd.DataFrame):
            row = model_input.to_dict(orient="records")[0]
        elif isinstance(model_input, dict):
            row = model_input
        else:
            row = list(model_input)[0]

        panel_count = int(row.get("panel_count", 4))
        caption = str(row.get("caption", "a colourful drawing"))

        panels = []
        narrations = [
            f"Once upon a time, {caption}.",
            "The adventure was just beginning.",
            "Together they faced every challenge.",
            "And in the end, everyone was happy.",
            "They celebrated with a big party!",
            "The End — what a wonderful story!",
        ]
        dialogues = [
            "Let's go on an adventure!",
            None,
            "We can do it together!",
            None,
            "Hooray!",
            None,
        ]

        for i in range(panel_count):
            idx = i % len(narrations)
            panels.append({
                "panel": i + 1,
                "narration": narrations[idx],
                "dialogue": dialogues[idx],
            })

        return {"panels": panels}


# ---------------------------------------------------------------------------
# Registration helper
# ---------------------------------------------------------------------------

def _register(name: str, model: mlflow.pyfunc.PythonModel, alias: str = "Production") -> None:
    print(f"\n→ Registering '{name}' stub …")

    with mlflow.start_run(run_name=f"seed-{name}") as run:
        mlflow.log_param("model_type", "stub")
        mlflow.log_param("stub", "true")
        mlflow.pyfunc.log_model(
            artifact_path="model",
            python_model=model,
            registered_model_name=name,
        )
        run_id = run.info.run_id

    client = mlflow.MlflowClient()

    # Find the version just created and assign the alias
    versions = client.search_model_versions(f"name='{name}'")
    versions_sorted = sorted(versions, key=lambda v: int(v.version), reverse=True)
    latest = versions_sorted[0]

    client.set_registered_model_alias(name, alias, latest.version)
    print(f"   ✓ {name} v{latest.version} → alias '{alias}' (run {run_id[:8]})")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    print(f"MLflow tracking URI: {MLFLOW_URI}")
    print("Seeding stub models …")

    try:
        _register("captioner", _StubCaptioner())
        _register("storyteller", _StubStoryteller())
    except Exception as exc:
        print(f"\n✗ Seeding failed: {exc}", file=sys.stderr)
        sys.exit(1)

    print("\n✓ Done. Restart fastapi and celery-worker to pick up the new models:")
    print("  docker compose restart fastapi celery-worker")
