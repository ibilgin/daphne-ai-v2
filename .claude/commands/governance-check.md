---
description: Run the governance gate runner and report which checks pass or fail. Blocks model promotion if any required check fails. Usage: /governance-check
---

Run the governance gate for the Sketch to Story project and report results.

Steps:

1. **Check governance.yaml exists**:
   ```bash
   ls backend/governance/governance.yaml
   ```
   If missing: "Phase 5 has not been implemented yet. Run `/implement-phase 5` first."

2. **Show current governance.yaml state**:
   ```bash
   cat backend/governance/governance.yaml
   ```

3. **Run the gate runner**:
   ```bash
   cd backend && python governance/gate_runner.py
   echo "Exit code: $?"
   ```

4. **Parse and report results** in a clear table:

   | Check | Required | Status | Last Verified | Result |
   |-------|----------|--------|---------------|--------|
   | child_safety_gate_present | ✅ | pass/fail/pending | date | ✅/❌ |
   | ...

5. **For each failing or stale check**, explain what needs to be done:
   - `child_safety_gate_present`: Verify `backend/security/safety_gate.py` exists and `check_safety` node in LangGraph calls it
   - `audit_log_enabled`: Verify `backend/security/audit_log.py` and that `app/tasks.py` calls `AuditLogger.log_job()`
   - `data_minimisation_verified`: Verify `audit_log.py` stores only hashes, not raw images/text
   - `input_validation_present`: Verify `backend/security/input_validator.py` is called in the generate-comic route
   - `model_card_generated`: Run `python governance/model_card_generator.py` for both models
   - `bias_audit_complete`: Run `python governance/bias_audit.py` and check demographic_parity_diff < 0.15
   - `vault_secrets_confirmed`: Run `grep -r "password\|secret\|key" backend/ --include="*.py" | grep -v vault_client | grep -v "# "` to check for hardcoded secrets
   - `rollback_tested`: Run `/model-rollback` to test the rollback workflow

6. **Update governance.yaml** with `last_verified` timestamps for any checks you just verified.

7. **Summary**: Report GATE PASSED or GATE FAILED. If failed, list what must be fixed before running `/model-promote`.
