"""
ChromaDB indexer for the narrative style library.

Embeds each entry in style_library.json using sentence-transformers
all-MiniLM-L6-v2 (local, no external API) and stores them in a persistent
ChromaDB collection called 'narrative_styles'.

CLI usage
---------
    python indexer.py --rebuild   # delete and re-create the collection from scratch

The ChromaDB data directory is ./chroma_db relative to the backend/ root,
regardless of where this script is invoked from.
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
import time
from pathlib import Path
from typing import Any

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Paths — computed relative to this file so they are stable regardless of cwd
# ---------------------------------------------------------------------------
_THIS_DIR = Path(__file__).parent                    # backend/rag/
_BACKEND_DIR = _THIS_DIR.parent                      # backend/
_STYLE_LIBRARY_PATH = _THIS_DIR / "style_library.json"
_CHROMA_DIR = str(_BACKEND_DIR / "chroma_db")       # backend/chroma_db/

COLLECTION_NAME = "narrative_styles"
EMBED_MODEL_NAME = "all-MiniLM-L6-v2"


def _load_style_library() -> list[dict[str, Any]]:
    """Load and return all entries from style_library.json."""
    with _STYLE_LIBRARY_PATH.open(encoding="utf-8") as fh:
        entries = json.load(fh)
    logger.info("Loaded %d entries from style_library.json", len(entries))
    return entries


def _get_embedding_model():
    """Return a SentenceTransformer model (cached after first call)."""
    from sentence_transformers import SentenceTransformer
    logger.info("Loading embedding model %s …", EMBED_MODEL_NAME)
    model = SentenceTransformer(EMBED_MODEL_NAME)
    logger.info("Embedding model ready")
    return model


def _get_chroma_client():
    """Return a persistent ChromaDB client."""
    import chromadb
    os.makedirs(_CHROMA_DIR, exist_ok=True)
    client = chromadb.PersistentClient(path=_CHROMA_DIR)
    return client


def build_index(rebuild: bool = False) -> None:
    """
    Embed all style library entries and store them in ChromaDB.

    Parameters
    ----------
    rebuild : bool
        If True, delete the existing collection before re-creating it.
    """
    entries = _load_style_library()
    embed_model = _get_embedding_model()
    client = _get_chroma_client()

    # Handle rebuild
    if rebuild:
        existing = [c.name for c in client.list_collections()]
        if COLLECTION_NAME in existing:
            logger.info("Deleting existing collection '%s' for rebuild", COLLECTION_NAME)
            client.delete_collection(COLLECTION_NAME)

    collection = client.get_or_create_collection(
        name=COLLECTION_NAME,
        metadata={"hnsw:space": "cosine"},
    )

    current_count = collection.count()
    if current_count > 0 and not rebuild:
        logger.info(
            "Collection '%s' already has %d documents. Use --rebuild to re-index.",
            COLLECTION_NAME,
            current_count,
        )
        return

    # Embed all texts
    texts = [entry["text"] for entry in entries]
    t0 = time.perf_counter()
    embeddings = embed_model.encode(texts, show_progress_bar=True, normalize_embeddings=True)
    elapsed = (time.perf_counter() - t0) * 1000
    logger.info("Embedded %d texts in %.0f ms", len(texts), elapsed)

    # Prepare ChromaDB payloads
    ids = [entry["id"] for entry in entries]
    metadatas = [
        {
            "style": entry["style"],
            "age_group": entry["age_group"],
            "tone": entry["tone"],
        }
        for entry in entries
    ]

    collection.add(
        ids=ids,
        embeddings=embeddings.tolist(),
        documents=texts,
        metadatas=metadatas,
    )
    logger.info(
        "Indexed %d entries into collection '%s' at %s",
        len(entries),
        COLLECTION_NAME,
        _CHROMA_DIR,
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Build/rebuild the ChromaDB style index")
    parser.add_argument(
        "--rebuild",
        action="store_true",
        help="Delete and re-create the collection from scratch",
    )
    args = parser.parse_args()
    build_index(rebuild=args.rebuild)
    logger.info("Done.")


if __name__ == "__main__":
    main()
