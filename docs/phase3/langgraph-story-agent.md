Rewrite the comic generation pipeline as a LangGraph stateful agent with safety retry logic and LangSmith tracing.

Create:
1. agent/state.py — TypedDict ComicState: {job_id, image_bytes, child_name, age_group, style_pref, caption, style_examples, panels, safety_verdict, retry_count, final_comic, error}.

2. agent/nodes.py — implement each node as a pure function (state: ComicState) -> ComicState:
   - analyse_drawing: calls BLIP-2 captioner (mlflow.pyfunc), sets state["caption"]
   - retrieve_style: calls StyleRetriever from Phase 3, sets state["style_examples"]
   - generate_panels: calls LangChain story_chain, sets state["panels"]
   - check_safety: runs Detoxify on all narration + dialogue text. Sets state["safety_verdict"] = "PASS"|"FAIL". If FAIL, appends safety failure reason to state for prompt augmentation on retry.
   - assemble: structures final ComicSchema (Pydantic from Phase 2), sets state["final_comic"]
   - human_review: writes job to Postgres review queue table with all state fields, sets status = "pending_review"

3. agent/graph.py — build LangGraph StateGraph: add all nodes, add conditional edge from check_safety: PASS → assemble, FAIL + retry_count < 2 → generate_panels (with incremented retry_count), FAIL + retry_count >= 2 → human_review.

4. agent/tracing.py — configure LangSmith to run locally (SQLite backend), wrap graph execution with trace context. Each run produces a trace with node timings.

5. Update app/tasks.py from Phase 2 to invoke the LangGraph agent instead of the direct pipeline. Progress updates (Redis) now come from node transitions.