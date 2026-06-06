"""
RAG evaluation harness.

Loads 15 (caption, expected_style) test pairs, runs the StyleRetriever,
computes precision@3 (did the expected style appear in the top-3 returned?),
and logs metrics to the MLflow experiment 'rag-eval'.

Also prints a per-style breakdown table.

Usage
-----
    cd backend
    python -m rag.eval
    # or
    python rag/eval.py
"""

from __future__ import annotations

import logging
import sys
from pathlib import Path

# Ensure backend/ is on the path when run directly
_BACKEND_DIR = Path(__file__).parent.parent
sys.path.insert(0, str(_BACKEND_DIR))

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Test pairs: (caption, expected_style)
# Chosen to stress the retriever across all 6 styles.
# ---------------------------------------------------------------------------
TEST_PAIRS: list[tuple[str, str]] = [
    # adventure
    ("a child hiking through a dense forest with a backpack and compass", "adventure"),
    ("a girl climbing a rocky cliff to reach the peak", "adventure"),
    ("two friends paddling a wooden raft down a wide river", "adventure"),
    # fantasy
    ("a small dragon sitting on a pile of books in a magical library", "fantasy"),
    ("a child riding a unicorn through a glowing enchanted meadow", "fantasy"),
    ("a fairy sprinkling golden dust over sleeping flowers at night", "fantasy"),
    # friendship
    ("two children sharing an umbrella in the rain on the way to school", "friendship"),
    ("a girl handing her friend a handmade birthday card", "friendship"),
    ("three kids laughing together at a picnic in the park", "friendship"),
    # mystery
    ("a child with a magnifying glass examining muddy footprints near a garden shed", "mystery"),
    ("a girl reading a coded message found tucked inside an old library book", "mystery"),
    ("a boy noticing that the lights in an empty house turn on every midnight", "mystery"),
    # animals
    ("a duckling following its mother across a busy road while cars wait", "animals"),
    ("a child sitting quietly beside a sleeping rescue cat on a sofa", "animals"),
    ("a fox kit peeking out from behind a tree at the edge of a meadow", "animals"),
    # space — added as bonus; we only assert on the first 15
]

# Use exactly 15 pairs (trim to 15 to match the spec)
TEST_PAIRS = TEST_PAIRS[:15]


def run_eval() -> None:
    """Run retrieval evaluation and log results to MLflow."""
    import mlflow

    from rag.retriever import StyleRetriever

    retriever = StyleRetriever()

    # Default to age_group "7-9" for evaluation (balanced mid-group)
    eval_age_group = "7-9"

    hits_by_style: dict[str, list[bool]] = {}
    latencies: list[float] = []

    logger.info("Running RAG evaluation on %d test pairs …", len(TEST_PAIRS))

    results_rows: list[dict] = []
    for caption, expected_style in TEST_PAIRS:
        examples = retriever.retrieve(caption, age_group=eval_age_group, top_k=3)
        retrieved_styles = [ex.style for ex in examples]
        latency = examples[0].latency_ms if examples else 0.0
        latencies.append(latency)

        hit = expected_style in retrieved_styles
        hits_by_style.setdefault(expected_style, []).append(hit)

        results_rows.append(
            {
                "caption": caption[:60],
                "expected": expected_style,
                "retrieved": retrieved_styles,
                "hit": hit,
                "latency_ms": latency,
            }
        )
        logger.debug(
            "caption=%r expected=%s retrieved=%s hit=%s",
            caption[:40],
            expected_style,
            retrieved_styles,
            hit,
        )

    # ---------------------------------------------------------------------------
    # Compute metrics
    # ---------------------------------------------------------------------------
    total_hits = sum(r["hit"] for r in results_rows)
    precision_at_3 = total_hits / len(TEST_PAIRS)
    mean_latency_ms = sum(latencies) / len(latencies) if latencies else 0.0

    per_style_precision: dict[str, float] = {
        style: sum(hits) / len(hits)
        for style, hits in hits_by_style.items()
    }

    # ---------------------------------------------------------------------------
    # Print breakdown table
    # ---------------------------------------------------------------------------
    print("\n" + "=" * 60)
    print(f"  RAG Evaluation — precision@3 = {precision_at_3:.3f}")
    print(f"  Mean latency: {mean_latency_ms:.0f} ms  |  Test pairs: {len(TEST_PAIRS)}")
    print("=" * 60)
    print(f"  {'Style':<15} {'Hits/Total':<12} {'Precision'}")
    print("  " + "-" * 45)
    for style, hits in hits_by_style.items():
        n = len(hits)
        h = sum(hits)
        print(f"  {style:<15} {h}/{n:<11} {h / n:.3f}")
    print("=" * 60)
    print("\nPer-caption results:")
    print(f"  {'Caption':<45} {'Expected':<12} {'Retrieved':<30} {'Hit'}")
    print("  " + "-" * 100)
    for row in results_rows:
        hit_mark = "YES" if row["hit"] else " NO"
        retrieved_str = str(row["retrieved"])
        print(
            f"  {row['caption']:<45} {row['expected']:<12} {retrieved_str:<30} {hit_mark}"
        )
    print()

    # ---------------------------------------------------------------------------
    # Log to MLflow
    # ---------------------------------------------------------------------------
    mlflow.set_experiment("rag-eval")
    with mlflow.start_run(run_name="rag-precision-eval"):
        mlflow.log_metric("precision_at_3", precision_at_3)
        mlflow.log_metric("mean_latency_ms", mean_latency_ms)
        mlflow.log_metric("total_test_pairs", len(TEST_PAIRS))
        mlflow.log_metric("total_hits", total_hits)

        for style, prec in per_style_precision.items():
            mlflow.log_metric(f"precision_at_3_{style}", prec)

        mlflow.log_param("eval_age_group", eval_age_group)
        mlflow.log_param("top_k", 3)
        mlflow.log_param("embed_model", "all-MiniLM-L6-v2")
        mlflow.log_param("cross_encoder", "cross-encoder/ms-marco-MiniLM-L-6-v2")

        logger.info(
            "MLflow run logged: precision_at_3=%.3f mean_latency_ms=%.0f",
            precision_at_3,
            mean_latency_ms,
        )


if __name__ == "__main__":
    run_eval()
