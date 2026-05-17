#!/usr/bin/env python3
"""Generate per-manhole OGP images (1200×630 JPEG) for social sharing.

Usage:
    python3 generate_manhole_ogp.py \
        --manholes docs/pokefuta.ndjson \
        --image-dir dataset/manhole/image \
        --output dist/assets/ogp/manholes
"""
from __future__ import annotations

import argparse
import json
import logging
import urllib.request
from pathlib import Path
from typing import Optional

from PIL import Image, ImageDraw, ImageFont

# --- Canvas layout ---
CANVAS_W = 1200
CANVAS_H = 630
PHOTO_SIZE = 630       # left panel: square equal to canvas height
RIGHT_X = PHOTO_SIZE + 36   # 666 — left edge of right panel
RIGHT_W = CANVAS_W - RIGHT_X - 20  # ~514px usable width
BOTTOM_H = 56
BOTTOM_Y = CANVAS_H - BOTTOM_H    # 574

# --- Colors (RGB) ---
BG_COLOR             = (255, 250, 243)  # #FFFAF3
BOTTOM_BG            = ( 61,  43,  31)  # #3D2B1F
BOTTOM_TEXT_COLOR    = (255, 255, 255)
PREF_COLOR           = (136, 136, 136)  # #888888
CITY_COLOR           = ( 26,  26,  26)  # #1a1a1a
POKEMON_LABEL_COLOR  = (136, 136, 136)
POKEMON_TEXT_COLOR   = ( 61,  43,  31)  # #3D2B1F
DIVIDER_COLOR        = (224, 213, 200)  # #E0D5C8
PLACEHOLDER_BG       = (245, 237, 224)  # #F5EDE0
PLACEHOLDER_BORDER   = (200, 168, 128)  # #C8A880
PLACEHOLDER_TITLE    = (138, 100,  64)  # #8A6440
PLACEHOLDER_SUB      = (176, 128,  80)  # #B08050

BOTTOM_TEXT = "data.pokefuta.com  ／  全国470枚・387自治体"

# --- Font candidates (searched in order) ---
_FONT_BOLD = [
    # Ubuntu/CI: after apt-get install fonts-noto-cjk
    "/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc",
    "/usr/share/fonts/truetype/noto/NotoSansCJK-Bold.ttc",
    "/usr/share/fonts/noto-cjk/NotoSansCJKjp-Bold.otf",
    # macOS
    "/System/Library/Fonts/ヒラギノ角ゴシック W6.ttc",
    # DejaVu (always present on Ubuntu but no Japanese glyphs — won't crash)
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
]
_FONT_REGULAR = [
    "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
    "/usr/share/fonts/truetype/noto/NotoSansCJK-Regular.ttc",
    "/usr/share/fonts/noto-cjk/NotoSansCJKjp-Regular.otf",
    "/System/Library/Fonts/ヒラギノ角ゴシック W3.ttc",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
]
_FALLBACK_URL  = "https://github.com/googlefonts/noto-cjk/raw/main/Sans/SubsetOTF/JP/NotoSansCJKjp-Bold.otf"
_FALLBACK_TMP  = Path("/tmp/pokefuta-NotoSansCJKjp-Bold.otf")

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Font helpers
# ---------------------------------------------------------------------------

def _find_system_font(paths: list[str]) -> Optional[Path]:
    for p in paths:
        if Path(p).exists():
            return Path(p)
    return None


def _download_fallback(url: str, dest: Path) -> Optional[Path]:
    if dest.exists():
        return dest
    try:
        logger.warning("No system Japanese font found — downloading fallback to /tmp ...")
        urllib.request.urlretrieve(url, dest)
        logger.info("Downloaded fallback font: %s", dest)
        return dest
    except Exception as exc:
        logger.error("Failed to download fallback font: %s", exc)
        return None


def _truetype(path: Optional[Path], size: int) -> ImageFont.FreeTypeFont:
    if path is None:
        return ImageFont.load_default()
    try:
        return ImageFont.truetype(str(path), size, index=0)
    except Exception as exc:
        logger.warning("Failed to load font %s at size %d: %s", path, size, exc)
        return ImageFont.load_default()


def load_fonts() -> dict:
    """Return a dict of named ImageFont objects."""
    bold_path = _find_system_font(_FONT_BOLD)
    reg_path  = _find_system_font(_FONT_REGULAR)

    if bold_path is None:
        bold_path = _download_fallback(_FALLBACK_URL, _FALLBACK_TMP)
    if reg_path is None:
        reg_path = bold_path  # use bold as regular fallback

    if bold_path is None:
        logger.warning("No Japanese font available — Japanese text will render as boxes.")

    return {
        "pref":              _truetype(reg_path,  20),
        "city_large":        _truetype(bold_path, 44),
        "city_small":        _truetype(bold_path, 34),
        "pokemon_label":     _truetype(reg_path,  13),
        "pokemon_text":      _truetype(bold_path, 20),
        "bottom":            _truetype(bold_path, 15),
        "placeholder_title": _truetype(bold_path, 28),
        "placeholder_sub":   _truetype(reg_path,  18),
    }


# ---------------------------------------------------------------------------
# Drawing helpers
# ---------------------------------------------------------------------------

def _text_w(draw: ImageDraw.ImageDraw, text: str, font) -> int:
    try:
        return int(draw.textlength(text, font=font))
    except Exception:
        return len(text) * 12


def _text_bbox(draw: ImageDraw.ImageDraw, text: str, font):
    try:
        return draw.textbbox((0, 0), text, font=font)
    except Exception:
        w = len(text) * 12
        return (0, 0, w, 16)


def _wrap_pokemon(draw: ImageDraw.ImageDraw, text: str, font, max_w: int) -> list[str]:
    """Split at '・' so each line fits within max_w pixels."""
    parts = text.split("・")
    lines: list[str] = []
    current = ""
    for part in parts:
        sep = "・" if current else ""
        candidate = current + sep + part
        if _text_w(draw, candidate, font) <= max_w:
            current = candidate
        else:
            if current:
                lines.append(current)
            current = part
    if current:
        lines.append(current)
    return lines or [text]


def _dashed_rect(
    draw: ImageDraw.ImageDraw,
    x1: int, y1: int, x2: int, y2: int,
    color: tuple, dash: int = 10, gap: int = 6, width: int = 2,
) -> None:
    """Draw a dashed rectangle border."""
    def segments(a: int, b: int):
        pos, on = a, True
        while pos < b:
            end = min(pos + (dash if on else gap), b)
            if on:
                yield pos, end
            pos, on = end, not on

    for xs, xe in segments(x1, x2):
        draw.line([(xs, y1), (xe, y1)], fill=color, width=width)
        draw.line([(xs, y2), (xe, y2)], fill=color, width=width)
    for ys, ye in segments(y1, y2):
        draw.line([(x1, ys), (x1, ye)], fill=color, width=width)
        draw.line([(x2, ys), (x2, ye)], fill=color, width=width)


def _draw_photo_zone(img: Image.Image, local_jpeg: Optional[Path], fonts: dict) -> None:
    """Fill the left 630×630 area with a photo or a placeholder card."""
    if local_jpeg and local_jpeg.exists():
        try:
            src = Image.open(local_jpeg).convert("RGB")
            w, h = src.size
            side = min(w, h)
            src = src.crop(((w - side) // 2, (h - side) // 2,
                             (w + side) // 2, (h + side) // 2))
            src = src.resize((PHOTO_SIZE, PHOTO_SIZE), Image.LANCZOS)
            img.paste(src, (0, 0))
            return
        except Exception as exc:
            logger.warning("Could not load photo %s: %s", local_jpeg, exc)

    # --- Placeholder ---
    draw = ImageDraw.Draw(img)
    draw.rectangle([0, 0, PHOTO_SIZE - 1, PHOTO_SIZE - 1], fill=PLACEHOLDER_BG)
    margin = 48
    _dashed_rect(draw, margin, margin, PHOTO_SIZE - margin, BOTTOM_Y - margin,
                 PLACEHOLDER_BORDER)

    title_text = "写真募集中"
    sub_text   = "このポケふたの旅写真を募集中"
    t_font = fonts["placeholder_title"]
    s_font = fonts["placeholder_sub"]

    t_bb = _text_bbox(draw, title_text, t_font)
    s_bb = _text_bbox(draw, sub_text,   s_font)
    t_h  = t_bb[3] - t_bb[1]
    s_h  = s_bb[3] - s_bb[1]
    total_h = t_h + 12 + s_h
    center_y = BOTTOM_Y // 2

    ty = center_y - total_h // 2
    draw.text(
        (PHOTO_SIZE // 2 - (t_bb[2] - t_bb[0]) // 2, ty),
        title_text, font=t_font, fill=PLACEHOLDER_TITLE,
    )
    draw.text(
        (PHOTO_SIZE // 2 - (s_bb[2] - s_bb[0]) // 2, ty + t_h + 12),
        sub_text, font=s_font, fill=PLACEHOLDER_SUB,
    )


def _draw_right_panel(
    draw: ImageDraw.ImageDraw,
    prefecture: str,
    city: str,
    pokemon_text: str,
    fonts: dict,
) -> None:
    x = RIGHT_X

    draw.text((x, 44), prefecture, font=fonts["pref"], fill=PREF_COLOR)

    city_font = fonts["city_large"]
    if _text_w(draw, city, city_font) > RIGHT_W:
        city_font = fonts["city_small"]
    draw.text((x, 84), city, font=city_font, fill=CITY_COLOR)

    draw.line([(x, 140), (CANVAS_W - 20, 140)], fill=DIVIDER_COLOR, width=1)
    draw.text((x, 154), "登場ポケモン", font=fonts["pokemon_label"], fill=POKEMON_LABEL_COLOR)

    lines = _wrap_pokemon(draw, pokemon_text, fonts["pokemon_text"], RIGHT_W)
    y = 176
    for line in lines[:3]:
        draw.text((x, y), line, font=fonts["pokemon_text"], fill=POKEMON_TEXT_COLOR)
        y += 30


def _draw_bottom_bar(draw: ImageDraw.ImageDraw, fonts: dict) -> None:
    draw.rectangle([0, BOTTOM_Y, CANVAS_W, CANVAS_H], fill=BOTTOM_BG)
    w = _text_w(draw, BOTTOM_TEXT, fonts["bottom"])
    bb = _text_bbox(draw, BOTTOM_TEXT, fonts["bottom"])
    text_h = bb[3] - bb[1]
    x = (CANVAS_W - w) // 2
    y = BOTTOM_Y + (BOTTOM_H - text_h) // 2
    draw.text((x, y), BOTTOM_TEXT, font=fonts["bottom"], fill=BOTTOM_TEXT_COLOR)


# ---------------------------------------------------------------------------
# Main generation
# ---------------------------------------------------------------------------

def _filter_pokemons(raw: list) -> list[str]:
    return [p for p in raw if isinstance(p, str) and p.strip() and "ローカルActs" not in p]


def generate_ogp_image(
    manhole: dict,
    local_jpeg: Optional[Path],
    output_path: Path,
    fonts: dict,
) -> bool:
    """Generate a 1200×630 OGP JPEG for one manhole. Returns True on success."""
    try:
        prefecture   = manhole.get("prefecture", "")
        city         = manhole.get("city", "")
        pokemons     = _filter_pokemons(manhole.get("pokemons", []))
        pokemon_text = "・".join(pokemons) if pokemons else "ポケモン"

        img  = Image.new("RGB", (CANVAS_W, CANVAS_H), BG_COLOR)
        draw = ImageDraw.Draw(img)

        _draw_photo_zone(img, local_jpeg, fonts)
        _draw_right_panel(draw, prefecture, city, pokemon_text, fonts)
        _draw_bottom_bar(draw, fonts)

        output_path.parent.mkdir(parents=True, exist_ok=True)
        img.save(str(output_path), "JPEG", quality=85, optimize=True)
        return True
    except Exception as exc:
        logger.warning("OGP generation failed for manhole %s: %s", manhole.get("id"), exc)
        return False


def generate_all_ogp(
    manholes: list[dict],
    image_dir: Path,
    output_dir: Path,
    force: bool = False,
) -> tuple[int, int, int]:
    """Generate OGP images for all manholes.

    Returns (total, generated, skipped).
    """
    fonts = load_fonts()
    total = generated = skipped = 0

    for manhole in manholes:
        mid = str(manhole.get("id", "")).strip()
        if not mid:
            continue
        total += 1

        output_path = output_dir / f"{mid}.jpg"
        if not force and output_path.exists():
            skipped += 1
            continue

        local_jpeg: Optional[Path] = image_dir / f"{mid}_latest.jpeg"
        if not local_jpeg.exists():
            local_jpeg = None

        if generate_ogp_image(manhole, local_jpeg, output_path, fonts):
            generated += 1

    return total, generated, skipped


# ---------------------------------------------------------------------------
# Data loading
# ---------------------------------------------------------------------------

def load_manholes(path: Path) -> list[dict]:
    manholes: list[dict] = []
    if not path.exists():
        logger.warning("Manhole data file not found: %s", path)
        return manholes
    for line_num, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        try:
            manholes.append(json.loads(line))
        except json.JSONDecodeError as exc:
            logger.warning("Failed to parse line %d: %s", line_num, exc)
    return manholes


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manholes",  default="docs/pokefuta.ndjson",
                        help="Path to manholes NDJSON file")
    parser.add_argument("--image-dir", default="dataset/manhole/image",
                        help="Directory containing {id}_latest.jpeg files")
    parser.add_argument("--output",    default="dist/assets/ogp/manholes",
                        help="Output directory for JPEG files")
    parser.add_argument("--force",     action="store_true",
                        help="Regenerate images that already exist")
    parser.add_argument("--log-level", default="INFO",
                        choices=["DEBUG", "INFO", "WARNING", "ERROR"])
    args = parser.parse_args()

    logging.basicConfig(
        level=getattr(logging, args.log_level),
        format="%(levelname)s: %(message)s",
    )

    manholes = load_manholes(Path(args.manholes))
    if not manholes:
        logger.error("No manholes loaded — aborting.")
        return 1

    output_dir = Path(args.output)
    output_dir.mkdir(parents=True, exist_ok=True)

    total, generated, skipped = generate_all_ogp(
        manholes, Path(args.image_dir), output_dir, force=args.force,
    )
    print(f"[generate_manhole_ogp] total: {total}  generated: {generated}  skipped: {skipped}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
