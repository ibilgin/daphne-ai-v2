---
description: Implement a specific phase. Usage: /implement-phase N (e.g. /implement-phase 1). Reads the phase doc and builds all deliverables using the appropriate specialist agent.
---

Implement Phase $ARGUMENTS of the Sketch to Story project.

Follow this process:

1. **Read the phase spec**: Read `docs/phase$ARGUMENTS/` — find all `.md` files in that folder and read each one carefully. These are the exact prompts/specs for what to build.

2. **Check prerequisites**: Run `/phase-status` logic to confirm all previous phases are complete before starting. If a prerequisite phase is missing, stop and inform the user.

3. **Create the phase branch** (if not already on it):
   ```bash
   git checkout -b phase/$ARGUMENTS-<name>
   ```
   Use these branch names: 1→mlops, 2→serving, 3→rag-agent, 4→monitoring, 5→governance, 6→frontend

4. **Implement all deliverables** listed in the phase spec(s). Build every file described — do not skip any deliverable. Follow the constraints in CLAUDE.md.

5. **Write tests** where the spec calls for them. For Phases 1-2, ensure `tests/test_captioner.py` and `tests/test_storyteller.py` exist.

6. **Verify correctness**:
   - Python files: check for syntax errors with `python -m py_compile`
   - Phase 1: confirm model pyfunc interface matches `model_loader.py`
   - Phase 2: confirm ComicSchema matches what the Vue store expects
   - Phase 3: verify LangGraph `graph.get_graph().draw_mermaid()` shows the safety retry loop
   - Phase 4: verify Prometheus metrics names match what's in the Grafana dashboard
   - Phase 5: run `python backend/governance/gate_runner.py` and check exit code
   - Phase 6: verify BFF proxy and HTML export route are both present

7. **Commit the work**:
   ```bash
   git add <all new files>
   git commit -m "feat(phase$ARGUMENTS): <summary of what was built>"
   ```

8. **Report**: List all files created, note any manual steps required (e.g. `docker compose up -d` to start services, `python scripts/register_models.py` to register models).

Use the specialist agents for each phase:
- Phase 1 → mlops-engineer
- Phase 2 → api-serving-engineer
- Phase 3 → rag-agent-engineer
- Phase 4 → ml-observability
- Phase 5 → security-governance
- Phase 6 → frontend-engineer
