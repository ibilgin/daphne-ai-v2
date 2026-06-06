"""
Evidently → Prometheus exporter.

Runs as a standalone HTTP server on port 9101.
Reads the most-recent drift report from ./reports/drift_*.json and exposes
per-feature PSI / drift scores as Prometheus gauges.

Metrics exposed
---------------
ml_drift_psi{feature="caption_word_count"}        — PSI / drift score from Evidently
ml_drift_detected{feature="caption_word_count"}   — 1.0 if drift detected, 0.0 otherwise
ml_embedding_cosine_distance                       — custom mean cosine distance

Usage
-----
    python -m monitoring.evidently_exporter          # listens on :9101
    python monitoring/evidently_exporter.py

Grafana / Prometheus scrapes http://evidently-exporter:9101/metrics every 60s.
The report is refreshed from disk on each scrape cycle (every 60s).

Evidently JSON schema note
--------------------------
Schema layout (evidently>=0.4, using report.as_dict()):
  report_dict["metrics"]  — list of metric result dicts
  Each metric dict has:
    "metric"  — class name string, e.g. "ColumnDriftMetric"
    "result"  — dict with the metric's result fields

  For ColumnDriftMetric:
    result["column_name"]   — feature name
    result["drift_score"]   — numeric PSI / drift score
    result["drift_detected"] — bool

  For DataDriftPreset (DatasetDriftMetric):
    result["drift_by_columns"]  — dict keyed by column name
      each value has:  drift_score, drift_detected, stattest_name
"""

from __future__ import annotations

import glob
import json
import logging
import os
import threading
import time
from pathlib import Path
from typing import Any

from prometheus_client import Gauge, start_http_server, REGISTRY

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
_PORT = int(os.environ.get("EVIDENTLY_EXPORTER_PORT", "9101"))
_REFRESH_INTERVAL_SECONDS = int(os.environ.get("EVIDENTLY_REFRESH_INTERVAL", "60"))
_MODULE_DIR = Path(__file__).parent
_REPORTS_DIR = Path(os.environ.get("EVIDENTLY_REPORTS_DIR", str(_MODULE_DIR / "reports")))

# ---------------------------------------------------------------------------
# Prometheus gauges (registered once at module load)
# ---------------------------------------------------------------------------

def _get_or_create_gauge(name: str, documentation: str, labelnames: list[str]) -> Gauge:
    if name in REGISTRY._names_to_collectors:  # noqa: SLF001
        return REGISTRY._names_to_collectors[name]  # noqa: SLF001
    return Gauge(name, documentation, labelnames=labelnames)


ml_drift_psi: Gauge = _get_or_create_gauge(
    "ml_drift_psi",
    "PSI / drift score for a feature computed by Evidently",
    labelnames=["feature"],
)

ml_drift_detected: Gauge = _get_or_create_gauge(
    "ml_drift_detected",
    "Whether Evidently detected drift for a feature (1.0=yes, 0.0=no)",
    labelnames=["feature"],
)

ml_embedding_cosine_distance: Gauge = _get_or_create_gauge(
    "ml_embedding_cosine_distance",
    "Mean cosine distance between reference and current caption embeddings",
    labelnames=[],
)

ml_report_timestamp: Gauge = _get_or_create_gauge(
    "ml_report_last_loaded_timestamp",
    "Unix timestamp when the most recent drift report was loaded",
    labelnames=[],
)


# ---------------------------------------------------------------------------
# Report loading & parsing
# ---------------------------------------------------------------------------

def _latest_report_path() -> Path | None:
    """Return the path to the most-recent drift_*.json report, or None."""
    pattern = str(_REPORTS_DIR / "drift_*.json")
    candidates = sorted(glob.glob(pattern))
    if not candidates:
        return None
    return Path(candidates[-1])


def _extract_drift_scores(report_dict: dict[str, Any]) -> dict[str, dict[str, Any]]:
    """
    Extract per-feature drift scores from an Evidently report dict.

    Returns a mapping of feature_name -> {drift_score, drift_detected}.

    Handles both:
      1. ColumnDriftMetric entries in report_dict["metrics"]
      2. DatasetDriftMetric / DataDriftPreset result["drift_by_columns"]
    """
    scores: dict[str, dict[str, Any]] = {}

    metrics_list = report_dict.get("metrics", [])
    if not isinstance(metrics_list, list):
        return scores

    for metric_entry in metrics_list:
        if not isinstance(metric_entry, dict):
            continue

        metric_class = metric_entry.get("metric", "")
        result = metric_entry.get("result", {})
        if not isinstance(result, dict):
            continue

        # ColumnDriftMetric — one entry per feature
        if metric_class == "ColumnDriftMetric":
            feature = result.get("column_name")
            drift_score = result.get("drift_score")
            drift_detected = result.get("drift_detected", False)
            if feature and drift_score is not None:
                scores[feature] = {
                    "drift_score": float(drift_score),
                    "drift_detected": bool(drift_detected),
                }

        # DatasetDriftMetric (from DataDriftPreset) — aggregates per column
        elif metric_class in ("DatasetDriftMetric", "DataDriftTable"):
            drift_by_columns = result.get("drift_by_columns", {})
            if isinstance(drift_by_columns, dict):
                for feature, col_result in drift_by_columns.items():
                    if not isinstance(col_result, dict):
                        continue
                    drift_score = col_result.get("drift_score")
                    drift_detected = col_result.get("drift_detected", False)
                    if drift_score is not None:
                        scores[feature] = {
                            "drift_score": float(drift_score),
                            "drift_detected": bool(drift_detected),
                        }

    return scores


def _update_metrics_from_report(report_path: Path) -> None:
    """Parse a drift report JSON and update all Prometheus gauges."""
    try:
        report_dict = json.loads(report_path.read_text(encoding="utf-8"))
    except Exception as exc:  # noqa: BLE001
        logger.error("evidently_exporter: could not read report %s — %s", report_path, exc)
        return

    # -- Drift scores --------------------------------------------------------
    scores = _extract_drift_scores(report_dict)
    for feature, vals in scores.items():
        ml_drift_psi.labels(feature=feature).set(vals["drift_score"])
        ml_drift_detected.labels(feature=feature).set(1.0 if vals["drift_detected"] else 0.0)
        logger.debug(
            "evidently_exporter: feature=%s drift_score=%.4f drift_detected=%s",
            feature,
            vals["drift_score"],
            vals["drift_detected"],
        )

    # -- Custom embedding distance -------------------------------------------
    custom = report_dict.get("custom_metrics", {})
    emb_metric = custom.get("caption_embedding_cosine_distance", {})
    if emb_metric.get("mean") is not None:
        ml_embedding_cosine_distance.labels().set(float(emb_metric["mean"]))
        logger.debug(
            "evidently_exporter: embedding_cosine_distance=%.4f",
            float(emb_metric["mean"]),
        )

    # -- Report load timestamp -----------------------------------------------
    ml_report_timestamp.labels().set(time.time())
    logger.info("evidently_exporter: metrics updated from %s", report_path.name)


# ---------------------------------------------------------------------------
# Refresh loop
# ---------------------------------------------------------------------------

def _refresh_loop() -> None:
    """Background thread: reload the latest report every _REFRESH_INTERVAL_SECONDS."""
    logger.info(
        "evidently_exporter: refresh loop started (interval=%ds, reports_dir=%s)",
        _REFRESH_INTERVAL_SECONDS,
        _REPORTS_DIR,
    )
    while True:
        try:
            report_path = _latest_report_path()
            if report_path:
                _update_metrics_from_report(report_path)
            else:
                logger.debug("evidently_exporter: no reports found yet in %s", _REPORTS_DIR)
        except Exception as exc:  # noqa: BLE001
            logger.error("evidently_exporter: refresh error — %s", exc)
        time.sleep(_REFRESH_INTERVAL_SECONDS)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s — %(message)s",
    )
    logger.info("evidently_exporter: starting HTTP server on port %d", _PORT)

    # Perform one immediate load before the server starts accepting scrapes
    report_path = _latest_report_path()
    if report_path:
        _update_metrics_from_report(report_path)
    else:
        logger.info("evidently_exporter: no drift report yet — metrics will update after first run")

    # Start Prometheus HTTP server
    start_http_server(_PORT)
    logger.info("evidently_exporter: listening on :%d/metrics", _PORT)

    # Start background refresh thread
    t = threading.Thread(target=_refresh_loop, daemon=True)
    t.start()

    # Block forever
    try:
        while True:
            time.sleep(3600)
    except KeyboardInterrupt:
        logger.info("evidently_exporter: shutting down")


if __name__ == "__main__":
    main()
