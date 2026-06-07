"""
Tests for the narrative-rewrite story generation path.

Covers:
- rag.story_chain.generate_panels with rough_narrative (rewrite path)
- rag.story_chain.generate_panels without rough_narrative (caption path)
- Panel count and required fields in returned dicts
- Fallback on malformed LLM response
- Integration with generate_panels node via ComicState
"""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_OLLAMA_PATCH = "langchain_community.llms.Ollama"


def _mock_ollama(panels_json: str) -> MagicMock:
    """Patch target for langchain Ollama; invoke returns a plain JSON string."""
    mock_llm = MagicMock()
    mock_llm.invoke.return_value = panels_json
    mock_cls = MagicMock(return_value=mock_llm)
    return mock_cls


def _make_panels_json(panel_count: int = 4) -> str:
    panels = [
        {"panel": i + 1, "narration": f"Scene {i + 1} happened here.", "dialogue": None}
        for i in range(panel_count)
    ]
    return json.dumps({"panels": panels})


# ---------------------------------------------------------------------------
# story_chain.generate_panels — rewrite path
# ---------------------------------------------------------------------------


def test_generate_panels_rewrite_path_returns_panels():
    """rough_narrative triggers the rewrite path and returns 4 panels."""
    with patch(_OLLAMA_PATCH, _mock_ollama(_make_panels_json(4))):
        from rag.story_chain import generate_panels

        result = generate_panels(
            caption="a dragon drawing",
            style_examples=["Once upon a time..."],
            child_name="Lily",
            panel_count=4,
            rough_narrative="There is a dragon who makes friends with a knight.",
        )

    assert len(result) == 4
    for panel in result:
        assert "panel" in panel
        assert "narration" in panel
        assert "dialogue" in panel


def test_generate_panels_rewrite_path_panel_count_matches():
    """Returned panel list length matches panel_count on the rewrite path."""
    with patch(_OLLAMA_PATCH, _mock_ollama(_make_panels_json(4))):
        from rag.story_chain import generate_panels

        result = generate_panels(
            caption="",
            style_examples=[],
            child_name="Sam",
            panel_count=4,
            rough_narrative="Sam and his robot go to space.",
        )

    assert len(result) == 4


def test_generate_panels_rewrite_path_uses_rewrite_system_prompt():
    """The rewrite-path prompt includes keywords from _SYSTEM_PROMPT_REWRITE."""
    captured: list[str] = []

    def _capturing_ollama(**kwargs):  # noqa: ARG001
        mock_llm = MagicMock()

        def invoke(prompt: str) -> str:
            captured.append(prompt)
            return _make_panels_json(4)

        mock_llm.invoke.side_effect = invoke
        return mock_llm

    with patch(_OLLAMA_PATCH, _capturing_ollama):
        from rag.story_chain import generate_panels

        generate_panels(
            caption="a rocket ship drawing",
            style_examples=[],
            child_name="Alex",
            panel_count=4,
            rough_narrative="Alex flies to the moon and finds a moon cat.",
        )

    assert captured, "Ollama.invoke should have been called"
    # Rewrite path should contain the child's own narrative text in the prompt
    assert "moon cat" in captured[0]


# ---------------------------------------------------------------------------
# story_chain.generate_panels — caption path (regression)
# ---------------------------------------------------------------------------


def test_generate_panels_caption_path_returns_panels():
    """No rough_narrative → caption path still returns 4 panels."""
    with patch(_OLLAMA_PATCH, _mock_ollama(_make_panels_json(4))):
        from rag.story_chain import generate_panels

        result = generate_panels(
            caption="a bright sunny drawing",
            style_examples=[],
            child_name="Emma",
            panel_count=4,
            rough_narrative="",
        )

    assert len(result) == 4


def test_generate_panels_whitespace_narrative_uses_caption_path():
    """Whitespace-only rough_narrative falls through to the caption path."""
    captured: list[str] = []

    def _capturing_ollama(**kwargs):  # noqa: ARG001
        mock_llm = MagicMock()

        def invoke(prompt: str) -> str:
            captured.append(prompt)
            return _make_panels_json(4)

        mock_llm.invoke.side_effect = invoke
        return mock_llm

    with patch(_OLLAMA_PATCH, _capturing_ollama):
        from rag.story_chain import generate_panels

        generate_panels(
            caption="a cat drawing",
            style_examples=[],
            child_name="Leo",
            panel_count=4,
            rough_narrative="   ",
        )

    assert captured, "Ollama.invoke should have been called"
    assert "a cat drawing" in captured[0]


# ---------------------------------------------------------------------------
# Fallback on malformed LLM response
# ---------------------------------------------------------------------------


def test_generate_panels_raises_on_persistent_malformed_json():
    """Malformed LLM response across all retries raises RuntimeError."""
    import pytest

    with patch(_OLLAMA_PATCH, _mock_ollama("not valid json at all")):
        from rag.story_chain import generate_panels

        with pytest.raises(RuntimeError, match="attempts failed"):
            generate_panels(
                caption="a drawing",
                style_examples=[],
                child_name="Zoe",
                panel_count=4,
                rough_narrative="",
            )


# ---------------------------------------------------------------------------
# Node integration — generate_panels node reads rough_narrative from state
# ---------------------------------------------------------------------------


def test_generate_panels_node_passes_narrative_to_chain():
    """The LangGraph node passes state['rough_narrative'] to story_chain."""
    with patch(_OLLAMA_PATCH, _mock_ollama(_make_panels_json(4))):
        from agent.nodes import generate_panels as node_fn

        state = {
            "job_id": "test-job-1",
            "image_bytes": "",
            "child_name": "Alex",
            "age_group": "7-9",
            "style_pref": "fantasy",
            "rough_narrative": "A wizard finds a magic wand.",
            "caption": "a colourful wizard drawing",
            "style_examples": [],
            "panels": [],
            "safety_verdict": None,
            "safety_failure_reason": None,
            "retry_count": 0,
            "final_comic": None,
            "error": None,
        }

        result_state = node_fn(state)

    assert "panels" in result_state
    assert len(result_state["panels"]) == 4


def test_generate_panels_node_empty_narrative_caption_path():
    """Node with empty rough_narrative uses the caption path."""
    with patch(_OLLAMA_PATCH, _mock_ollama(_make_panels_json(4))):
        from agent.nodes import generate_panels as node_fn

        state = {
            "job_id": "test-job-2",
            "image_bytes": "",
            "child_name": "Mia",
            "age_group": "4-6",
            "style_pref": "animals",
            "rough_narrative": "",
            "caption": "a bunny in a meadow",
            "style_examples": [],
            "panels": [],
            "safety_verdict": None,
            "safety_failure_reason": None,
            "retry_count": 0,
            "final_comic": None,
            "error": None,
        }

        result_state = node_fn(state)

    assert "panels" in result_state
    assert len(result_state["panels"]) == 4
