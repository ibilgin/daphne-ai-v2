"""
LangGraph agent state definition.

ComicState is the single TypedDict that flows through every node in the
LangGraph StateGraph.  All node functions receive a ComicState and return
a ComicState — no side-effects other than audit logging and Redis progress
updates are permitted inside nodes.

Field notes
-----------
image_bytes       : base64-encoded drawing bytes.  Never written to disk or DB.
rough_narrative   : optional child-authored story idea passed from the API.
                    Empty string ("") when not provided.  Never persisted.
safety_verdict    : "PASS" | "FAIL" | None (None until check_safety runs).
retry_count       : incremented BEFORE re-entering generate_panels on FAIL.
final_comic       : serialised ComicSchema dict, set by assemble node.
error             : set by human_review ("escalated_to_review") or on fatal error.
"""

from __future__ import annotations

from typing import Dict, List, Optional, TypedDict


class ComicState(TypedDict):
    # Job identity
    job_id: str

    # Input data (raw bytes never persisted)
    image_bytes: str        # base64-encoded PNG/JPEG

    # Personalisation inputs
    child_name: str
    age_group: str          # "4-6" | "7-9" | "10-12"
    style_pref: str         # user-selected style preference hint
    rough_narrative: str    # optional child-authored story idea; "" when not provided

    # Pipeline intermediate values
    caption: Optional[str]
    style_examples: List[str]       # retrieved style example texts
    panels: List[Dict]              # raw panel dicts from story_chain

    # Safety gate
    safety_verdict: Optional[str]          # "PASS" | "FAIL"
    safety_failure_reason: Optional[str]   # human-readable failure detail for retry prompt

    # Retry tracking (incremented before re-entering generate_panels)
    retry_count: int

    # Final output
    final_comic: Optional[Dict]     # serialised ComicSchema

    # Error / escalation
    error: Optional[str]
