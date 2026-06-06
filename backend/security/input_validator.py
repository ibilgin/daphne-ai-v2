"""
Input Validator — Sketch to Story platform, Phase 5.

validate_image() is called at the very start of POST /api/generate-comic,
before any model invocation.

Checks (in order):
  1. File size < 5 MB
  2. Valid image magic bytes: JPEG (FF D8 FF) or PNG (89 50 4E 47)
  3. Pixel standard deviation > 10 — rejects blank/solid-colour images
  4. Aspect ratio between 0.3 and 3.0

Returns ValidationResult{valid: bool, reason: str | None}.
"""

from __future__ import annotations

import io
import logging

import numpy as np
from PIL import Image
from pydantic import BaseModel

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
_MAX_BYTES: int = 5 * 1024 * 1024  # 5 MB
_MIN_STD: float = 10.0
_MIN_ASPECT: float = 0.3
_MAX_ASPECT: float = 3.0

_JPEG_MAGIC = bytes([0xFF, 0xD8, 0xFF])
_PNG_MAGIC = bytes([0x89, 0x50, 0x4E, 0x47])

# ---------------------------------------------------------------------------
# Result schema
# ---------------------------------------------------------------------------


class ValidationResult(BaseModel):
    """Structured result returned by validate_image()."""

    valid: bool
    reason: str | None = None


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def validate_image(image_bytes: bytes) -> ValidationResult:
    """
    Validate raw image bytes before any model invocation.

    Parameters
    ----------
    image_bytes:
        Raw bytes from the uploaded file (not base64-encoded).

    Returns
    -------
    ValidationResult with ``valid=True`` or ``valid=False`` plus a human-readable
    ``reason`` for failures.
    """
    # 1. Size check
    size = len(image_bytes)
    if size > _MAX_BYTES:
        mb = size / (1024 * 1024)
        reason = f"Image size {mb:.2f} MB exceeds maximum of 5 MB."
        logger.info("validate_image: FAIL size — %s", reason)
        return ValidationResult(valid=False, reason=reason)

    # 2. Magic bytes check
    if not (image_bytes[:3] == _JPEG_MAGIC or image_bytes[:4] == _PNG_MAGIC):
        reason = (
            "Image does not have valid JPEG (FF D8 FF) or PNG (89 50 4E 47) magic bytes."
        )
        logger.info("validate_image: FAIL magic bytes")
        return ValidationResult(valid=False, reason=reason)

    # 3. Decode image for pixel checks
    try:
        img = Image.open(io.BytesIO(image_bytes)).convert("L")  # greyscale
    except Exception as exc:  # noqa: BLE001
        reason = f"Could not decode image: {exc}"
        logger.info("validate_image: FAIL decode — %s", exc)
        return ValidationResult(valid=False, reason=reason)

    # 4. Blank image check (std dev of pixel values)
    std = float(np.array(img).std())
    if std <= _MIN_STD:
        reason = (
            f"Image appears blank or nearly uniform (pixel std={std:.2f}, "
            f"minimum required={_MIN_STD})."
        )
        logger.info("validate_image: FAIL blank std=%.2f", std)
        return ValidationResult(valid=False, reason=reason)

    # 5. Aspect ratio check (use original size, not greyscale — same dimensions)
    try:
        orig = Image.open(io.BytesIO(image_bytes))
        width, height = orig.size
    except Exception:  # noqa: BLE001
        # img was already opened; fall back to greyscale dimensions
        width, height = img.size

    if height == 0:
        reason = "Image has zero height."
        return ValidationResult(valid=False, reason=reason)

    aspect = width / height
    if not (_MIN_ASPECT <= aspect <= _MAX_ASPECT):
        reason = (
            f"Aspect ratio {aspect:.2f} is outside the allowed range "
            f"[{_MIN_ASPECT}, {_MAX_ASPECT}]."
        )
        logger.info("validate_image: FAIL aspect_ratio=%.2f", aspect)
        return ValidationResult(valid=False, reason=reason)

    logger.debug(
        "validate_image: PASS size=%d std=%.2f aspect=%.2f", size, std, aspect
    )
    return ValidationResult(valid=True, reason=None)
