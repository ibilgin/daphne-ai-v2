"""
Panel image generator — derives each panel illustration from the seed drawing.

Takes the child's original uploaded image and applies per-panel artistic
transforms so each frame feels like the same drawing reimagined at that
story moment:

  1. Pencil-sketch effect   — colour-dodge blend makes it look hand-drawn
  2. Mood colour tint       — narrative keywords choose a warm/cool palette
  3. Progressive zoom       — each panel zooms in slightly for a "closer look"
  4. Bold panel border

The seed image (original drawing) is always the artistic base, so the
child's characters and shapes carry through every panel.

In a production upgrade, swap this module for an img2img diffusion model
(e.g. Stable Diffusion XL img2img or ControlNet-Scribble) registered in
MLflow under "panel_image_gen@Production".  The node signature stays the
same; only this file changes.

Public API
----------
    from agent.panel_artist import draw_panel_image

    b64_jpeg = draw_panel_image(
        seed_image_b64="...",          # original drawing, base64 JPEG/PNG
        narration="Emma flew above the clouds on a silver dragon.",
        panel_num=2,
        style="fantasy",
    )
"""

from __future__ import annotations

import base64
import io
import re
from typing import Any

# ---------------------------------------------------------------------------
# Mood colour palette — (R, G, B) tint applied as a light overlay
# Tint alpha is low (0.18) so the sketch stays dominant.
# ---------------------------------------------------------------------------
_MOOD_TINTS: list[tuple[list[str], tuple[int, int, int]]] = [
    # warm / adventure
    (["adventure", "quest", "hero", "brave", "fight", "run", "fast",
      "race", "found", "discover", "treasure", "won"], (255, 160, 60)),
    # magical / fantasy
    (["magic", "wizard", "dragon", "castle", "fairy", "spell",
      "enchant", "glow", "shimmer", "mystical"], (180, 100, 240)),
    # nature / calm
    (["forest", "tree", "meadow", "garden", "flower", "river",
      "nature", "leaf", "breeze", "peaceful", "quiet"], (80, 190, 100)),
    # ocean / water
    (["ocean", "sea", "wave", "sail", "boat", "fish",
      "swim", "water", "river", "rain", "splash"], (60, 150, 230)),
    # night / mystery
    (["night", "dark", "mystery", "shadow", "secret", "dream",
      "moon", "star", "whisper", "hidden"], (80, 70, 160)),
    # celebration / joy
    (["celebrate", "party", "birthday", "happy", "joy", "laugh",
      "dance", "sing", "together", "friend", "hooray"], (255, 220, 50)),
    # space
    (["space", "rocket", "planet", "galaxy", "asteroid",
      "orbit", "cosmos", "alien", "launch"], (40, 80, 200)),
    # sad / emotional
    (["sad", "cry", "miss", "lonely", "lost", "afraid",
      "worried", "tear", "scared"], (120, 150, 200)),
]

def _pick_tint(narration: str, style: str, panel_num: int) -> tuple[int, int, int]:
    """
    Return a mood colour tint for the panel.

    Narration takes priority over style.  Word-boundary matching prevents
    substrings like 'fast' matching inside 'past'.
    """
    def _any_word(words: list[str], text: str) -> bool:
        return any(re.search(r"\b" + re.escape(w) + r"\b", text) for w in words)

    # 1. Narration keywords
    narr = narration.lower()
    for keywords, tint in _MOOD_TINTS:
        if _any_word(keywords, narr):
            return tint

    # 2. Style name as secondary signal (e.g. style="fantasy" → purple tint)
    sty = style.lower()
    for keywords, tint in _MOOD_TINTS:
        if _any_word(keywords, sty):
            return tint

    # 3. Fallback: rotate neutrals by panel_num so sequential panels differ
    fallbacks = [
        (200, 180, 140),   # sepia
        (140, 200, 180),   # mint
        (200, 140, 160),   # rose
        (160, 160, 200),   # lavender
    ]
    return fallbacks[panel_num % len(fallbacks)]


# ---------------------------------------------------------------------------
# Pencil-sketch effect
#
# Algorithm: colour-dodge blend of the greyscale image with a heavily
# blurred version of its inverse — the classic "pencil sketch" technique.
#
# We avoid heavy dependencies: numpy is already in requirements.txt.
# ---------------------------------------------------------------------------

def _pencil_sketch(img: Any) -> Any:
    """Return a pencil-sketch version of a PIL RGB image."""
    import numpy as np
    from PIL import Image, ImageFilter, ImageOps

    gray = img.convert("L")
    inv  = ImageOps.invert(gray)
    blur = inv.filter(ImageFilter.GaussianBlur(radius=18))

    # Colour-dodge: result = gray / (1 - blur/255)  clipped to [0,255]
    gray_arr = np.array(gray, dtype=np.float32)
    blur_arr = np.array(blur, dtype=np.float32) / 255.0
    denom    = np.clip(1.0 - blur_arr, 1e-6, 1.0)
    sketch   = np.clip(gray_arr / denom, 0, 255).astype(np.uint8)

    return Image.fromarray(sketch).convert("RGB")


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def draw_panel_image(
    seed_image_b64: str,
    narration: str,
    panel_num: int,
    style: str = "adventure",
) -> str:
    """
    Generate a panel illustration derived from the seed drawing.

    Parameters
    ----------
    seed_image_b64 : str
        Base64-encoded original drawing (JPEG or PNG, no data-URI prefix).
    narration : str
        Panel narration text — used to choose the mood colour tint.
    panel_num : int
        Zero-based panel index — drives the progressive zoom.
    style : str
        User-selected comic style — used as a secondary mood signal.

    Returns
    -------
    str
        Base64-encoded JPEG (no data-URI prefix).
    """
    from PIL import Image, ImageDraw

    # --- decode seed image ---------------------------------------------------
    raw = base64.b64decode(seed_image_b64)
    img = Image.open(io.BytesIO(raw)).convert("RGB")

    # Normalise canvas to 400 × 300
    W, H = 400, 300
    img = img.resize((W, H), Image.LANCZOS)

    # --- pencil-sketch effect -------------------------------------------------
    sketch = _pencil_sketch(img)

    # --- mood colour tint -----------------------------------------------------
    tint_rgb = _pick_tint(narration, style, panel_num)
    tint_layer = Image.new("RGB", (W, H), tint_rgb)
    # Blend: 18 % tint so the child's drawing stays dominant
    tinted = Image.blend(sketch, tint_layer, alpha=0.18)

    # --- progressive zoom (0 % → panel_num × 6 %) ----------------------------
    # Panel 0 = full frame; each subsequent panel zooms in slightly so
    # the sequence feels like the story is "moving closer".
    zoom_pct = panel_num * 0.06
    if zoom_pct > 0:
        crop_w = int(W * (1 - zoom_pct))
        crop_h = int(H * (1 - zoom_pct))
        left   = (W - crop_w) // 2
        top    = (H - crop_h) // 2
        tinted = tinted.crop((left, top, left + crop_w, top + crop_h))
        tinted = tinted.resize((W, H), Image.LANCZOS)

    # --- bold comic border ----------------------------------------------------
    draw = ImageDraw.Draw(tinted)
    draw.rectangle([0, 0, W - 1, H - 1], outline=(20, 20, 20), width=4)

    # --- encode ---------------------------------------------------------------
    buf = io.BytesIO()
    tinted.save(buf, format="JPEG", quality=88)
    return base64.b64encode(buf.getvalue()).decode()
