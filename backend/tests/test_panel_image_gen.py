"""
Tests for models.panel_image_gen — pluggable img2img MLflow pyfunc.

Covers:
- PIL fallback path (no API key required)
- Output schema: {"image_b64": str}
- DataFrame and dict input formats
- Backend selection via PANEL_IMG_GEN_BACKEND env var
- Missing seed image → placeholder returned, no crash
- generate_panel_images LangGraph node integration (PIL fallback)
"""

from __future__ import annotations

import base64
import io
import os

import pandas as pd
import pytest
from PIL import Image


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_seed_b64(width: int = 40, height: int = 30) -> str:
    """Return a small gradient JPEG as base64 (survives pencil-sketch effect)."""
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


def _is_valid_jpeg(b64: str) -> bool:
    try:
        data = base64.b64decode(b64)
        img = Image.open(io.BytesIO(data))
        img.verify()
        return True
    except Exception:
        return False


# ---------------------------------------------------------------------------
# PIL fallback via _pil_fallback (imported directly)
# ---------------------------------------------------------------------------


def test_pil_fallback_returns_valid_jpeg():
    from models.panel_image_gen import _pil_fallback

    result_b64 = _pil_fallback(_SEED, "A dragon soars over the mountains.", 0, "fantasy")
    assert result_b64, "Expected non-empty base64 string"
    assert _is_valid_jpeg(result_b64)


def test_pil_fallback_returns_different_images_per_panel():
    from models.panel_image_gen import _pil_fallback

    img0 = _pil_fallback(_SEED, "Panel one.", 0, "adventure")
    img1 = _pil_fallback(_SEED, "Panel two — at night.", 3, "mystery")
    assert img0 != img1, "Different panels should produce different images"


def test_pil_fallback_empty_seed_returns_placeholder():
    from models.panel_image_gen import _pil_fallback

    result_b64 = _pil_fallback("", "some scene", 0, "adventure")
    assert _is_valid_jpeg(result_b64), "Empty seed should return a valid placeholder JPEG"


# ---------------------------------------------------------------------------
# PanelImageGenModel.predict — PIL backend (no API keys needed)
# ---------------------------------------------------------------------------


@pytest.fixture()
def pil_model():
    os.environ["PANEL_IMG_GEN_BACKEND"] = "pil"
    from models.panel_image_gen import PanelImageGenModel

    model = PanelImageGenModel()
    model.load_context(None)
    yield model
    del os.environ["PANEL_IMG_GEN_BACKEND"]


def test_predict_dataframe_input(pil_model):
    df = pd.DataFrame([{
        "seed_image_b64": _SEED,
        "narration": "A brave knight enters the forest.",
        "panel_num": 0,
        "style": "adventure",
    }])
    result = pil_model.predict(None, df)
    assert isinstance(result, dict)
    assert "image_b64" in result
    assert _is_valid_jpeg(result["image_b64"])


def test_predict_dict_input(pil_model):
    row = {
        "seed_image_b64": _SEED,
        "narration": "The dragon breathes fire.",
        "panel_num": 1,
        "style": "fantasy",
    }
    result = pil_model.predict(None, row)
    assert isinstance(result, dict)
    assert "image_b64" in result
    assert _is_valid_jpeg(result["image_b64"])


def test_predict_missing_seed_returns_placeholder(pil_model):
    df = pd.DataFrame([{
        "seed_image_b64": "",
        "narration": "A mystery unfolds.",
        "panel_num": 2,
        "style": "mystery",
    }])
    result = pil_model.predict(None, df)
    assert "image_b64" in result
    assert _is_valid_jpeg(result["image_b64"])


def test_predict_different_panels_differ(pil_model):
    def _run(panel_num: int, narration: str) -> str:
        return pil_model.predict(None, pd.DataFrame([{
            "seed_image_b64": _SEED,
            "narration": narration,
            "panel_num": panel_num,
            "style": "adventure",
        }]))["image_b64"]

    img0 = _run(0, "The journey begins at dawn.")
    img3 = _run(3, "The heroes celebrate their victory at night.")
    assert img0 != img3


# ---------------------------------------------------------------------------
# Backend env-var selection — non-PIL backends fall back to PIL on failure
# ---------------------------------------------------------------------------


def test_stability_backend_falls_back_to_pil_on_error(monkeypatch):
    """stability backend raises when no API key → falls back to PIL without crashing."""
    monkeypatch.setenv("PANEL_IMG_GEN_BACKEND", "stability")
    monkeypatch.delenv("STABILITY_API_KEY", raising=False)

    from models.panel_image_gen import PanelImageGenModel

    model = PanelImageGenModel()
    model.load_context(None)

    result = model.predict(None, pd.DataFrame([{
        "seed_image_b64": _SEED,
        "narration": "A sunny day.",
        "panel_num": 0,
        "style": "adventure",
    }]))
    assert "image_b64" in result
    assert _is_valid_jpeg(result["image_b64"])


def test_hf_api_backend_falls_back_to_pil_on_error(monkeypatch):
    """hf_api backend raises when no token → falls back to PIL without crashing."""
    monkeypatch.setenv("PANEL_IMG_GEN_BACKEND", "hf_api")
    monkeypatch.delenv("HF_API_TOKEN", raising=False)

    from models.panel_image_gen import PanelImageGenModel

    model = PanelImageGenModel()
    model.load_context(None)

    result = model.predict(None, pd.DataFrame([{
        "seed_image_b64": _SEED,
        "narration": "Stars in the sky.",
        "panel_num": 0,
        "style": "space",
    }]))
    assert "image_b64" in result
    assert _is_valid_jpeg(result["image_b64"])


# ---------------------------------------------------------------------------
# LangGraph node integration
# ---------------------------------------------------------------------------


def test_generate_panel_images_node_pil_fallback():
    """generate_panel_images node produces valid panel images via PIL fallback."""
    from agent.nodes import generate_panel_images

    state = {
        "job_id": "test-img-gen-1",
        "image_bytes": _SEED,
        "child_name": "Lily",
        "age_group": "7-9",
        "style_pref": "fantasy",
        "rough_narrative": "",
        "caption": "a colourful drawing",
        "style_examples": [],
        "panels": [
            {"panel": 1, "narration": "A wizard appears.", "dialogue": "Hello!"},
            {"panel": 2, "narration": "The dragon arrives.", "dialogue": None},
        ],
        "safety_verdict": None,
        "safety_failure_reason": None,
        "retry_count": 0,
        "final_comic": None,
        "error": None,
    }

    result = generate_panel_images(state)

    assert len(result["panels"]) == 2
    for panel in result["panels"]:
        assert "image_bytes_b64" in panel
        assert _is_valid_jpeg(panel["image_bytes_b64"])
