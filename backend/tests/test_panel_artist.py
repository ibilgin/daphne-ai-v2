"""
Tests for agent.panel_artist — per-panel image generation.
"""

from __future__ import annotations

import base64

import pytest


def _decode(b64: str) -> bytes:
    return base64.b64decode(b64)


def test_draw_panel_image_returns_nonempty_base64():
    from agent.panel_artist import draw_panel_image

    b64 = draw_panel_image("Emma played in the sunny meadow.", panel_num=0)
    assert isinstance(b64, str) and len(b64) > 1000


def test_draw_panel_image_is_valid_jpeg():
    from agent.panel_artist import draw_panel_image
    from PIL import Image
    import io

    b64 = draw_panel_image("A boat sailed across the ocean.", panel_num=0, style="adventure")
    img = Image.open(io.BytesIO(_decode(b64)))
    assert img.format == "JPEG"
    assert img.size == (400, 300)


def test_each_panel_produces_different_image():
    from agent.panel_artist import draw_panel_image

    narrations = [
        "Once upon a time a child flew above the clouds.",
        "The forest was dark and full of ancient trees.",
        "They sailed across the endless ocean together.",
        "Rockets blasted through the stars of outer space.",
    ]
    images = [draw_panel_image(n, i, "adventure") for i, n in enumerate(narrations)]
    # All images must differ (different panel_num → different scenes)
    assert len(set(images)) == len(images), "Every panel should produce a unique image"


@pytest.mark.parametrize("style", ["adventure", "fantasy", "friendship", "mystery", "space"])
def test_all_styles_render(style: str):
    from agent.panel_artist import draw_panel_image

    b64 = draw_panel_image("The hero set off on a great adventure.", panel_num=0, style=style)
    assert len(b64) > 500


@pytest.mark.parametrize("narration,expected_scene", [
    ("The rocket flew past the planets and stars.", "space"),
    ("The dragon soared over the magic castle.", "fantasy_castle"),
    ("Waves crashed as they sailed the ocean.", "ocean"),
    ("They climbed to the top of the mountain.", "mountain"),
])
def test_scene_detection(narration: str, expected_scene: str):
    from agent.panel_artist import _detect_scene

    assert _detect_scene(narration) == expected_scene


def test_generate_panel_images_node_enriches_panels():
    from agent.nodes import generate_panel_images

    state = {
        "job_id": "test-job",
        "image_bytes": "",
        "child_name": "Lily",
        "age_group": "7-9",
        "style_pref": "adventure",
        "caption": "a drawing",
        "style_examples": [],
        "panels": [
            {"panel": 1, "narration": "Lily found a treasure chest.", "dialogue": "Wow!"},
            {"panel": 2, "narration": "She opened it slowly.", "dialogue": None},
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
    # Each panel should have a different image
    assert panels[0]["image_bytes_b64"] != panels[1]["image_bytes_b64"]
