"""
StyleRetriever — two-stage RAG retrieval for narrative style examples.

Stage 1: ChromaDB cosine similarity search (top-10 candidates, filtered by age_group).
Stage 2: Cross-encoder re-ranking using cross-encoder/ms-marco-MiniLM-L-6-v2.
Returns top_k StyleExample objects plus overall latency_ms.

Usage
-----
    from rag.retriever import StyleRetriever

    retriever = StyleRetriever()
    results = retriever.retrieve(
        caption="a child flying a red kite in a sunny park",
        age_group="7-9",
        top_k=3,
    )
    for r in results:
        print(r.style, r.text)
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

_BACKEND_DIR = Path(__file__).parent.parent          # backend/
_CHROMA_DIR = str(_BACKEND_DIR / "chroma_db")

COLLECTION_NAME = "narrative_styles"
EMBED_MODEL_NAME = "all-MiniLM-L6-v2"
CROSS_ENCODER_MODEL_NAME = "cross-encoder/ms-marco-MiniLM-L-6-v2"

# Number of candidates to fetch from ChromaDB before cross-encoder re-ranking
_INITIAL_CANDIDATES = 10


@dataclass
class StyleExample:
    """A single retrieved style example with metadata."""
    id: str
    style: str
    age_group: str
    tone: str
    text: str
    score: float          # cross-encoder relevance score (higher = better)
    latency_ms: float     # end-to-end retrieval latency


class StyleRetriever:
    """
    Two-stage style retriever backed by ChromaDB and a cross-encoder.

    Both the embedding model and the cross-encoder are loaded lazily on the
    first call to retrieve() to avoid startup cost when the module is imported.
    """

    def __init__(self) -> None:
        self._embed_model: Any = None
        self._cross_encoder: Any = None
        self._collection: Any = None

    # ------------------------------------------------------------------
    # Lazy initialisation helpers
    # ------------------------------------------------------------------

    def _get_embed_model(self):
        if self._embed_model is None:
            from sentence_transformers import SentenceTransformer
            logger.info("Loading embedding model %s", EMBED_MODEL_NAME)
            self._embed_model = SentenceTransformer(EMBED_MODEL_NAME)
        return self._embed_model

    def _get_cross_encoder(self):
        if self._cross_encoder is None:
            from sentence_transformers import CrossEncoder
            logger.info("Loading cross-encoder %s", CROSS_ENCODER_MODEL_NAME)
            self._cross_encoder = CrossEncoder(CROSS_ENCODER_MODEL_NAME)
        return self._cross_encoder

    def _get_collection(self):
        if self._collection is None:
            import chromadb
            client = chromadb.PersistentClient(path=_CHROMA_DIR)
            self._collection = client.get_collection(name=COLLECTION_NAME)
            logger.info(
                "Connected to ChromaDB collection '%s' (%d docs)",
                COLLECTION_NAME,
                self._collection.count(),
            )
        return self._collection

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def retrieve(
        self,
        caption: str,
        age_group: str,
        top_k: int = 3,
    ) -> list[StyleExample]:
        """
        Retrieve the most relevant style examples for a given caption.

        Parameters
        ----------
        caption : str
            Text description of the drawing (from the captioner model).
        age_group : str
            One of "4-6", "7-9", "10-12". Used to pre-filter ChromaDB results.
        top_k : int
            Number of style examples to return after re-ranking.

        Returns
        -------
        list[StyleExample]
            Top-k results, each carrying id, style, tone, text, score, latency_ms.
            latency_ms is identical on all returned objects — it is the total
            wall-clock time for both retrieval stages combined.
        """
        t_start = time.perf_counter()

        # Stage 1: vector search
        embed_model = self._get_embed_model()
        collection = self._get_collection()

        query_embedding = embed_model.encode(
            caption, normalize_embeddings=True
        ).tolist()

        n_candidates = min(_INITIAL_CANDIDATES, collection.count())
        # Request more candidates to account for age_group filtering reducing results
        n_fetch = min(n_candidates * 3, collection.count())

        results = collection.query(
            query_embeddings=[query_embedding],
            n_results=n_fetch,
            where={"age_group": {"$eq": age_group}},
            include=["documents", "metadatas", "distances"],
        )

        ids: list[str] = results["ids"][0]
        documents: list[str] = results["documents"][0]
        metadatas: list[dict] = results["metadatas"][0]

        # If age_group filter returns fewer results, fall back without filter
        if len(ids) < 1:
            logger.warning(
                "No results for age_group=%s; falling back to unfiltered search",
                age_group,
            )
            results = collection.query(
                query_embeddings=[query_embedding],
                n_results=n_candidates,
                include=["documents", "metadatas", "distances"],
            )
            ids = results["ids"][0]
            documents = results["documents"][0]
            metadatas = results["metadatas"][0]

        logger.debug("Stage 1 returned %d candidates", len(ids))

        # Stage 2: cross-encoder re-ranking
        cross_encoder = self._get_cross_encoder()
        pairs = [[caption, doc] for doc in documents]
        ce_scores: list[float] = cross_encoder.predict(pairs).tolist()

        # Sort by cross-encoder score descending and take top_k
        ranked = sorted(
            zip(ids, documents, metadatas, ce_scores),
            key=lambda x: x[3],
            reverse=True,
        )[:top_k]

        latency_ms = (time.perf_counter() - t_start) * 1000.0
        logger.info(
            "retrieve: caption=%r age_group=%s top_k=%d latency_ms=%.1f",
            caption[:60],
            age_group,
            top_k,
            latency_ms,
        )

        return [
            StyleExample(
                id=doc_id,
                style=meta.get("style", ""),
                age_group=meta.get("age_group", age_group),
                tone=meta.get("tone", ""),
                text=text,
                score=score,
                latency_ms=latency_ms,
            )
            for doc_id, text, meta, score in ranked
        ]
