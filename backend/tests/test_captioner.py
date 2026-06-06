"""
Captioner test suite.

Uses 10 fixture images from tests/fixtures/ (padded with generated grey PNGs
if fewer real fixtures exist).

Assertions per image:
  - caption is a str
  - caption word count: 5–50 words
  - caption does not contain blocked words
  - inference returns in < 5 seconds
"""

from __future__ import annotations

import base64
import io
import time
from pathlib import Path

import pandas as pd
import pytest
from PIL import Image

# Blocked words — must not appear in any generated caption
BLOCKED_WORDS = {
    "violent",
    "blood",
    "weapon",
    "gun",
    "knife",
    "nude",
    "naked",
    "sexual",
    "adult",
    "gore",
}

FIXTURES_DIR = Path(__file__).parents[2] / "tests" / "fixtures"
INFERENCE_TIMEOUT_S = 5.0
FIXTURE_COUNT = 10


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _grey_png_b64(idx: int) -> str:
    """Generate a small grey PNG and return its base64 representation."""
    img = Image.new("RGB", (64, 64), color=(200 - idx * 5, 200, 200))
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return base64.b64encode(buf.getvalue()).decode()


def _load_fixtures(count: int = 10) -> list[str]:
    """Load up to `count` base64-encoded fixture images; pad with generated PNGs."""
    images: list[str] = []
    if FIXTURES_DIR.exists():
        image_files = sorted(
            p
            for p in FIXTURES_DIR.iterdir()
            if p.suffix.lower() in {".png", ".jpg", ".jpeg"}
        )
        for p in image_files[:count]:
            with open(p, "rb") as f:
                images.append(base64.b64encode(f.read()).decode())

    while len(images) < count:
        images.append(_grey_png_b64(len(images)))

    return images


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def captioner_model():
    """Load the CaptionerModel once for the entire module."""
    import sys

    sys.path.insert(0, str(Path(__file__).parents[1]))
    from models.captioner import CaptionerModel

    model = CaptionerModel()

    class _FakeContext:
        artifacts = {}

    model.load_context(_FakeContext())
    return model


@pytest.fixture(scope="module")
def fixture_images() -> list[str]:
    return _load_fixtures(FIXTURE_COUNT)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("image_idx", range(FIXTURE_COUNT))
def test_caption_is_string(captioner_model, fixture_images, image_idx):
    img_b64 = fixture_images[image_idx]
    row = pd.DataFrame([{"image_bytes": img_b64}])
    result = captioner_model.predict(None, row)
    assert isinstance(result["caption"], str), "caption must be a str"


@pytest.mark.parametrize("image_idx", range(FIXTURE_COUNT))
def test_caption_word_count(captioner_model, fixture_images, image_idx):
    img_b64 = fixture_images[image_idx]
    row = pd.DataFrame([{"image_bytes": img_b64}])
    result = captioner_model.predict(None, row)
    words = result["caption"].split()
    assert 5 <= len(words) <= 50, (
        f"Caption word count {len(words)} is outside [5, 50]: {result['caption']!r}"
    )


@pytest.mark.parametrize("image_idx", range(FIXTURE_COUNT))
def test_caption_no_blocked_words(captioner_model, fixture_images, image_idx):
    img_b64 = fixture_images[image_idx]
    row = pd.DataFrame([{"image_bytes": img_b64}])
    result = captioner_model.predict(None, row)
    caption_lower = result["caption"].lower()
    found = [w for w in BLOCKED_WORDS if w in caption_lower]
    assert not found, f"Caption contains blocked words {found}: {result['caption']!r}"


@pytest.mark.parametrize("image_idx", range(FIXTURE_COUNT))
def test_caption_latency(captioner_model, fixture_images, image_idx):
    img_b64 = fixture_images[image_idx]
    row = pd.DataFrame([{"image_bytes": img_b64}])
    t0 = time.perf_counter()
    captioner_model.predict(None, row)
    elapsed = time.perf_counter() - t0
    assert elapsed < INFERENCE_TIMEOUT_S, (
        f"Inference took {elapsed:.2f}s, expected < {INFERENCE_TIMEOUT_S}s"
    )


@pytest.mark.parametrize("image_idx", range(FIXTURE_COUNT))
def test_latency_ms_field(captioner_model, fixture_images, image_idx):
    img_b64 = fixture_images[image_idx]
    row = pd.DataFrame([{"image_bytes": img_b64}])
    result = captioner_model.predict(None, row)
    assert "latency_ms" in result, "Result must include 'latency_ms'"
    assert isinstance(result["latency_ms"], float), "latency_ms must be a float"
    assert result["latency_ms"] >= 0, "latency_ms must be non-negative"
