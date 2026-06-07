"""
LangChain story generation chain.

Takes a caption, retrieved style examples, child_name, and panel_count,
then calls Ollama Mistral (local) to produce structured JSON panels.

Retries up to 2 times on JSON parse failure before raising.

Usage
-----
    from rag.story_chain import generate_panels

    panels = generate_panels(
        caption="a child flying a red kite in a sunny park",
        style_examples=["The wind carried Marco far above the rooftops...",],
        child_name="Emma",
        panel_count=4,
    )
    # panels: [{"panel": 1, "narration": "...", "dialogue": "..."}, ...]
"""

from __future__ import annotations

import json
import logging
import os
from typing import Any

logger = logging.getLogger(__name__)

_DEFAULT_OLLAMA_URL = "http://localhost:11434"
_DEFAULT_MODEL = "mistral"
_MAX_RETRIES = 2

_SYSTEM_PROMPT = (
    "You are a creative children's comic book writer who writes age-appropriate, "
    "warm, and imaginative stories. Given an image caption, style examples, and a "
    "child's name, produce exactly {panel_count} comic panels. "
    "Each panel must have 'narration' (2-3 descriptive sentences) and 'dialogue' "
    "(a short character quote, or null if none). "
    "Keep all content child-friendly — no violence, fear, or adult themes. "
    "Respond ONLY with a JSON object in this exact format: "
    '{{"panels": [{{"panel": 1, "narration": "...", "dialogue": "..."}}, ...]}}'
)

_SYSTEM_PROMPT_REWRITE = (
    "You are a warm and imaginative children's book author. "
    "A child has shared a rough story idea. Your job is to bring their vision to life "
    "as exactly {panel_count} comic book panels, keeping their characters and ideas "
    "but writing in vivid, age-appropriate storybook language. "
    "Each panel must cover a distinct moment and have 'narration' (2-3 descriptive "
    "sentences) and 'dialogue' (a short character quote, or null if none). "
    "Preserve the child's imagination — do not replace their ideas, only enrich them. "
    "Keep all content child-friendly. "
    "Respond ONLY with a JSON object in this exact format: "
    '{{"panels": [{{"panel": 1, "narration": "...", "dialogue": "..."}}, ...]}}'
)


def _build_user_prompt(
    caption: str,
    style_examples: list[str],
    child_name: str,
    panel_count: int,
    safety_failure_reason: str | None = None,
) -> str:
    """Construct the user-facing prompt for caption-based generation."""
    lines = [
        f"Child's name: {child_name}",
        f"Image caption: {caption}",
        f"Number of panels: {panel_count}",
    ]
    if style_examples:
        lines.append("\nStyle examples to match:")
        for i, ex in enumerate(style_examples, 1):
            lines.append(f"  {i}. {ex}")
    if safety_failure_reason:
        lines.append(
            f"\nIMPORTANT: A previous version of this story was rejected because it "
            f"contained inappropriate content: {safety_failure_reason}. "
            "Please rewrite the story to be completely age-appropriate and positive."
        )
    return "\n".join(lines)


def _build_rewrite_prompt(
    rough_narrative: str,
    caption: str,
    child_name: str,
    panel_count: int,
    safety_failure_reason: str | None = None,
) -> str:
    """Construct the user-facing prompt for narrative rewriting."""
    lines = [
        f"Child's name: {child_name}",
        f"Image caption (for visual context): {caption}",
        f"Number of panels: {panel_count}",
        f"\nChild's rough story idea:\n{rough_narrative.strip()}",
    ]
    if safety_failure_reason:
        lines.append(
            f"\nIMPORTANT: A previous version was rejected: {safety_failure_reason}. "
            "Rewrite to be completely age-appropriate and positive."
        )
    return "\n".join(lines)


def _validate_panels(parsed: Any, panel_count: int) -> list[dict]:
    """Validate and normalise the parsed JSON response into a list of panel dicts."""
    if not isinstance(parsed, dict) or "panels" not in parsed:
        raise ValueError("Response missing top-level 'panels' key")
    panels = parsed["panels"]
    if not isinstance(panels, list):
        raise ValueError("'panels' must be a list")

    validated: list[dict] = []
    for i, p in enumerate(panels[:panel_count]):
        narration = p.get("narration")
        dialogue = p.get("dialogue")
        if not isinstance(narration, str) or not narration.strip():
            raise ValueError(f"Panel {i + 1} 'narration' must be a non-empty string")
        validated.append(
            {
                "panel": p.get("panel", i + 1),
                "narration": narration.strip(),
                "dialogue": dialogue.strip() if isinstance(dialogue, str) and dialogue.strip() else None,
            }
        )
    if len(validated) < panel_count:
        raise ValueError(f"Expected {panel_count} panels, got {len(validated)}")
    return validated


def generate_panels(
    caption: str,
    style_examples: list[str],
    child_name: str,
    panel_count: int = 4,
    safety_failure_reason: str | None = None,
    rough_narrative: str = "",
) -> list[dict]:
    """
    Generate comic panels via the LangChain → Ollama Mistral pipeline.

    Parameters
    ----------
    caption : str
        Image caption from the BLIP captioner.
    style_examples : list[str]
        Retrieved style example texts from the RAG retriever.
    child_name : str
        Used to personalise the story.
    panel_count : int
        Number of panels to generate.
    safety_failure_reason : str | None
        If this is a retry after a safety failure, include the reason so the
        model can avoid repeating the problematic content.
    rough_narrative : str
        Optional child-authored story idea.  When non-empty the model rewrites
        it into storybook panels instead of generating from the caption alone.

    Returns
    -------
    list[dict]
        Each dict: {"panel": int, "narration": str, "dialogue": str | None}

    Raises
    ------
    RuntimeError
        If all retry attempts fail to produce valid JSON.
    """
    from langchain_community.llms import Ollama  # noqa: PLC0415

    ollama_url = os.environ.get("OLLAMA_BASE_URL", _DEFAULT_OLLAMA_URL)
    model_name = os.environ.get("OLLAMA_MODEL", _DEFAULT_MODEL)

    if rough_narrative.strip():
        # Narrative-rewriting path: the child provided a story idea.
        system_prompt = _SYSTEM_PROMPT_REWRITE.format(panel_count=panel_count)
        user_prompt = _build_rewrite_prompt(
            rough_narrative, caption, child_name, panel_count, safety_failure_reason
        )
        logger.info("story_chain: using narrative-rewrite path (rough_narrative provided)")
    else:
        # Caption-based path: generate a story from the image description.
        system_prompt = _SYSTEM_PROMPT.format(panel_count=panel_count)
        user_prompt = _build_user_prompt(
            caption, style_examples, child_name, panel_count, safety_failure_reason
        )

    # Combine into a single prompt — Ollama LLM takes a plain string
    full_prompt = f"{system_prompt}\n\n{user_prompt}"

    llm = Ollama(
        base_url=ollama_url,
        model=model_name,
        format="json",
        temperature=0.7,
        num_predict=1024,
    )

    last_error: Exception | None = None

    for attempt in range(_MAX_RETRIES + 1):
        try:
            logger.info(
                "story_chain: attempt %d/%d ollama=%s model=%s",
                attempt + 1,
                _MAX_RETRIES + 1,
                ollama_url,
                model_name,
            )
            response = llm.invoke(full_prompt)
            raw_content: str = response if isinstance(response, str) else str(response)
            parsed = json.loads(raw_content)
            panels = _validate_panels(parsed, panel_count)
            logger.info("story_chain: generated %d panels successfully", len(panels))
            return panels

        except (json.JSONDecodeError, KeyError, ValueError) as exc:
            last_error = exc
            logger.warning(
                "story_chain: attempt %d/%d failed with parse error — %s",
                attempt + 1,
                _MAX_RETRIES + 1,
                exc,
            )
        except Exception as exc:  # noqa: BLE001
            last_error = exc
            logger.warning(
                "story_chain: attempt %d/%d failed with unexpected error — %s",
                attempt + 1,
                _MAX_RETRIES + 1,
                exc,
            )

    raise RuntimeError(
        f"story_chain: all {_MAX_RETRIES + 1} attempts failed. "
        f"Last error: {last_error}"
    )
