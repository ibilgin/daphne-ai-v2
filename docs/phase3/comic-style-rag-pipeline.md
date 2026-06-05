Build a LangChain RAG pipeline for comic story style retrieval using ChromaDB and Ollama.

Create:
1. rag/style_library.json — 60 short narrative examples (2–4 sentences each) across 6 styles: adventure, fantasy, friendship, mystery, animals, space. Each entry: {id, style, age_group: "4-6"|"7-9"|"10-12", tone, text}. Generate realistic, age-appropriate examples.

2. rag/indexer.py — loads style_library.json, embeds each entry using sentence-transformers all-MiniLM-L6-v2 (local, no API call), stores in ChromaDB (persistent, local ./chroma_db directory). Includes a CLI: python indexer.py --rebuild to re-index from scratch.

3. rag/retriever.py — StyleRetriever class with method retrieve(caption: str, age_group: str, top_k: int = 3) -> list[StyleExample]. First retrieves top-10 by cosine similarity, then re-ranks with a cross-encoder (cross-encoder/ms-marco-MiniLM-L-6-v2) and returns top_k. Returns latency_ms alongside results.

4. rag/story_chain.py — LangChain chain: takes caption + retrieved style examples + child_name + panel_count, calls Ollama Mistral, enforces structured JSON output via Ollama's format parameter. Retries up to 2 times if JSON parse fails.

5. rag/eval.py — evaluation harness: loads 15 (caption, expected_style) test pairs, runs retriever, computes precision@3 (did expected style appear in top 3?), logs metrics to MLflow experiment "rag-eval". Prints a confusion-style breakdown by style.

Wire retriever into the Celery task from Phase 2 (replace the direct Ollama call).