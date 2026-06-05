"""
LangSmith local tracing configuration for the comic generation agent.

Configures LangSmith to use a local SQLite backend (no external API key
required) and exposes run_agent() — the single entry point that wraps
compiled_graph.invoke() with full LangSmith tracing.

Each trace is named comic-generation-{job_id} so runs can be correlated
with the Celery job in logs and the LangSmith UI.

Local LangSmith backend
-----------------------
LangSmith can run locally via the `langsmith` package's built-in SQLite store.
Environment variables set here point to localhost:1984 where the local server
must be running (or are set to no-op if unavailable).
"""

from __future__ import annotations

import logging
import os

from agent.state import ComicState

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# LangSmith local configuration
# ---------------------------------------------------------------------------
_LANGSMITH_ENDPOINT = os.environ.get("LANGCHAIN_ENDPOINT", "http://localhost:1984")
_LANGSMITH_PROJECT = os.environ.get("LANGCHAIN_PROJECT", "sketch-to-story")


def _configure_langsmith() -> None:
    """Set LangSmith environment variables for local tracing."""
    os.environ.setdefault("LANGCHAIN_TRACING_V2", "true")
    os.environ.setdefault("LANGCHAIN_ENDPOINT", _LANGSMITH_ENDPOINT)
    os.environ.setdefault("LANGCHAIN_PROJECT", _LANGSMITH_PROJECT)
    # No API key required for local SQLite backend
    os.environ.setdefault("LANGCHAIN_API_KEY", "local")
    logger.debug(
        "LangSmith configured: endpoint=%s project=%s",
        _LANGSMITH_ENDPOINT,
        _LANGSMITH_PROJECT,
    )


# Configure on module import
_configure_langsmith()


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def run_agent(state: ComicState) -> ComicState:
    """
    Invoke the LangGraph compiled graph with LangSmith tracing.

    Each invocation creates a trace named comic-generation-{job_id} that
    records per-node timings, inputs, and outputs in the local LangSmith store.

    Parameters
    ----------
    state : ComicState
        The initial state dict.  Must include at least job_id, image_bytes,
        child_name, age_group, style_pref, and retry_count (typically 0).

    Returns
    -------
    ComicState
        The final state after the graph has finished executing (all nodes run).
    """
    from langchain_core.tracers.context import tracing_v2_enabled

    from agent.graph import compiled_graph

    job_id = state.get("job_id", "unknown")
    run_name = f"comic-generation-{job_id}"

    logger.info("run_agent: starting job_id=%s run_name=%s", job_id, run_name)

    try:
        with tracing_v2_enabled(project_name=_LANGSMITH_PROJECT):
            result: ComicState = compiled_graph.invoke(
                state,
                config={"run_name": run_name},
            )
    except Exception:
        # If LangSmith tracing is unavailable, fall back to untraced execution
        logger.warning(
            "run_agent: LangSmith tracing unavailable — running without tracing"
        )
        result = compiled_graph.invoke(state)

    logger.info(
        "run_agent: completed job_id=%s error=%s",
        job_id,
        result.get("error"),
    )
    return result
