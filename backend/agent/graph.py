"""
LangGraph StateGraph for comic generation.

Graph topology
--------------
START
  → analyse_drawing   (caption)
  → retrieve_style    (style_examples)
  → generate_panels   (panels)
  → check_safety      (safety_verdict)
        PASS → assemble → END
        FAIL + retry_count < 2 → generate_panels  (retry_count incremented here)
        FAIL + retry_count >= 2 → human_review → END

The compiled graph is exported as `compiled_graph`.

Usage
-----
    from agent.graph import compiled_graph
    result_state = compiled_graph.invoke(initial_state)
"""

from __future__ import annotations

import logging

from langgraph.graph import END, START, StateGraph

from agent.nodes import (
    analyse_drawing,
    assemble,
    check_safety,
    generate_panels,
    human_review,
    retrieve_style,
)
from agent.state import ComicState

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Node name constants — single source of truth to avoid string typos
# ---------------------------------------------------------------------------
_ANALYSE = "analyse_drawing"
_RETRIEVE = "retrieve_style"
_GENERATE = "generate_panels"
_SAFETY = "check_safety"
_ASSEMBLE = "assemble"
_REVIEW = "human_review"

# ---------------------------------------------------------------------------
# Safety routing function
# ---------------------------------------------------------------------------

_MAX_RETRIES = 2


def _route_safety(state: ComicState) -> str:
    """
    Conditional edge from check_safety.

    Returns the name of the next node to execute.
    retry_count is incremented here — before re-entering generate_panels —
    so that the panels node always sees the current count.
    """
    verdict = state.get("safety_verdict", "FAIL")
    retry_count = state.get("retry_count", 0)

    if verdict == "PASS":
        logger.info("route_safety: PASS → assemble")
        return _ASSEMBLE

    if retry_count < _MAX_RETRIES:
        # Increment retry_count in state before routing back
        state["retry_count"] = retry_count + 1
        logger.info(
            "route_safety: FAIL → generate_panels (retry %d/%d)",
            state["retry_count"],
            _MAX_RETRIES,
        )
        return _GENERATE

    logger.warning(
        "route_safety: FAIL after %d retries → human_review", retry_count
    )
    return _REVIEW


# ---------------------------------------------------------------------------
# Build the graph
# ---------------------------------------------------------------------------

def _build_graph() -> StateGraph:
    builder = StateGraph(ComicState)

    # Add all nodes
    builder.add_node(_ANALYSE, analyse_drawing)
    builder.add_node(_RETRIEVE, retrieve_style)
    builder.add_node(_GENERATE, generate_panels)
    builder.add_node(_SAFETY, check_safety)
    builder.add_node(_ASSEMBLE, assemble)
    builder.add_node(_REVIEW, human_review)

    # Linear edges
    builder.add_edge(START, _ANALYSE)
    builder.add_edge(_ANALYSE, _RETRIEVE)
    builder.add_edge(_RETRIEVE, _GENERATE)
    builder.add_edge(_GENERATE, _SAFETY)

    # Conditional edge from check_safety
    builder.add_conditional_edges(
        _SAFETY,
        _route_safety,
        {
            _ASSEMBLE: _ASSEMBLE,
            _GENERATE: _GENERATE,
            _REVIEW: _REVIEW,
        },
    )

    # Terminal edges
    builder.add_edge(_ASSEMBLE, END)
    builder.add_edge(_REVIEW, END)

    return builder


# ---------------------------------------------------------------------------
# Compile once at module level — import `compiled_graph` anywhere
# ---------------------------------------------------------------------------

compiled_graph = _build_graph().compile()
logger.info("LangGraph comic agent compiled successfully")


if __name__ == "__main__":
    # Quick sanity check: print the Mermaid diagram to stdout
    print(compiled_graph.get_graph().draw_mermaid())
