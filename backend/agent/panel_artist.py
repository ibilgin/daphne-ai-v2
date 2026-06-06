"""
Panel image generator — creates child-drawing-style illustrations using PIL.

Each panel gets a unique scene derived from:
  - keywords in the panel narration  (selects scene elements)
  - the panel index                  (varies layout/palette)
  - the style preference             (influences colour mood)

The output intentionally looks like a child drew it with thick crayons:
flat colours, simple shapes, bold outlines, no gradients.

In production this module would be swapped for a diffusion model
(e.g. Stable Diffusion XL Turbo) registered in MLflow under
"panel_image_gen@Production". For the study project, PIL is sufficient
and avoids GPU requirements.

Public API
----------
    from agent.panel_artist import draw_panel_image

    b64_jpeg = draw_panel_image(
        narration="Emma flew above the clouds on a silver dragon.",
        panel_num=2,
        style="fantasy",
    )
"""

from __future__ import annotations

import base64
import io
import math
import random
from typing import Any

# ---------------------------------------------------------------------------
# Canvas dimensions
# ---------------------------------------------------------------------------
_W, _H = 400, 300
_GROUND_Y = 210          # y-coordinate where sky meets ground

# ---------------------------------------------------------------------------
# Colour palettes  (sky_top, sky_bottom, ground, accent_a, accent_b)
# ---------------------------------------------------------------------------
_PALETTES: dict[str, dict[str, Any]] = {
    "adventure": {
        "sky":    (135, 200, 235),
        "ground": (80,  155, 60),
        "sun":    (255, 220, 50),
        "accents": [(255, 140, 0), (200, 100, 50), (255, 200, 80)],
    },
    "fantasy": {
        "sky":    (190, 140, 230),
        "ground": (110, 70,  160),
        "sun":    (255, 230, 100),
        "accents": [(255, 100, 180), (100, 200, 255), (255, 215, 0)],
    },
    "friendship": {
        "sky":    (200, 230, 255),
        "ground": (110, 200, 110),
        "sun":    (255, 220, 80),
        "accents": [(255, 180, 200), (255, 220, 120), (150, 220, 255)],
    },
    "mystery": {
        "sky":    (50,  60,  120),
        "ground": (40,  60,  40),
        "sun":    (200, 200, 255),   # moon
        "accents": [(120, 100, 200), (80, 200, 180), (180, 130, 230)],
    },
    "animals": {
        "sky":    (160, 220, 255),
        "ground": (100, 180, 70),
        "sun":    (255, 215, 50),
        "accents": [(200, 140, 70), (255, 190, 100), (80, 180, 80)],
    },
    "space": {
        "sky":    (10,  10,  40),
        "ground": (30,  20,  60),
        "sun":    (255, 255, 200),   # star
        "accents": [(200, 100, 255), (100, 200, 255), (255, 150, 50)],
    },
}

_DEFAULT_PALETTE = _PALETTES["adventure"]

# ---------------------------------------------------------------------------
# Keyword → scene element mapping
# ---------------------------------------------------------------------------
_KEYWORD_SCENES: list[tuple[list[str], str]] = [
    (["dragon", "wizard", "castle", "magic", "spell", "wand", "fairy"],  "fantasy_castle"),
    (["space", "rocket", "planet", "star", "galaxy", "moon", "alien"],    "space"),
    (["ocean", "sea", "wave", "fish", "boat", "ship", "swim", "beach"],   "ocean"),
    (["forest", "tree", "jungle", "wood", "vine", "leaf", "animal"],      "forest"),
    (["mountain", "hill", "climb", "valley", "snow", "peak"],             "mountain"),
    (["house", "home", "door", "village", "family", "kitchen", "room"],   "village"),
    (["cloud", "fly", "bird", "sky", "wind", "air", "wing", "float"],     "sky"),
    (["party", "cake", "birthday", "friend", "celebrate", "happy", "joy"], "party"),
    (["night", "dark", "dream", "sleep", "star", "moon", "twilight"],     "night"),
    (["flower", "garden", "meadow", "spring", "butterfly", "bee"],        "garden"),
]


def _detect_scene(narration: str) -> str:
    text = narration.lower()
    for keywords, scene in _KEYWORD_SCENES:
        if any(kw in text for kw in keywords):
            return scene
    return "meadow"   # default


def _get_palette(style: str) -> dict[str, Any]:
    return _PALETTES.get(style.lower(), _DEFAULT_PALETTE)


# ---------------------------------------------------------------------------
# Drawing primitives  (all coordinates relative to _W × _H canvas)
# ---------------------------------------------------------------------------

def _draw_sun(draw: Any, x: int, y: int, r: int = 32,
              color: tuple = (255, 220, 50)) -> None:
    draw.ellipse([x - r, y - r, x + r, y + r], fill=color, outline=(200, 150, 0), width=3)
    for angle_deg in range(0, 360, 45):
        rad = math.radians(angle_deg)
        x1 = int(x + (r + 6) * math.cos(rad))
        y1 = int(y + (r + 6) * math.sin(rad))
        x2 = int(x + (r + 18) * math.cos(rad))
        y2 = int(y + (r + 18) * math.sin(rad))
        draw.line([x1, y1, x2, y2], fill=(200, 160, 0), width=3)


def _draw_moon(draw: Any, x: int, y: int, r: int = 28,
               color: tuple = (230, 230, 200)) -> None:
    draw.ellipse([x - r, y - r, x + r, y + r], fill=color)
    draw.ellipse([x + r // 3, y - r, x + r + r // 2, y + r], fill=(50, 60, 120))


def _draw_cloud(draw: Any, x: int, y: int,
                color: tuple = (240, 245, 255)) -> None:
    for dx, dy, rx, ry in [(0, 0, 32, 22), (28, -10, 24, 18),
                            (-28, -10, 24, 18), (50, 4, 18, 14), (-50, 4, 18, 14)]:
        draw.ellipse([x + dx - rx, y + dy - ry, x + dx + rx, y + dy + ry], fill=color)


def _draw_star(draw: Any, x: int, y: int, r: int = 10,
               color: tuple = (255, 240, 100)) -> None:
    pts = []
    for i in range(10):
        a = math.radians(i * 36 - 90)
        radius = r if i % 2 == 0 else int(r * 0.4)
        pts.append((x + radius * math.cos(a), y + radius * math.sin(a)))
    draw.polygon(pts, fill=color)


def _draw_tree(draw: Any, x: int, y: int,
               trunk: tuple = (101, 67, 33),
               leaves: tuple = (34, 140, 34)) -> None:
    draw.rectangle([x - 9, y - 45, x + 9, y], fill=trunk, outline=(70, 40, 20), width=2)
    draw.polygon([(x, y - 90), (x - 38, y - 35), (x + 38, y - 35)],
                 fill=leaves, outline=(20, 100, 20), width=2)
    draw.polygon([(x, y - 110), (x - 28, y - 65), (x + 28, y - 65)],
                 fill=leaves, outline=(20, 100, 20), width=2)


def _draw_house(draw: Any, x: int, y: int,
                wall: tuple = (215, 145, 80),
                roof: tuple = (180, 55, 35)) -> None:
    draw.rectangle([x - 42, y - 55, x + 42, y], fill=wall, outline=(100, 70, 30), width=3)
    draw.polygon([(x - 55, y - 55), (x, y - 100), (x + 55, y - 55)],
                 fill=roof, outline=(120, 30, 20), width=3)
    draw.rectangle([x - 13, y - 28, x + 13, y], fill=(120, 75, 35),
                   outline=(80, 50, 20), width=2)
    for wx in (-28, 18):
        draw.rectangle([x + wx, y - 50, x + wx + 20, y - 30],
                       fill=(200, 230, 255), outline=(80, 60, 30), width=2)
        draw.line([x + wx + 10, y - 50, x + wx + 10, y - 30], fill=(140, 170, 200), width=1)
        draw.line([x + wx, y - 40, x + wx + 20, y - 40], fill=(140, 170, 200), width=1)


def _draw_character(draw: Any, x: int, y: int,
                    skin: tuple = (255, 205, 150),
                    shirt: tuple = (100, 150, 255),
                    hair: tuple = (100, 70, 30)) -> None:
    draw.ellipse([x - 16, y - 56, x + 16, y - 26], fill=skin, outline=(100, 80, 60), width=2)
    draw.arc([x - 16, y - 56, x + 16, y - 26], 200, 340, fill=hair, width=5)
    draw.rectangle([x - 14, y - 26, x + 14, y + 18], fill=shirt, outline=(60, 100, 200), width=2)
    draw.line([x, y + 18, x - 18, y + 60], fill=(80, 100, 160), width=5)
    draw.line([x, y + 18, x + 18, y + 60], fill=(80, 100, 160), width=5)
    draw.line([x - 14, y - 18, x - 38, y + 5], fill=shirt, width=5)
    draw.line([x + 14, y - 18, x + 38, y + 5], fill=shirt, width=5)


def _draw_mountain(draw: Any, x: int, y: int, w: int = 130, h: int = 110,
                   color: tuple = (120, 100, 85)) -> None:
    draw.polygon([(x, y - h), (x - w // 2, y), (x + w // 2, y)],
                 fill=color, outline=(80, 65, 55), width=2)
    draw.polygon([(x, y - h), (x - 28, y - h + 38), (x + 28, y - h + 38)],
                 fill=(240, 245, 255))


def _draw_flower(draw: Any, x: int, y: int,
                 petal: tuple = (255, 100, 150)) -> None:
    for a in range(0, 360, 60):
        rad = math.radians(a)
        px, py = int(x + 12 * math.cos(rad)), int(y + 12 * math.sin(rad))
        draw.ellipse([px - 9, py - 9, px + 9, py + 9], fill=petal)
    draw.ellipse([x - 8, y - 8, x + 8, y + 8], fill=(255, 225, 50))
    draw.line([x, y + 8, x, y + 38], fill=(50, 150, 50), width=3)


def _draw_wave(draw: Any, y_base: int,
               color: tuple = (60, 160, 230)) -> None:
    for layer in range(3):
        pts = []
        for x in range(0, _W + 10, 8):
            wy = y_base + layer * 12 + int(9 * math.sin((x + layer * 40) * 0.06))
            pts.append((x, wy))
        draw.line(pts, fill=color, width=4)


def _draw_planet(draw: Any, x: int, y: int, r: int = 30,
                 color: tuple = (180, 100, 220)) -> None:
    draw.ellipse([x - r, y - r, x + r, y + r], fill=color, outline=(120, 60, 180), width=2)
    draw.ellipse([x - r * 2, y - r // 3, x + r * 2, y + r // 3],
                 outline=(220, 160, 255), width=3)


def _draw_rocket(draw: Any, x: int, y: int,
                 body: tuple = (200, 210, 230)) -> None:
    pts = [(x, y - 55), (x - 18, y + 20), (x + 18, y + 20)]
    draw.polygon(pts, fill=body, outline=(100, 110, 130), width=2)
    draw.ellipse([x - 18, y - 60, x + 18, y - 40], fill=(255, 100, 100), outline=(200, 50, 50), width=2)
    draw.ellipse([x - 9, y - 20, x + 9, y - 5], fill=(180, 230, 255))
    draw.polygon([(x - 18, y + 10), (x - 32, y + 28), (x - 8, y + 20)], fill=(255, 140, 0))
    draw.polygon([(x + 18, y + 10), (x + 32, y + 28), (x + 8, y + 20)], fill=(255, 140, 0))
    draw.ellipse([x - 6, y + 18, x + 6, y + 30], fill=(255, 100, 0))


def _draw_dragon(draw: Any, x: int, y: int,
                 color: tuple = (100, 200, 100)) -> None:
    draw.ellipse([x - 35, y - 30, x + 35, y + 30], fill=color, outline=(50, 150, 50), width=3)
    draw.ellipse([x + 20, y - 55, x + 60, y - 20], fill=color, outline=(50, 150, 50), width=2)
    for i, (dx, dy) in enumerate([(-10, -60), (5, -65), (20, -60)]):
        draw.ellipse([x + dx - 6, y + dy - 6, x + dx + 6, y + dy + 6], fill=(255, 60, 60))
    draw.polygon([(x - 35, y - 15), (x - 70, y - 50), (x - 25, y - 10)],
                 fill=(140, 230, 140), outline=(50, 150, 50), width=2)
    draw.polygon([(x - 35, y + 15), (x - 70, y + 50), (x - 25, y + 10)],
                 fill=(140, 230, 140), outline=(50, 150, 50), width=2)
    draw.line([x + 35, y, x + 80, y + 20, x + 90, y + 5], fill=color, width=6)


def _draw_cake(draw: Any, x: int, y: int) -> None:
    draw.rectangle([x - 40, y - 50, x + 40, y], fill=(255, 180, 200), outline=(200, 100, 130), width=2)
    draw.rectangle([x - 50, y - 30, x + 50, y], fill=(255, 220, 240), outline=(200, 100, 130), width=2)
    for i in range(-3, 4):
        cx = x + i * 14
        draw.rectangle([cx - 3, y - 70, cx + 3, y - 50], fill=(255, 200, 50))
        draw.ellipse([cx - 5, y - 76, cx + 5, y - 65], fill=(255, 100, 50))


# ---------------------------------------------------------------------------
# Scene composers — each returns nothing, draws onto `draw` in place
# ---------------------------------------------------------------------------

def _scene_meadow(draw: Any, palette: dict, panel_num: int) -> None:
    _draw_sun(draw, 60, 50, color=palette["sun"])
    _draw_cloud(draw, 200, 55)
    _draw_cloud(draw, 330, 40)
    positions = [(80, _GROUND_Y), (200, _GROUND_Y), (320, _GROUND_Y)]
    for i, (tx, ty) in enumerate(positions[:2 + panel_num % 2]):
        _draw_tree(draw, tx, ty)
    _draw_character(draw, 240 + (panel_num % 3) * 40, _GROUND_Y,
                    shirt=palette["accents"][panel_num % 3])
    for fx in [140, 160, 290, 310]:
        _draw_flower(draw, fx, _GROUND_Y, petal=palette["accents"][panel_num % 3])


def _scene_forest(draw: Any, palette: dict, panel_num: int) -> None:
    _draw_sun(draw, 340, 45, r=25, color=palette["sun"])
    for tx in [40, 100, 160, 260, 330, 380]:
        _draw_tree(draw, tx, _GROUND_Y,
                   leaves=(30 + (tx % 4) * 15, 120 + (tx % 3) * 20, 30))
    _draw_character(draw, 200 + panel_num * 10, _GROUND_Y,
                    shirt=palette["accents"][0])


def _scene_ocean(draw: Any, palette: dict, panel_num: int) -> None:
    _draw_sun(draw, 340, 50, color=palette["sun"])
    _draw_cloud(draw, 120, 55)
    _draw_cloud(draw, 280, 40)
    _draw_wave(draw, _GROUND_Y - 20, color=(60, 140, 220))
    _draw_wave(draw, _GROUND_Y + 10, color=(40, 120, 200))
    _draw_wave(draw, _GROUND_Y + 30, color=(30, 100, 180))
    boat_x = 150 + panel_num * 30
    draw.polygon([(boat_x - 45, _GROUND_Y - 20), (boat_x + 45, _GROUND_Y - 20),
                  (boat_x + 35, _GROUND_Y + 5), (boat_x - 35, _GROUND_Y + 5)],
                 fill=(220, 170, 100), outline=(150, 100, 50), width=3)
    draw.polygon([(boat_x, _GROUND_Y - 20), (boat_x, _GROUND_Y - 75),
                  (boat_x + 35, _GROUND_Y - 40)], fill=(240, 50, 50))


def _scene_mountain(draw: Any, palette: dict, panel_num: int) -> None:
    _draw_sun(draw, 340, 55, color=palette["sun"])
    _draw_mountain(draw, 120, _GROUND_Y, w=160, h=130)
    _draw_mountain(draw, 280, _GROUND_Y, w=120, h=100,
                   color=(140, 120, 100))
    _draw_cloud(draw, 200, 60)
    _draw_character(draw, 200, _GROUND_Y, shirt=palette["accents"][1])


def _scene_village(draw: Any, palette: dict, panel_num: int) -> None:
    _draw_sun(draw, 340, 50, color=palette["sun"])
    _draw_cloud(draw, 150, 55)
    _draw_house(draw, 130, _GROUND_Y, wall=palette["accents"][0],
                roof=palette["accents"][2])
    _draw_house(draw, 300, _GROUND_Y, wall=(215, 185, 150),
                roof=palette["accents"][1])
    _draw_tree(draw, 220, _GROUND_Y)
    _draw_character(draw, 195, _GROUND_Y, shirt=palette["accents"][1])


def _scene_sky(draw: Any, palette: dict, panel_num: int) -> None:
    for cx, cy in [(80, 80), (200, 50), (320, 80), (140, 130), (280, 120)]:
        _draw_cloud(draw, cx, cy)
    _draw_sun(draw, 350, 50, color=palette["sun"])
    _draw_character(draw, 180 + panel_num * 20, 130,
                    shirt=palette["accents"][0])
    for bx, by in [(100, 110), (250, 90), (310, 130)]:
        for dx, dy in [(-12, 0), (12, 0)]:
            draw.ellipse([bx + dx - 10, by + dy - 6, bx + dx + 10, by + dy + 6],
                         fill=palette["accents"][2])


def _scene_fantasy_castle(draw: Any, palette: dict, panel_num: int) -> None:
    _draw_moon(draw, 340, 50)
    cx = 180
    draw.rectangle([cx - 55, _GROUND_Y - 110, cx + 55, _GROUND_Y],
                   fill=(160, 130, 200), outline=(100, 70, 150), width=3)
    for tx in [cx - 55, cx - 10, cx + 10, cx + 55]:
        draw.rectangle([tx - 14, _GROUND_Y - 145, tx + 14, _GROUND_Y - 100],
                       fill=(140, 110, 180), outline=(100, 70, 150), width=2)
        pts = [(tx - 14, _GROUND_Y - 145), (tx, _GROUND_Y - 165), (tx + 14, _GROUND_Y - 145)]
        draw.polygon(pts, fill=palette["accents"][0])
    draw.rectangle([cx - 16, _GROUND_Y - 45, cx + 16, _GROUND_Y],
                   fill=(80, 60, 30))
    draw.ellipse([cx - 16, _GROUND_Y - 60, cx + 16, _GROUND_Y - 36],
                 fill=(80, 60, 30))
    _draw_dragon(draw, 310, 130, color=(100, 200, 120))
    for sx, sy in [(50, 90), (80, 60), (130, 40), (300, 55), (370, 80)]:
        _draw_star(draw, sx, sy, r=8, color=palette["accents"][1])


def _scene_space(draw: Any, palette: dict, panel_num: int) -> None:
    import random as _rng
    rng = _rng.Random(panel_num * 42)
    for _ in range(25):
        sx, sy = rng.randint(10, _W - 10), rng.randint(10, _GROUND_Y - 20)
        sr = rng.randint(2, 6)
        _draw_star(draw, sx, sy, r=sr, color=palette["sun"])
    _draw_planet(draw, 300, 80, r=35, color=palette["accents"][0])
    _draw_planet(draw, 80, 60, r=20, color=palette["accents"][1])
    _draw_rocket(draw, 190 + panel_num * 15, 110)


def _scene_garden(draw: Any, palette: dict, panel_num: int) -> None:
    _draw_sun(draw, 340, 50, color=palette["sun"])
    _draw_cloud(draw, 130, 60)
    for fx, fy in [(70, _GROUND_Y), (110, _GROUND_Y - 5), (160, _GROUND_Y),
                   (250, _GROUND_Y - 3), (300, _GROUND_Y), (350, _GROUND_Y - 5)]:
        _draw_flower(draw, fx, fy, petal=palette["accents"][fx % len(palette["accents"])])
    _draw_tree(draw, 200, _GROUND_Y)
    _draw_character(draw, 200 + panel_num * 15, _GROUND_Y,
                    shirt=palette["accents"][1])
    for bx, by in [(170, _GROUND_Y - 80), (230, _GROUND_Y - 70)]:
        draw.ellipse([bx - 10, by - 6, bx + 10, by + 6], fill=(255, 180, 80))
        draw.ellipse([bx + 10, by - 10, bx + 25, by + 2], fill=(255, 130, 30))


def _scene_party(draw: Any, palette: dict, panel_num: int) -> None:
    _draw_sun(draw, 340, 50, color=palette["sun"])
    _draw_cake(draw, 200, _GROUND_Y)
    _draw_character(draw, 130, _GROUND_Y, shirt=palette["accents"][0])
    _draw_character(draw, 270, _GROUND_Y, shirt=palette["accents"][1])
    for bx, by in [(80, 120), (140, 90), (250, 100), (320, 110), (170, 70), (220, 80)]:
        draw.ellipse([bx - 10, by - 10, bx + 10, by + 10],
                     fill=palette["accents"][bx % 3], outline=(200, 200, 200), width=2)
        draw.line([bx, by + 10, bx + (bx % 20 - 10), by + 40],
                  fill=(200, 200, 200), width=1)


def _scene_night(draw: Any, palette: dict, panel_num: int) -> None:
    import random as _rng
    rng = _rng.Random(panel_num * 17)
    for _ in range(20):
        sx, sy = rng.randint(10, _W - 10), rng.randint(10, 140)
        _draw_star(draw, sx, sy, r=rng.randint(3, 8))
    _draw_moon(draw, 320, 60)
    _draw_house(draw, 170, _GROUND_Y, wall=(60, 55, 80), roof=(80, 40, 60))
    for wx in [70, 230, 330]:
        draw.ellipse([wx - 8, _GROUND_Y - 95, wx + 8, _GROUND_Y - 80],
                     fill=(255, 230, 100))
    _draw_character(draw, 260, _GROUND_Y, shirt=palette["accents"][0])


_SCENE_DRAWERS = {
    "meadow":         _scene_meadow,
    "forest":         _scene_forest,
    "ocean":          _scene_ocean,
    "mountain":       _scene_mountain,
    "village":        _scene_village,
    "sky":            _scene_sky,
    "fantasy_castle": _scene_fantasy_castle,
    "space":          _scene_space,
    "garden":         _scene_garden,
    "party":          _scene_party,
    "night":          _scene_night,
}

# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def draw_panel_image(narration: str, panel_num: int, style: str = "adventure") -> str:
    """
    Generate a child-drawing-style JPEG for one comic panel.

    Parameters
    ----------
    narration : str
        The panel narration text — used to detect the scene type.
    panel_num : int
        Zero-based panel index — drives palette variation and character positions.
    style : str
        User-selected comic style (adventure / fantasy / friendship / mystery /
        animals / space).  Controls the colour palette.

    Returns
    -------
    str
        Base64-encoded JPEG image (no data-URI prefix).
    """
    from PIL import Image, ImageDraw

    palette = _get_palette(style)
    scene = _detect_scene(narration)
    drawer = _SCENE_DRAWERS.get(scene, _scene_meadow)

    img = Image.new("RGB", (_W, _H), palette["sky"])
    draw = ImageDraw.Draw(img)

    # Ground
    draw.rectangle([0, _GROUND_Y, _W, _H], fill=palette["ground"])

    # Grass tufts
    acc = palette["accents"]
    grass_color = tuple(min(255, c + 30) for c in palette["ground"])
    for gx in range(0, _W, 18):
        gy = _GROUND_Y - 2
        draw.polygon([(gx, gy), (gx + 5, gy - 10), (gx + 9, gy)],
                     fill=grass_color)

    # Draw scene elements
    drawer(draw, palette, panel_num)

    # Bold comic panel border
    draw.rectangle([0, 0, _W - 1, _H - 1], outline=(20, 20, 20), width=4)

    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=88)
    return base64.b64encode(buf.getvalue()).decode()
