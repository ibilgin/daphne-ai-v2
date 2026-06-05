Scaffold a local MLOps stack for a multimodal comic generation project.

Create:
1. docker-compose.yml with MLflow tracking server (port 5001), MinIO (port 9000/9001), and PostgreSQL as the MLflow backend store. MLflow should use MinIO as its S3 artifact store.

2. src/models/captioner.py — an mlflow.pyfunc.PythonModel wrapper for BLIP-2 (salesforce/blip-image-captioning-base via HuggingFace transformers). The predict() method accepts a dict with key "image_bytes" (base64-encoded PNG/JPEG) and returns {"caption": str, "latency_ms": float}.

3. src/models/storyteller.py — an mlflow.pyfunc.PythonModel wrapper for Mistral via Ollama HTTP API (localhost:11434). predict() accepts {"caption": str, "style_examples": list[str], "panel_count": int} and returns {"panels": list[{"panel": int, "narration": str, "dialogue": str}]}.

4. src/eval/quality_gate.py — loads the latest Staging captioner from MLflow registry, runs it against a test set of 20 images, computes METEOR and BERTScore, and promotes to Production only if METEOR > 0.35 and BERTScore F1 > 0.75.

5. scripts/register_models.py — registers both models into MLflow registry with tags: dataset_hash, eval_date, model_type.

Use Python 3.11, include requirements.txt, and add a README section on how to start the stack.