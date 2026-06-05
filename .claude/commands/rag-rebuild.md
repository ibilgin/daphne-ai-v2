---
description: Rebuild the ChromaDB style library index from scratch and run RAG evaluation (precision@3). Usage: /rag-rebuild
---

Rebuild the ChromaDB narrative style index and run RAG evaluation for the Sketch to Story project.

Steps:

1. **Check Phase 3 exists**:
   ```bash
   ls backend/rag/indexer.py backend/rag/style_library.json
   ```
   If missing: "Phase 3 has not been implemented yet. Run `/implement-phase 3` first."

2. **Check Python environment**:
   ```bash
   cd backend && python3 -c "import chromadb, sentence_transformers; print('deps OK')" || \
   echo "Install deps: uv pip install -r requirements.txt"
   ```

3. **Show current index state** (if it exists):
   ```bash
   cd backend && python3 -c "
   import chromadb
   client = chromadb.PersistentClient(path='./chroma_db')
   try:
       col = client.get_collection('narrative_styles')
       print(f'Current index: {col.count()} documents')
   except Exception as e:
       print(f'No existing index: {e}')
   "
   ```

4. **Rebuild the index**:
   ```bash
   cd backend && python rag/indexer.py --rebuild
   ```
   Expected output: "Indexed 60 documents into narrative_styles collection"

5. **Verify index after rebuild**:
   ```bash
   cd backend && python3 -c "
   import chromadb
   client = chromadb.PersistentClient(path='./chroma_db')
   col = client.get_collection('narrative_styles')
   print(f'Index size: {col.count()} documents')
   # Sample retrieval
   results = col.query(query_texts=['a child drawing a dog in a garden'], n_results=3)
   for i, (doc, meta) in enumerate(zip(results['documents'][0], results['metadatas'][0])):
       print(f'  {i+1}. [{meta[\"style\"]}] {doc[:80]}...')
   "
   ```

6. **Run RAG evaluation**:
   ```bash
   cd backend && python rag/eval.py
   ```
   This logs `precision_at_3` and `mean_latency_ms` to MLflow experiment `rag-eval`.

7. **Show results**:
   ```bash
   cd backend && python3 -c "
   import mlflow
   mlflow.set_tracking_uri('http://localhost:5001')
   runs = mlflow.search_runs(experiment_names=['rag-eval'], max_results=1, order_by=['start_time DESC'])
   if not runs.empty:
       r = runs.iloc[0]
       print(f'precision@3: {r.get(\"metrics.precision_at_3\", \"N/A\"):.3f}')
       print(f'mean_latency_ms: {r.get(\"metrics.mean_latency_ms\", \"N/A\"):.1f}')
   " 2>/dev/null || echo "MLflow not running — run eval output shown above"
   ```

8. **Report**: Confirm index size (expected: 60), precision@3 score, mean latency, and any styles with low retrieval accuracy.

If precision@3 is below 0.7, suggest reviewing the style_library.json examples for the underperforming genres.
