Build a complete ML monitoring stack for a generative comic pipeline.

Create:
1. monitoring/metrics_exporter.py — FastAPI middleware (or standalone Prometheus exporter) that instruments the comic pipeline. Expose:
   - pipeline_stage_duration_seconds{stage} histogram
   - caption_word_count histogram (buckets: 0,5,10,20,30,50)
   - story_panel_count histogram
   - safety_score histogram (Detoxify toxicity score 0–1)
   - jobs_total{status} counter
   - queue_depth gauge (reads from Redis)

2. monitoring/drift_reporter.py — Evidently-based drift report job. Loads last 100 production captions from a SQLite log, compares against a reference set (first 100 processed). Generates: DataDriftReport for caption_word_count and caption_embedding_cosine_distance. Saves JSON report to ./reports/drift_{timestamp}.json.

3. monitoring/evidently_exporter.py — reads latest drift report JSON, extracts PSI scores per feature, exposes them as Prometheus gauges: ml_drift_psi{feature}. Runs as a standalone HTTP server on port 9101.

4. monitoring/docker-compose-monitoring.yml — adds to the existing compose: prometheus (scrapes :8000/metrics and :9101), grafana (port 3000, provisioned datasource), alertmanager.

5. monitoring/grafana/dashboard.json — Grafana dashboard JSON with panels: Caption Drift PSI (stat + time series), Safety Rejection Rate (time series), Pipeline P99 Latency by Stage (bar chart), Job Queue Depth (gauge), Story Vocabulary TTR (time series).

6. monitoring/alertmanager/config.yml — alert rule: ml_drift_psi{feature="caption_word_count"} > 0.2 for 15m → fires webhook to http://fastapi:8000/hooks/retrain.

7. app/routes/hooks.py — POST /hooks/retrain: validates HMAC signature, triggers act to run model-ci.yml, returns {triggered: true, run_id}.