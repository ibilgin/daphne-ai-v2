"""
Tests for agent.panel_artist — seed-based per-panel image generation.
"""

from __future__ import annotations

import base64
import io

import pytest
from PIL import Image


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_seed_b64(width: int = 40, height: int = 30) -> str:
    """
    Return a small base64 JPEG with real pixel variation (colour gradient).

    A solid-colour seed produces an all-white sketch (the colour-dodge
    algorithm magnifies uniform images to maximum brightness), so this factory
    draws a gradient that survives the sketch effect and produces distinguishable
    tinted results across different panel_num / tint combinations.
    """
    import numpy as np

    arr = np.zeros((height, width, 3), dtype=np.uint8)
    for y in range(height):
        for x in range(width):
            arr[y, x] = [x * (255 // width), y * (255 // height), ((x + y) * 4) % 256]
    img = Image.fromarray(arr)
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=95)
    return base64.b64encode(buf.getvalue()).decode()


_SEED = _make_seed_b64()


def _decode(b64: str) -> bytes:
    return base64.b64decode(b64)


# ---------------------------------------------------------------------------
# Basic output checks
# ---------------------------------------------------------------------------


def test_draw_panel_image_returns_nonempty_base64():
    from agent.panel_artist import draw_panel_image

    b64 = draw_panel_image(_SEED, "Emma played in the sunny meadow.", panel_num=0)
    assert isinstance(b64, str) and len(b64) > 1000


def test_draw_panel_image_is_valid_jpeg():
    from agent.panel_artist import draw_panel_image

    b64 = draw_panel_image(_SEED, "A boat sailed across the ocean.", panel_num=0, style="adventure")
    img = Image.open(io.BytesIO(_decode(b64)))
    assert img.format == "JPEG"
    assert img.size == (400, 300)


# ---------------------------------------------------------------------------
# Per-panel uniqueness — different panel_num → different zoom + tint
# ---------------------------------------------------------------------------


def test_each_panel_produces_different_image():
    from agent.panel_artist import draw_panel_image

    narrations = [
        "The hero walked through the green forest.",
        "She sailed across the deep blue ocean.",
        "The rocket launched into outer space.",
        "They danced at the birthday party together.",
    ]
    images = [
        draw_panel_image(_SEED, n, panel_num=i, style="mystery")
        for i, n in enumerate(narrations)
    ]
    assert len(set(images)) == len(images), "Every panel should produce a unique image"


# ---------------------------------------------------------------------------
# Style variants
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("style", ["adventure", "fantasy", "friendship", "mystery", "space"])
def test_all_styles_render(style: str):
    from agent.panel_artist import draw_panel_image

    b64 = draw_panel_image(_SEED, "The hero set off on a great adventure.", panel_num=0, style=style)
    assert len(b64) > 500


# ---------------------------------------------------------------------------
# Mood tint selection — word-boundary matching and narration-first priority
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("narration,expected_tint", [
    # "rocket" → space group — word boundary prevents "fast" hitting "past"
    ("The rocket launched past the planets.", (40, 80, 200)),
    # "dragon" → fantasy group
    ("The dragon soared over the magic castle.", (180, 100, 240)),
    # "ocean" → ocean group
    ("Waves crashed as they crossed the ocean.", (60, 150, 230)),
    # "party" → celebration group
    ("They celebrated the birthday party together.", (255, 220, 50)),
])
def test_mood_tints_are_selected(narration: str, expected_tint: tuple):
    from agent.panel_artist import _pick_tint

    tint = _pick_tint(narration, "mystery", 0)  # style="mystery" should not override narration
    assert tint == expected_tint


def test_style_used_as_fallback_when_no_narration_keyword():
    """When narration has no keyword match, style name determines the tint."""
    from agent.panel_artist import _pick_tint

    # "mystery" style → night/mystery group
    tint = _pick_tint("Something happened one day.", "mystery", 0)
    assert tint == (80, 70, 160)  # night/mystery tint


# ---------------------------------------------------------------------------
# Node integration — enriches panel dicts
# ---------------------------------------------------------------------------


def test_generate_panel_images_node_enriches_panels():
    from agent.nodes import generate_panel_images

    state = {
        "job_id": "test-job",
        "image_bytes": _SEED,
        "child_name": "Lily",
        "age_group": "7-9",
        "style_pref": "mystery",    # mystery style → no adventure override
        "caption": "a drawing",
        "style_examples": [],
        "panels": [
            {"panel": 1, "narration": "Lily flew above the forest trees.", "dialogue": "Wow!"},
            {"panel": 2, "narration": "She reached the ocean shore.", "dialogue": None},
        ],
        "safety_verdict": None,
        "safety_failure_reason": None,
        "retry_count": 0,
        "final_comic": None,
        "error": None,
    }

    result = generate_panel_images(state)

    panels = result["panels"]
    assert len(panels) == 2
    for p in panels:
        assert "image_bytes_b64" in p
        assert len(p["image_bytes_b64"]) > 500
    # panel 0: forest tint + 0 % zoom  ≠  panel 1: ocean tint + 6 % zoom
    assert panels[0]["image_bytes_b64"] != panels[1]["image_bytes_b64"]


def test_generate_panel_images_uses_seed_not_generic():
    """The same narration + panel_num but different seeds should produce different output."""
    from agent.nodes import generate_panel_images

    seed_a = _make_seed_b64()                            # default gradient
    seed_b = _make_seed_b64(width=50, height=40)         # different size → different gradient

    def _run(seed: str) -> str:
        state = {
            "job_id": "test-seed-check",
            "image_bytes": seed,
            "child_name": "Max",
            "age_group": "5-6",
            "style_pref": "mystery",
            "caption": "a drawing",
            "style_examples": [],
            "panels": [{"panel": 1, "narration": "The hero walks forward.", "dialogue": None}],
            "safety_verdict": None,
            "safety_failure_reason": None,
            "retry_count": 0,
            "final_comic": None,
            "error": None,
        }
        return generate_panel_images(state)["panels"][0]["image_bytes_b64"]

    img_a = _run(seed_a)
    img_b = _run(seed_b)
    assert img_a != img_b, "Different seed images should produce different panel images"
