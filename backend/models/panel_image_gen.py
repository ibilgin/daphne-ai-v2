"""
Panel Image Generation model — MLflow pyfunc wrapper.

Takes the child's seed drawing (base64) + panel narration and returns a new
JPEG image that is visually consistent with the seed while illustrating the
panel's narrative moment.

Backend selection via PANEL_IMG_GEN_BACKEND env var
----------------------------------------------------
"stability"       Stability AI Control/Sketch API (POST /v2beta/stable-image/control/sketch).
                  Requires: STABILITY_API_KEY env var (sourced from Vault in production).
                  The child's drawing acts as the sketch guide; the narration is the prompt.
                  control_strength=0.7 keeps the original shapes while adding illustration
                  detail.  style_preset="comic-book" gives a storybook aesthetic.

"hf_api"          HuggingFace Inference API img2img
                  (stabilityai/stable-diffusion-xl-refiner-1.0 or similar).
                  Requires: HF_API_TOKEN env var (sourced from Vault in production).

"local_diffusers" FLUX.1 img2img via mflux (Apple MLX). Apple Silicon only.
                  No API key needed. First run downloads ~8GB model from HuggingFace.
                  Subsequent runs load from ~/.cache/mflux.
                  Install: pip install mflux  (not included in Docker image).
                  Tune with: MFLUX_MODEL, MFLUX_QUANTIZE, MFLUX_STEPS,
                             MFLUX_INIT_IMAGE_STRENGTH.

"pil"             PIL pencil-sketch + mood-tint fallback (no API key needed).
                  Always available.  Used automatically when no API key is configured.

Upgrading to a production backend
----------------------------------
1. Set PANEL_IMG_GEN_BACKEND and the corresponding API key via Vault:
       vault kv put secret/sketch-to-story \
           stability_api_key=<key> \
           panel_img_gen_backend=stability
2. Register a new model version:
       python scripts/register_panel_image_gen.py
3. Run the governance gate — model_card check requires a new card entry.

Public API (pyfunc)
-------------------
Input dict (or single-row DataFrame):
    seed_image_b64  : str   base64 JPEG/PNG of the child's drawing
    narration       : str   panel narration text (used as image prompt)
    panel_num       : int   0-based panel index (drives zoom in PIL fallback)
    style           : str   style preference hint ("adventure", "fantasy", …)

Output dict:
    image_b64       : str   base64 JPEG of the generated panel image
"""

from __future__ import annotations

import base64
import logging
import os
from typing import Any

import mlflow.pyfunc

logger = logging.getLogger(__name__)

# Comic-book style presets for the external API prompts
_STYLE_SUFFIXES = {
    "adventure": "vibrant adventure comic book style, warm colours",
    "fantasy":   "magical fantasy storybook illustration, soft watercolour",
    "friendship": "warm cosy children's book illustration, pastel tones",
    "mystery":   "atmospheric mystery comic, cool muted palette",
    "animals":   "cute animal storybook illustration, playful style",
    "space":     "sci-fi comic book illustration, deep space colours",
}
_DEFAULT_STYLE_SUFFIX = "children's comic book illustration"


def _style_suffix(style: str) -> str:
    return _STYLE_SUFFIXES.get(style.lower(), _DEFAULT_STYLE_SUFFIX)


# ---------------------------------------------------------------------------
# Stability AI backend
# ---------------------------------------------------------------------------

def _stability_img2img(seed_b64: str, narration: str, style: str) -> str:
    """
    Call Stability AI /v2beta/stable-image/control/sketch.

    The child's drawing is used as the sketch control signal (the composition
    and shapes are preserved) while the narration drives the illustration
    details.  Returns base64 JPEG.
    """
    import requests  # noqa: PLC0415

    api_key = os.environ.get("STABILITY_API_KEY", "")
    if not api_key:
        raise RuntimeError("STABILITY_API_KEY not set")

    prompt = f"{narration}. {_style_suffix(style)}, child-friendly, no text"

    response = requests.post(
        "https://api.stability.ai/v2beta/stable-image/control/sketch",
        headers={
            "Authorization": f"Bearer {api_key}",
            "Accept": "image/*",
        },
        files={
            "image": ("seed.jpg", base64.b64decode(seed_b64), "image/jpeg"),
        },
        data={
            "prompt": prompt,
            "control_strength": "0.7",
            "style_preset": "comic-book",
            "output_format": "jpeg",
        },
        timeout=30,
    )

    if response.status_code != 200:
        raise RuntimeError(
            f"Stability AI API error {response.status_code}: {response.text[:200]}"
        )

    raw_bytes = response.content
    return base64.b64encode(raw_bytes).decode()


# ---------------------------------------------------------------------------
# HuggingFace Inference API backend
# ---------------------------------------------------------------------------

def _hf_img2img(seed_b64: str, narration: str, style: str) -> str:
    """
    Call HuggingFace Inference API (image-to-image).

    Uses InferenceClient.image_to_image() which supports any img2img model
    hosted on the HF hub.  Model is selected via HF_IMG2IMG_MODEL env var
    (default: stabilityai/stable-diffusion-xl-refiner-1.0).
    Returns base64 JPEG.
    """
    from PIL import Image  # noqa: PLC0415
    from huggingface_hub import InferenceClient  # noqa: PLC0415
    import io  # noqa: PLC0415

    token = os.environ.get("HF_API_TOKEN", "")
    if not token:
        raise RuntimeError("HF_API_TOKEN not set")

    model = os.environ.get(
        "HF_IMG2IMG_MODEL", "stabilityai/stable-diffusion-xl-refiner-1.0"
    )
    prompt = f"{narration}. {_style_suffix(style)}, child-friendly"

    # Decode seed to PIL
    seed_bytes = base64.b64decode(seed_b64)
    seed_img = Image.open(io.BytesIO(seed_bytes)).convert("RGB")

    client = InferenceClient(token=token)
    result_img = client.image_to_image(
        image=seed_img,
        prompt=prompt,
        model=model,
    )

    buf = io.BytesIO()
    result_img.convert("RGB").save(buf, format="JPEG", quality=88)
    return base64.b64encode(buf.getvalue()).decode()


# ---------------------------------------------------------------------------
# PIL fallback backend
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# Local mflux backend (Apple Silicon only)
# ---------------------------------------------------------------------------

def _mflux_img2img(seed_b64: str, narration: str, panel_num: int, style: str) -> str:
    """
    Run FLUX.1 img2img locally via mflux (Apple MLX).

    Env vars
    --------
    MFLUX_MODEL              flux-schnell | flux-dev  (default: flux-schnell)
    MFLUX_QUANTIZE           4 | 8                    (default: 4)
    MFLUX_STEPS              inference steps          (default: 4 for schnell, 20 for dev)
    MFLUX_INIT_IMAGE_STRENGTH  0.0–1.0, how much the seed guides output
                               lower = more creative, higher = closer to seed
                               (default: 0.35)

    First run downloads the model from HuggingFace (~8GB for schnell Q4).
    Subsequent runs load from the MLX cache (~/.cache/mflux).

    Mac-only: this backend requires Apple Silicon and will not run in Docker.
    """
    import io  # noqa: PLC0415
    import os as _os  # noqa: PLC0415
    import tempfile  # noqa: PLC0415

    from PIL import Image  # noqa: PLC0415

    try:
        from mflux import Config, Flux1  # noqa: PLC0415
    except ImportError as exc:
        raise RuntimeError(
            "mflux not installed. Run: pip install mflux  "
            "(Apple Silicon only — requires macOS with Metal support)"
        ) from exc

    model_alias = os.environ.get("MFLUX_MODEL", "flux-schnell")
    quantize = int(os.environ.get("MFLUX_QUANTIZE", "4"))
    default_steps = "4" if model_alias == "flux-schnell" else "20"
    steps = int(os.environ.get("MFLUX_STEPS", default_steps))
    init_strength = float(os.environ.get("MFLUX_INIT_IMAGE_STRENGTH", "0.35"))

    prompt = (
        f"{narration}. {_style_suffix(style)}, "
        "children's comic book illustration, child-friendly, vibrant colours, no text"
    )

    # Decode seed → resize to 512×512 → write to temp file (mflux needs a path)
    seed_bytes = base64.b64decode(seed_b64)
    seed_img = Image.open(io.BytesIO(seed_bytes)).convert("RGB").resize(
        (512, 512), Image.LANCZOS
    )

    tmp_in = tempfile.NamedTemporaryFile(suffix=".jpg", delete=False)
    try:
        seed_img.save(tmp_in, format="JPEG", quality=90)
        tmp_in.close()

        logger.info(
            "mflux: loading model=%s quantize=%d steps=%d init_strength=%.2f",
            model_alias, quantize, steps, init_strength,
        )

        # Load model (cached after first run)
        flux = Flux1.from_alias(alias=model_alias, quantize=quantize)

        # Vary seed per panel so each panel is unique
        panel_seed = 42 + panel_num * 7

        generated = flux.generate_image(
            seed=panel_seed,
            prompt=prompt,
            config=Config(
                num_inference_steps=steps,
                height=512,
                width=512,
                init_image_path=tmp_in.name,
                init_image_strength=init_strength,
            ),
        )

        # `generated.image` is a PIL Image
        buf = io.BytesIO()
        generated.image.convert("RGB").save(buf, format="JPEG", quality=88)
        return base64.b64encode(buf.getvalue()).decode()

    finally:
        _os.unlink(tmp_in.name)


def _pil_fallback(seed_b64: str, narration: str, panel_num: int, style: str) -> str:
    """PIL pencil-sketch + mood-tint fallback (always available)."""
    import io  # noqa: PLC0415

    from PIL import Image  # noqa: PLC0415

    if not seed_b64.strip():
        placeholder = Image.new("RGB", (400, 300), (220, 220, 220))
        buf = io.BytesIO()
        placeholder.save(buf, format="JPEG", quality=85)
        return base64.b64encode(buf.getvalue()).decode()

    from agent.panel_artist import draw_panel_image  # noqa: PLC0415

    return draw_panel_image(seed_b64, narration, panel_num, style)


# ---------------------------------------------------------------------------
# MLflow pyfunc wrapper
# ---------------------------------------------------------------------------

class PanelImageGenModel(mlflow.pyfunc.PythonModel):
    """
    Pluggable img2img model for comic panel generation.

    Registered in MLflow under model name "panel_image_gen".
    Backend selected at inference time via PANEL_IMG_GEN_BACKEND env var.
    """

    def predict(self, context: Any, model_input: Any, params: Any = None) -> dict:
        import pandas as pd  # noqa: PLC0415

        if isinstance(model_input, pd.DataFrame):
            row = model_input.to_dict(orient="records")[0]
        elif isinstance(model_input, dict):
            row = model_input
        else:
            row = list(model_input)[0]

        seed_b64 = str(row.get("seed_image_b64", ""))
        narration = str(row.get("narration", ""))
        panel_num = int(row.get("panel_num", 0))
        style = str(row.get("style", "adventure"))

        backend = os.environ.get("PANEL_IMG_GEN_BACKEND", "pil").lower()

        logger.info(
            "panel_image_gen.predict: backend=%s panel_num=%d narration=%r",
            backend, panel_num, narration[:60],
        )

        try:
            if backend == "stability":
                image_b64 = _stability_img2img(seed_b64, narration, style)
                logger.info("panel_image_gen: Stability AI img2img OK")
            elif backend == "hf_api":
                image_b64 = _hf_img2img(seed_b64, narration, style)
                logger.info("panel_image_gen: HF API img2img OK")
            elif backend == "local_diffusers":
                image_b64 = _mflux_img2img(seed_b64, narration, panel_num, style)
                logger.info("panel_image_gen: mflux local img2img OK")
            else:
                image_b64 = _pil_fallback(seed_b64, narration, panel_num, style)
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "panel_image_gen: backend=%s failed (%s) — falling back to PIL",
                backend, exc,
            )
            image_b64 = _pil_fallback(seed_b64, narration, panel_num, style)

        return {"image_b64": image_b64}
