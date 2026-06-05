# Runbook: Read the Audit Log

**Purpose**: Query the `comic_audit` table to review inference events, inspect flagged safety cases, and produce compliance reports.

**Prerequisites**:
- PostgreSQL running (`docker compose up -d`)
- `psql` client available, or access to a DB GUI (e.g. pgAdmin, DBeaver)
- Database credentials from `backend/.env` (default: `postgres/postgres`, db `comicdb`)

---

## Database connection

```bash
psql -h localhost -p 5432 -U postgres -d comicdb
```

Or with the environment variable:

```bash
PGPASSWORD=postgres psql -h localhost -p 5432 -U postgres -d comicdb
```

---

## Steps

### 1. View recent audit entries

```sql
SELECT
    id,
    created_at,
    child_name_hash,
    style,
    age_group,
    safety_passed,
    toxicity_score,
    identity_attack_score,
    job_id
FROM comic_audit
ORDER BY created_at DESC
LIMIT 20;
```

### 2. Find flagged (failed safety gate) entries

```sql
SELECT *
FROM comic_audit
WHERE safety_passed = false
ORDER BY created_at DESC;
```

These rows indicate cases where the Detoxify safety gate blocked a generation. Review `toxicity_score` and `identity_attack_score` to determine which threshold was breached.

### 3. Filter by date range

```sql
SELECT
    DATE(created_at) AS date,
    COUNT(*) AS total_requests,
    SUM(CASE WHEN safety_passed THEN 1 ELSE 0 END) AS passed,
    SUM(CASE WHEN NOT safety_passed THEN 1 ELSE 0 END) AS failed
FROM comic_audit
WHERE created_at BETWEEN '2026-01-01' AND '2026-06-30'
GROUP BY DATE(created_at)
ORDER BY date;
```

### 4. Check for entries containing raw data (compliance check)

The audit log must **never** contain raw image bytes or child names. Verify:

```sql
-- Should return 0 rows if data minimisation is working correctly
SELECT COUNT(*)
FROM comic_audit
WHERE
    child_name IS NOT NULL   -- should always be NULL; only hash stored
    OR drawing_bytes IS NOT NULL;
```

Expected result: `0`.

### 5. Export flagged entries for human review

```bash
psql -h localhost -p 5432 -U postgres -d comicdb \
  -c "COPY (SELECT * FROM comic_audit WHERE safety_passed = false) TO STDOUT WITH CSV HEADER" \
  > flagged_entries_$(date +%Y%m%d).csv
```

Deliver the CSV to the designated human reviewer. Do not share child-identifying information.

---

## Verification

After any audit query, confirm no raw PII was logged:

```sql
SELECT column_name, data_type
FROM information_schema.columns
WHERE table_name = 'comic_audit';
```

Confirm that `child_name_hash` (SHA-256 hex string) is present but `child_name` (plaintext) is absent from the schema.

---

## Rollback / Remediation

If PII is discovered in the audit log (e.g. a migration error stored raw names):

1. Immediately notify the data protection officer.
2. Delete the offending rows:
   ```sql
   DELETE FROM comic_audit WHERE child_name IS NOT NULL;
   ```
3. Deploy a patched migration that adds a `NOT NULL` constraint on `child_name_hash` and a `CHECK (child_name IS NULL)` constraint.
4. Document the incident in the governance log.
