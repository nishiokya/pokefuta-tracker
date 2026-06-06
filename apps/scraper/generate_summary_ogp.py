#!/usr/bin/env python3
"""Generate a static OGP image for the summary page (1200×630 PNG).

Output: apps/web/assets/ogp/pokefuta_summary_ogp.png

Design:
- Background: #f7f0df (summary page background)
- Accent / brand: #176f68 (teal)
- Main text: "ポケふたは全国に何個ある？"
- Sub text:  "全国のポケモンマンホール 都道府県別データ"
- Decorative pokefuta marker (drawn with PIL shapes, matching pokefuta-marker.svg)
- Footer brand strip: #176f68
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Optional

from PIL import Image, ImageDraw, ImageFilter, ImageFont

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
CANVAS_W, CANVAS_H = 1200, 630
BG_COLOR      = (247, 240, 223)   # #f7f0df
TEAL          = (23, 111, 104)    # #176f68
TEAL_LIGHT    = (41, 163, 154)    # lighter teal for gradient-like accents
TEAL_DARK     = (15,  74,  70)    # darker teal for footer
WHITE         = (255, 255, 255)
DARK_TEXT     = ( 40,  36,  30)   # near-black for main heading
SUB_TEXT      = ( 80,  72,  60)   # brownish dark for subtext
ACCENT_SAND   = (202, 179, 130)   # sandy accent line
PURPLE_MARKER = (111,  85, 163)   # pokefuta marker purple (#6F55A3)
RED_MARKER    = (216,  68,  68)   # marker top arc
BLUE_MARKER   = ( 91, 165, 216)   # marker bottom arc

ROOT   = Path(__file__).resolve().parents[2]
OUTPUT = ROOT / "apps/web/assets/ogp/pokefuta_summary_ogp.png"
NDJSON = ROOT / "docs/pokefuta.ndjson"


def _compute_stats() -> tuple[int, int]:
    """Return (total_count, installed_pref_count) from pokefuta.ndjson."""
    if not NDJSON.exists():
        sys.exit(f"[generate_summary_ogp] {NDJSON} が見つかりません。")
    by_id: dict[str, dict] = {}
    with NDJSON.open(encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                r = json.loads(line)
            except json.JSONDecodeError:
                continue
            rid = str(r.get("id", "")).strip()
            if rid:
                by_id[rid] = {**by_id.get(rid, {}), **r}
    records = list(by_id.values())
    pref_counts: dict[str, int] = {}
    for r in records:
        pref = r.get("prefecture", "")
        if pref:
            pref_counts[pref] = pref_counts.get(pref, 0) + 1
    total = sum(pref_counts.values())
    installed = sum(1 for c in pref_counts.values() if c > 0)
    return total, installed

# ---------------------------------------------------------------------------
# Fonts
# ---------------------------------------------------------------------------
_FONT_BOLD = [
    "/System/Library/Fonts/ヒラギノ角ゴシック W6.ttc",
    "/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc",
    "/usr/share/fonts/truetype/noto/NotoSansCJK-Bold.ttc",
    "/usr/share/fonts/noto-cjk/NotoSansCJKjp-Bold.otf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
]
_FONT_REGULAR = [
    "/System/Library/Fonts/ヒラギノ角ゴシック W3.ttc",
    "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
    "/usr/share/fonts/truetype/noto/NotoSansCJK-Regular.ttc",
    "/usr/share/fonts/noto-cjk/NotoSansCJKjp-Regular.otf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
]


def _find_font(paths: list[str]) -> Optional[Path]:
    for p in paths:
        if Path(p).exists():
            return Path(p)
    return None


def _tt(path: Optional[Path], size: int) -> ImageFont.ImageFont:
    if path is None:
        return ImageFont.load_default()
    try:
        return ImageFont.truetype(str(path), size, index=0)
    except Exception:
        return ImageFont.load_default()


def load_fonts() -> dict:
    bold = _find_font(_FONT_BOLD)
    reg  = _find_font(_FONT_REGULAR)
    if reg is None:
        reg = bold
    return {
        "heading":  _tt(bold, 76),
        "heading_sm": _tt(bold, 60),
        "sub":      _tt(reg,  34),
        "label":    _tt(bold, 22),
        "footer":   _tt(reg,  20),
        "count":    _tt(bold, 110),
        "count_unit": _tt(bold, 46),
    }


# ---------------------------------------------------------------------------
# Text helpers
# ---------------------------------------------------------------------------

def _w(draw: ImageDraw.ImageDraw, text: str, font) -> int:
    try:
        return int(draw.textlength(text, font=font))
    except Exception:
        return len(text) * 12


def _bbox(draw: ImageDraw.ImageDraw, text: str, font):
    try:
        return draw.textbbox((0, 0), text, font=font)
    except Exception:
        return (0, 0, len(text) * 12, 16)


# ---------------------------------------------------------------------------
# Drawing helpers
# ---------------------------------------------------------------------------

def draw_marker(img: Image.Image, cx: int, cy: int, scale: float = 1.0) -> None:
    """Draw a pokefuta-style map marker (teardrop pin) using PIL.

    Matches pokefuta-marker.svg viewBox 0 0 64 76:
      teardrop body centred at (32, 28), tip at (32, 74).
    """
    # Map SVG coordinate space → pixel space
    def px(v: float) -> int:
        return int(cx + (v - 32) * scale)

    def py(v: float) -> int:
        return int(cy + (v - 28) * scale)

    r_body  = 26 * scale   # half-width of circular top of teardrop
    r_outer = 18 * scale   # inner white ring radius
    r_inner = 14 * scale   # dark pokéball circle radius
    r_dot   =  6 * scale   # centre dot radius

    stroke = max(2, int(4 * scale))

    # --- Drop shadow ---
    shadow = Image.new("RGBA", img.size, (0, 0, 0, 0))
    sd = ImageDraw.Draw(shadow)
    blur_r = max(6, int(10 * scale))
    sh_off = int(6 * scale)
    # Shadow: ellipse for body + triangle for tip
    sd.ellipse([px(6) + sh_off, py(2) + sh_off,
                px(58) + sh_off, py(54) + sh_off],
               fill=(30, 20, 10, 90))
    sd.polygon([
        (px(32) + sh_off, py(74) + sh_off),
        (px(18) + sh_off, py(46) + sh_off),
        (px(46) + sh_off, py(46) + sh_off),
    ], fill=(30, 20, 10, 90))
    img.alpha_composite(shadow.filter(ImageFilter.GaussianBlur(blur_r)))

    d = ImageDraw.Draw(img)

    # --- White border (drawn first, slightly larger) ---
    # Teardrop = top circle + bottom triangle for the tip
    # White outline
    d.ellipse([px(6) - stroke, py(2) - stroke,
               px(58) + stroke, py(54) + stroke],
              fill=WHITE)
    d.polygon([
        (px(32),          py(74) + stroke),
        (px(14) - stroke, py(42)),
        (px(50) + stroke, py(42)),
    ], fill=WHITE)

    # Purple body
    d.ellipse([px(6), py(2), px(58), py(54)], fill=PURPLE_MARKER)
    d.polygon([
        (px(32), py(74)),
        (px(16), py(44)),
        (px(48), py(44)),
    ], fill=PURPLE_MARKER)

    # --- Inner circles ---
    # White ring
    d.ellipse([px(32) - r_outer - stroke, py(28) - r_outer - stroke,
               px(32) + r_outer + stroke, py(28) + r_outer + stroke],
              fill=WHITE)

    # Dark pokéball circle
    d.ellipse([px(32) - r_inner, py(28) - r_inner,
               px(32) + r_inner, py(28) + r_inner],
              fill=(35, 35, 35))

    # Top-right arc: red
    d.pieslice([px(32) - r_inner, py(28) - r_inner,
                px(32) + r_inner, py(28) + r_inner],
               start=270, end=360, fill=RED_MARKER)

    # Bottom-left arc: blue
    d.pieslice([px(32) - r_inner, py(28) - r_inner,
                px(32) + r_inner, py(28) + r_inner],
               start=180, end=270, fill=BLUE_MARKER)

    # Horizontal divider line
    lw = max(1, int(4 * scale))
    d.line([(px(32) - r_inner, py(28)), (px(32) + r_inner, py(28))],
           fill=WHITE, width=lw)

    # Centre dot: cream ring + dark fill + cream centre
    d.ellipse([px(32) - r_dot - stroke, py(28) - r_dot - stroke,
               px(32) + r_dot + stroke, py(28) + r_dot + stroke],
              fill=(255, 249, 237))
    d.ellipse([px(32) - r_dot, py(28) - r_dot,
               px(32) + r_dot, py(28) + r_dot],
              fill=(35, 35, 35))
    inner = max(1, r_dot - stroke)
    d.ellipse([px(32) - inner, py(28) - inner,
               px(32) + inner, py(28) + inner],
              fill=(255, 249, 237))


def draw_rounded_rect(draw: ImageDraw.ImageDraw,
                       xy, radius: int, fill=None, outline=None, width: int = 1) -> None:
    draw.rounded_rectangle(xy, radius=radius, fill=fill, outline=outline, width=width)


# ---------------------------------------------------------------------------
# Compose
# ---------------------------------------------------------------------------

def compose(total_count: int, installed_pref: int) -> Image.Image:
    img = Image.new("RGBA", (CANVAS_W, CANVAS_H), (*BG_COLOR, 255))
    d = ImageDraw.Draw(img)
    fonts = load_fonts()

    # --- Background decorative dots grid (subtle sand dots) ---
    dot_color = (*ACCENT_SAND, 40)
    for gx in range(30, CANVAS_W, 40):
        for gy in range(30, CANVAS_H, 40):
            d.ellipse([gx - 2, gy - 2, gx + 2, gy + 2], fill=dot_color)

    # --- Left teal accent bar ---
    bar_w = 12
    d.rectangle([0, 0, bar_w, CANVAS_H], fill=(*TEAL, 255))

    # --- Top decorative rule ---
    rule_y = 56
    d.rectangle([bar_w + 30, rule_y, CANVAS_W - 40, rule_y + 3],
                fill=(*ACCENT_SAND, 180))

    # --- Bottom footer strip ---
    footer_h = 64
    footer_y = CANVAS_H - footer_h
    d.rectangle([0, footer_y, CANVAS_W, CANVAS_H], fill=(*TEAL_DARK, 255))

    # Footer text
    footer_text = "pokefuta-tracker.pages.dev"
    fw = _w(d, footer_text, fonts["footer"])
    d.text((CANVAS_W - fw - 40, footer_y + (footer_h - 20) // 2),
           footer_text, font=fonts["footer"], fill=(*WHITE, 200))

    # Footer label (left)
    site_label = "ポケふた追跡マップ"
    d.text((bar_w + 40, footer_y + (footer_h - 20) // 2),
           site_label, font=fonts["footer"], fill=(*WHITE, 255))

    # --- Right panel: teal background for marker + stat display ---
    panel_x = 720
    panel_w = CANVAS_W - panel_x
    panel_h = footer_y

    # Soft teal panel
    panel = Image.new("RGBA", (panel_w, panel_h), (*TEAL, 230))
    # Subtle gradient by layering lighter teal at top
    for gy in range(0, panel_h, 2):
        alpha = int(255 * (1 - gy / panel_h) * 0.3)
        d_panel_line = ImageDraw.Draw(panel)
        d_panel_line.rectangle([0, gy, panel_w, gy + 1],
                                fill=(*TEAL_LIGHT, alpha))
    img.alpha_composite(panel, dest=(panel_x, 0))
    d = ImageDraw.Draw(img)

    # Right panel decorative dots (white, subtle)
    for gx in range(panel_x + 20, CANVAS_W - 10, 36):
        for gy in range(20, footer_y - 10, 36):
            d.ellipse([gx - 2, gy - 2, gx + 2, gy + 2],
                      fill=(*WHITE, 30))

    # --- Pokefuta markers on right panel ---
    # Large centre marker
    marker_cx = panel_x + panel_w // 2
    marker_cy = int(footer_y * 0.42)
    draw_marker(img, cx=marker_cx, cy=marker_cy, scale=2.2)
    d = ImageDraw.Draw(img)

    # Small satellite markers
    for (ox, oy, sc) in [(-110, -80, 1.1), (115, -60, 1.0), (-80, 110, 0.9), (100, 115, 1.0)]:
        draw_marker(img, cx=marker_cx + ox, cy=marker_cy + oy, scale=sc)
    d = ImageDraw.Draw(img)

    # --- Left text column ---
    text_left = bar_w + 48
    text_max_w = panel_x - text_left - 30

    # Top label (small teal chip)
    label_text = "DATA"
    chip_h = 32
    chip_pad_x = 18
    lw = _w(d, label_text, fonts["label"])
    chip_x2 = text_left + lw + chip_pad_x * 2
    draw_rounded_rect(d, [text_left, rule_y + 18, chip_x2, rule_y + 18 + chip_h],
                      radius=chip_h // 2, fill=(*TEAL, 255))
    d.text((text_left + chip_pad_x, rule_y + 18 + (chip_h - 22) // 2),
           label_text, font=fonts["label"], fill=(*WHITE, 255))

    # Main heading
    heading = "ポケふたは全国に"
    heading2 = "何個ある？"
    y = rule_y + 18 + chip_h + 24

    # Pick font size based on width
    hfont = fonts["heading"]
    if _w(d, heading, hfont) > text_max_w:
        hfont = fonts["heading_sm"]

    d.text((text_left, y), heading, font=hfont, fill=DARK_TEXT)
    hb = _bbox(d, heading, hfont)
    y += (hb[3] - hb[1]) + 4

    d.text((text_left, y), heading2, font=hfont, fill=DARK_TEXT)
    hb2 = _bbox(d, heading2, hfont)
    y += (hb2[3] - hb2[1]) + 28

    # Accent underline
    d.rectangle([text_left, y, text_left + 120, y + 4], fill=(*TEAL, 230))
    y += 24

    # Sub text
    sub_text = "全国のポケモンマンホール"
    sub_text2 = "都道府県別データ"
    d.text((text_left, y), sub_text, font=fonts["sub"], fill=SUB_TEXT)
    sb = _bbox(d, sub_text, fonts["sub"])
    y += (sb[3] - sb[1]) + 6
    d.text((text_left, y), sub_text2, font=fonts["sub"], fill=SUB_TEXT)
    sb2 = _bbox(d, sub_text2, fonts["sub"])
    y += (sb2[3] - sb2[1]) + 36

    # --- Stat boxes: two separate pill-style cards ---
    stat_items = [
        (str(installed_pref), "都道府県"),
        (str(total_count), "設置枚数"),
    ]
    box_h = 72
    box_gap = 16
    # Compute each box width to fit content with padding
    boxes = []
    for val, unit in stat_items:
        vw = _w(d, val, fonts["count_unit"])
        uw = _w(d, unit, fonts["label"])
        box_w = vw + uw + 48  # 24px padding each side
        boxes.append((val, unit, vw, uw, box_w))

    bx = text_left
    for val, unit, vw, uw, box_w in boxes:
        box_y = y
        draw_rounded_rect(d, [bx, box_y, bx + box_w, box_y + box_h],
                          radius=14,
                          fill=(*WHITE, 220),
                          outline=(*TEAL, 255),
                          width=3)
        # Value + unit horizontally centred in box
        total_w = vw + uw + 6
        group_x = bx + (box_w - total_w) // 2
        vy = box_y + (box_h - 46) // 2
        d.text((group_x, vy), val, font=fonts["count_unit"], fill=(*TEAL, 255))
        # Unit aligned to baseline of value
        vb = _bbox(d, val, fonts["count_unit"])
        val_h = vb[3] - vb[1]
        ub = _bbox(d, unit, fonts["label"])
        unit_h = ub[3] - ub[1]
        d.text((group_x + vw + 6, vy + val_h - unit_h - 2),
               unit, font=fonts["label"], fill=SUB_TEXT)
        bx += box_w + box_gap

    # --- Bottom rule above footer ---
    d.rectangle([bar_w + 30, footer_y - 4, CANVAS_W - 40, footer_y - 1],
                fill=(*ACCENT_SAND, 120))

    return img.convert("RGB")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    total_count, installed_pref = _compute_stats()
    img = compose(total_count, installed_pref)
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    img.save(str(OUTPUT), "PNG", optimize=True)
    print(f"Saved: {OUTPUT}  ({img.width}×{img.height})")


if __name__ == "__main__":
    main()
