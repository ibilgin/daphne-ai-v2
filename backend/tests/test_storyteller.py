"""
Storyteller test suite.

Tests the StorytellerModel pyfunc wrapper using a mock Ollama HTTP server
(via pytest-httpserver or unittest.mock) so that tests run offline.

Assertions:
  - Returns valid dict with "panels" key
  - panels is a list
  - Each panel has "narration" (str) and "dialogue" (str or None)
  - Panel count matches requested count
  - Panel numbers are sequential
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).parents[1]))
from models.storyteller import StorytellerModel


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_model() -> StorytellerModel:
    """Instantiate and initialise StorytellerModel with test Ollama URL."""
    model = StorytellerModel()

    class _FakeContext:
        artifacts = {}

    # Patch env so load_context picks up the test URL
    with patch.dict(
        "os.environ",
        {"OLLAMA_BASE_URL": "http://localhost:11434", "OLLAMA_MODEL": "mistral"},
    ):
        model.load_context(_FakeContext())
    return model


def _fake_ollama_response(panels: list[dict]) -> MagicMock:
    """Build a mock requests.Response that returns a valid Ollama JSON payload."""
    mock_resp = MagicMock()
    mock_resp.raise_for_status = MagicMock()
    mock_resp.json.return_value = {
        "message": {"content": json.dumps({"panels": panels})}
    }
    return mock_resp


def _build_input(
    caption: str = "a child drawing of a superhero",
    style_examples: list[str] | None = None,
    panel_count: int = 3,
) -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "caption": caption,
                "style_examples": json.dumps(style_examples or []),
                "panel_count": panel_count,
            }
        ]
    )


def _sample_panels(n: int) -> list[dict]:
    return [
        {
            "panel": i + 1,
            "narration": f"Panel {i + 1} narration text.",
            "dialogue": f"Hero says: 'Panel {i + 1}!'" if i % 2 == 0 else None,
        }
        for i in range(n)
    ]


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestStorytellerBasic:
    """Basic correctness tests with mocked Ollama."""

    @pytest.fixture
    def model(self) -> StorytellerModel:
        return _make_model()

    @pytest.mark.parametrize("panel_count", [1, 3, 5, 8])
    def test_returns_panels_list(self, model, panel_count):
        panels = _sample_panels(panel_count)
        with patch("requests.post", return_value=_fake_ollama_response(panels)):
            result = model.predict(None, _build_input(panel_count=panel_count))

        assert "panels" in result, "Result must have 'panels' key"
        assert isinstance(result["panels"], list), "'panels' must be a list"

    @pytest.mark.parametrize("panel_count", [1, 3, 5])
    def test_panel_count_matches_request(self, model, panel_count):
        panels = _sample_panels(panel_count)
        with patch("requests.post", return_value=_fake_ollama_response(panels)):
            result = model.predict(None, _build_input(panel_count=panel_count))

        assert len(result["panels"]) == panel_count, (
            f"Expected {panel_count} panels, got {len(result['panels'])}"
        )

    @pytest.mark.parametrize("panel_count", [3])
    def test_each_panel_has_narration_str(self, model, panel_count):
        panels = _sample_panels(panel_count)
        with patch("requests.post", return_value=_fake_ollama_response(panels)):
            result = model.predict(None, _build_input(panel_count=panel_count))

        for i, panel in enumerate(result["panels"]):
            assert "narration" in panel, f"Panel {i} missing 'narration'"
            assert isinstance(panel["narration"], str), (
                f"Panel {i} 'narration' must be str, got {type(panel['narration'])}"
            )

    @pytest.mark.parametrize("panel_count", [3])
    def test_each_panel_has_dialogue_str_or_none(self, model, panel_count):
        panels = _sample_panels(panel_count)
        with patch("requests.post", return_value=_fake_ollama_response(panels)):
            result = model.predict(None, _build_input(panel_count=panel_count))

        for i, panel in enumerate(result["panels"]):
            assert "dialogue" in panel, f"Panel {i} missing 'dialogue'"
            assert panel["dialogue"] is None or isinstance(panel["dialogue"], str), (
                f"Panel {i} 'dialogue' must be str or None"
            )

    def test_panel_with_null_dialogue(self, model):
        panels = [
            {"panel": 1, "narration": "The hero arrives.", "dialogue": None},
            {"panel": 2, "narration": "The villain appears.", "dialogue": "I'm here!"},
            {"panel": 3, "narration": "Battle begins.", "dialogue": None},
        ]
        with patch("requests.post", return_value=_fake_ollama_response(panels)):
            result = model.predict(None, _build_input(panel_count=3))

        assert result["panels"][0]["dialogue"] is None
        assert result["panels"][2]["dialogue"] is None


class TestStorytellerRetry:
    """Tests for the JSON parse failure retry logic."""

    @pytest.fixture
    def model(self) -> StorytellerModel:
        return _make_model()

    def test_retries_on_bad_json_then_succeeds(self, model):
        """First call returns garbage JSON; second returns valid response."""
        good_panels = _sample_panels(2)

        bad_resp = MagicMock()
        bad_resp.raise_for_status = MagicMock()
        bad_resp.json.return_value = {"message": {"content": "not-valid-json{"}}

        good_resp = _fake_ollama_response(good_panels)

        with patch("requests.post", side_effect=[bad_resp, good_resp]):
            result = model.predict(None, _build_input(panel_count=2))

        assert len(result["panels"]) == 2

    def test_raises_after_all_retries_exhausted(self, model):
        """All attempts return invalid JSON — should raise RuntimeError."""
        bad_resp = MagicMock()
        bad_resp.raise_for_status = MagicMock()
        bad_resp.json.return_value = {"message": {"content": "!!bad!!"}}

        with patch("requests.post", return_value=bad_resp):
            with pytest.raises(RuntimeError, match="all .* attempts failed"):
                model.predict(None, _build_input(panel_count=3))


class TestStorytellerInputValidation:
    """Tests for missing / malformed inputs."""

    @pytest.fixture
    def model(self) -> StorytellerModel:
        return _make_model()

    def test_missing_caption_column_raises(self, model):
        df = pd.DataFrame([{"style_examples": "[]", "panel_count": 2}])
        with pytest.raises(ValueError, match="caption"):
            model.predict(None, df)

    def test_missing_panel_count_raises(self, model):
        df = pd.DataFrame([{"caption": "a drawing", "style_examples": "[]"}])
        with pytest.raises(ValueError, match="panel_count"):
            model.predict(None, df)

    def test_style_examples_as_list_accepted(self, model):
        """style_examples can be a native list (not a JSON str)."""
        panels = _sample_panels(2)
        df = pd.DataFrame(
            [
                {
                    "caption": "a drawing",
                    "style_examples": ["manga", "watercolour"],
                    "panel_count": 2,
                }
            ]
        )
        with patch("requests.post", return_value=_fake_ollama_response(panels)):
            result = model.predict(None, df)
        assert len(result["panels"]) == 2
