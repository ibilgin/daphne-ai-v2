"""
Child Safety Gate — Sketch to Story platform, Phase 5.

Runs Detoxify multilingual on all narration and dialogue text for every panel.
This is the authoritative safety implementation; the LangGraph check_safety node
delegates to this class.

Thresholds (CLAUDE.md critical constraints):
  toxicity        > 0.1  → FAIL
  identity_attack > 0.05 → FAIL

Privacy rule: never log the raw text that triggered the check — log panel index
and score only.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from pydantic import BaseModel

if TYPE_CHECKING:
    from app.schemas import PanelSchema

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Thresholds
# ---------------------------------------------------------------------------
_TOXICITY_THRESHOLD: float = 0.1
_IDENTITY_ATTACK_THRESHOLD: float = 0.05

# ---------------------------------------------------------------------------
# Result schema
# ---------------------------------------------------------------------------


class SafetyResult(BaseModel):
    """Structured result returned by SafetyGate.check_story()."""

    verdict: str  # "PASS" or "FAIL"
    scores: dict[str, float]  # panel_id (str index) → worst score for that panel
    reason: str | None = None


# ---------------------------------------------------------------------------
# Singleton Detoxify model
# ---------------------------------------------------------------------------
_detoxify_model = None


def _get_model():
    """Load Detoxify multilingual once and cache as a module-level singleton."""
    global _detoxify_model
    if _detoxify_model is None:
        try:
            from detoxify import Detoxify

            _detoxify_model = Detoxify("multilingual")
            logger.info("SafetyGate: Detoxify multilingual model loaded")
        except Exception as exc:  # noqa: BLE001
            logger.error("SafetyGate: failed to load Detoxify model — %s", exc)
            raise
    return _detoxify_model


# ---------------------------------------------------------------------------
# SafetyGate
# ---------------------------------------------------------------------------


class SafetyGate:
    """
    Runs Detoxify multilingual over all panels in a story.

    Usage::

        gate = SafetyGate()
        result = gate.check_story(panels)
        if result.verdict == "FAIL":
            ...
    """

    def check_story(self, panels: list) -> SafetyResult:
        """
        Score every panel's narration and dialogue text.

        Parameters
        ----------
        panels:
            List of PanelSchema instances (or dicts with ``narration`` /
            ``dialogue`` keys — both forms are accepted).

        Returns
        -------
        SafetyResult with verdict "PASS" or "FAIL", per-panel worst scores,
        and an optional failure reason (no raw text included).
        """
        if not panels:
            logger.warning("SafetyGate.check_story: empty panels list — returning FAIL")
            return SafetyResult(
                verdict="FAIL",
                scores={},
                reason="No panels provided.",
            )

        # Build per-panel text blobs.  Accept both PanelSchema and plain dicts.
        panel_texts: list[str] = []
        for panel in panels:
            if hasattr(panel, "narration"):
                narration = panel.narration or ""
                dialogue = panel.dialogue or ""
            else:
                narration = panel.get("narration") or ""
                dialogue = panel.get("dialogue") or ""
            combined = f"{narration} {dialogue}".strip()
            panel_texts.append(combined if combined else " ")  # never empty string

        try:
            model = _get_model()
            raw_scores = model.predict(panel_texts)
        except Exception as exc:  # noqa: BLE001
            logger.error("SafetyGate: Detoxify prediction failed — %s", exc)
            # Fail-safe: if the model cannot run, default to FAIL
            return SafetyResult(
                verdict="FAIL",
                scores={},
                reason=f"Safety model error: {exc}",
            )

        failures: list[str] = []
        worst_scores: dict[str, float] = {}

        for i in range(len(panel_texts)):
            toxicity = float(raw_scores["toxicity"][i])
            identity_attack = float(raw_scores["identity_attack"][i])
            worst = max(toxicity, identity_attack)
            panel_key = str(i)
            worst_scores[panel_key] = worst

            # Log panel index and score only — never raw text (child privacy).
            logger.debug(
                "SafetyGate: panel=%s toxicity=%.4f identity_attack=%.4f",
                panel_key,
                toxicity,
                identity_attack,
            )

            if toxicity > _TOXICITY_THRESHOLD:
                failures.append(
                    f"panel={panel_key} toxicity={toxicity:.4f} "
                    f"(threshold={_TOXICITY_THRESHOLD})"
                )
            if identity_attack > _IDENTITY_ATTACK_THRESHOLD:
                failures.append(
                    f"panel={panel_key} identity_attack={identity_attack:.4f} "
                    f"(threshold={_IDENTITY_ATTACK_THRESHOLD})"
                )

        if failures:
            reason = "; ".join(failures)
            logger.warning("SafetyGate: FAIL — %s", reason)
            return SafetyResult(verdict="FAIL", scores=worst_scores, reason=reason)

        logger.info("SafetyGate: PASS — %d panels checked", len(panel_texts))
        return SafetyResult(verdict="PASS", scores=worst_scores, reason=None)
