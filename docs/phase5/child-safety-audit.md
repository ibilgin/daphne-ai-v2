Add a child safety governance layer, audit logging, JWT RBAC, and HashiCorp Vault secret management to a FastAPI comic generation service.

Create:
1. security/safety_gate.py — SafetyGate class. check_story(panels: list[PanelSchema]) -> SafetyResult {verdict: PASS|FAIL, scores: dict[panel_id, float], reason: str | None}. Uses Detoxify multilingual model. Flag if any panel toxicity > 0.1 OR identity_attack > 0.05. Returns structured result for the LangGraph node (Phase 3).

2. security/input_validator.py — validate_image(image_bytes: bytes) -> ValidationResult. Checks: file size < 5MB, valid image magic bytes, image std deviation > 10 (not blank), aspect ratio 0.3–3.0. Returns {valid: bool, reason: str | None}. Runs before any model call.

3. security/audit_log.py — AuditLogger class using SQLAlchemy async. Table: comic_audit(id UUID PK, user_id str, image_hash str, caption_hash str, story_hash str, safety_verdict str, safety_scores JSONB, stage_timings JSONB, model_versions JSONB, created_at timestamp). Methods: log_job(job_id, ...), query_by_user(user_id, limit), query_flagged(since: datetime).

4. security/auth.py — JWT middleware for FastAPI. Roles: parent (can POST /api/generate-comic, GET /api/comics/{id}), admin (can GET /api/audit, GET /api/jobs), platform (can call /internal/* routes). decode_token(), require_role(role: str) dependency factory. Include a create_token() helper for local testing.

5. security/vault_client.py — VaultClient using hvac. On startup: authenticate with dev root token, read secret/comic-platform/config, return dict of secrets (minio_access_key, minio_secret_key, db_password, jwt_secret). Integrate into app/config.py replacing hardcoded values.

6. Update app/tasks.py to call AuditLogger.log_job() at task completion with all required fields.