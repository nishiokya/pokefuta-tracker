#!/usr/bin/env python3
"""Generate per-manhole OGP images (1200×630 PNG) for social sharing.

Pipeline:
  1. A decorative "travel poster" background lives as an SVG template
     (apps/web/assets/ogp/manhole_template.svg).
  2. At build time it is rasterized to a 1200×630 PNG base
     (cairosvg → rsvg-convert → committed fallback PNG).
  3. PIL composites the per-manhole data onto that base:
       都道府県 / 自治体 / 設置場所 / 登場ポケモン / 3情報チップ /
       コメント本文 / マンホール写真（円形・影）。

Usage:
    python3 generate_manhole_ogp.py \
        --manholes docs/pokefuta.ndjson \
        --image-dir dataset/manhole/image \
        --photos docs/latest-manhole-photos.json \
        --pokemon docs/pokemon_metadata.json \
        --output dist/assets/ogp/manholes
"""
from __future__ import annotations

import argparse
import datetime
import json
import logging
import math
import shutil
import subprocess
import urllib.request
from pathlib import Path
from typing import Optional

from PIL import Image, ImageDraw, ImageFilter, ImageFont

# --- Canvas ---
CANVAS_W, CANVAS_H = 1200, 630

# --- Coordinate contract (must match manhole_template.svg) ---
LEFT_X       = 60                 # left text column
TEXT_MAX_W   = 600                # left column wrap width
PHOTO_CX, PHOTO_CY, PHOTO_R = 925, 312, 150   # photo circle (in right map panel)

# --- Colors ---
PREF_COLOR    = ( 60,  52,  44)
CITY_COLOR    = (111,  85, 163)   # #6F55A3
LOC_COLOR     = (110,  98,  84)
LABEL_COLOR   = (154, 122,  63)   # #9A7A3F
POKE_COLOR    = ( 44,  44,  44)
CHIP_VAL      = ( 74,  58, 106)
COMMENT_COLOR = ( 74,  62,  50)
PH_CIRCLE     = (233, 222, 198)
PH_TEXT       = (150, 124,  82)
CREDIT_COLOR  = (140, 128, 112)

DEFAULT_SVG = Path("apps/web/assets/ogp/manhole_template.svg")

# --- Font candidates ---
_FONT_BOLD = [
    "/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc",
    "/usr/share/fonts/truetype/noto/NotoSansCJK-Bold.ttc",
    "/usr/share/fonts/noto-cjk/NotoSansCJKjp-Bold.otf",
    "/System/Library/Fonts/ヒラギノ角ゴシック W6.ttc",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
]
_FONT_REGULAR = [
    "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
    "/usr/share/fonts/truetype/noto/NotoSansCJK-Regular.ttc",
    "/usr/share/fonts/noto-cjk/NotoSansCJKjp-Regular.otf",
    "/System/Library/Fonts/ヒラギノ角ゴシック W3.ttc",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
]
_FALLBACK_URL = "https://github.com/googlefonts/noto-cjk/raw/main/Sans/SubsetOTF/JP/NotoSansCJKjp-Bold.otf"
_FALLBACK_TMP = Path("/tmp/pokefuta-NotoSansCJKjp-Bold.otf")

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Fonts
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
        logger.warning("No system Japanese font — downloading fallback to /tmp ...")
        with urllib.request.urlopen(url, timeout=30) as resp:
            dest.write_bytes(resp.read())
        return dest
    except Exception as exc:
        logger.error("Failed to download fallback font: %s", exc)
        return None


def _tt(path: Optional[Path], size: int) -> ImageFont.FreeTypeFont:
    if path is None:
        return ImageFont.load_default()
    try:
        return ImageFont.truetype(str(path), size, index=0)
    except Exception:
        return ImageFont.load_default()


def load_fonts() -> dict:
    bold = _find_system_font(_FONT_BOLD)
    reg  = _find_system_font(_FONT_REGULAR)
    if bold is None:
        bold = _download_fallback(_FALLBACK_URL, _FALLBACK_TMP)
    if reg is None:
        reg = bold
    return {
        "pref":        _tt(reg,  30),
        "city":        _tt(bold, 64),
        "city_sm":     _tt(bold, 48),
        "loc":         _tt(reg,  25),
        "label":       _tt(bold, 17),
        "poke":        _tt(bold, 38),
        "poke_sm":     _tt(bold, 28),
        "chip":        _tt(bold, 16),
        "comment":     _tt(reg,  21),
        "ph":          _tt(bold, 28),
        "ph_sm":       _tt(reg,  18),
        "credit":      _tt(reg,  16),
    }


# ---------------------------------------------------------------------------
# Text helpers
# ---------------------------------------------------------------------------

def _w(draw, text, font) -> int:
    try:
        return int(draw.textlength(text, font=font))
    except Exception:
        return len(text) * 12


def _bbox(draw, text, font):
    try:
        return draw.textbbox((0, 0), text, font=font)
    except Exception:
        return (0, 0, len(text) * 12, 16)


def _wrap(draw, text, font, max_w, max_lines) -> list[str]:
    text = " ".join(str(text).split())
    lines, cur = [], ""
    for ch in text:
        if _w(draw, cur + ch, font) <= max_w:
            cur += ch
        else:
            lines.append(cur)
            cur = ch
            if len(lines) == max_lines:
                break
    if len(lines) < max_lines and cur:
        lines.append(cur)
    if len(lines) == max_lines and sum(len(l) for l in lines) < len(text):
        last = lines[-1]
        while last and _w(draw, last + "...", font) > max_w:
            last = last[:-1]
        lines[-1] = last + "..."
    return lines


# ---------------------------------------------------------------------------
# Base template rasterization
# ---------------------------------------------------------------------------

def rasterize_base(svg_path: Path) -> Image.Image:
    """SVG → 1200×630 RGBA. cairosvg → rsvg-convert → committed PNG fallback."""
    tmp = Path("/tmp/pokefuta-ogp-base.png")
    # 1. cairosvg (CI / Linux with libcairo2)
    try:
        import cairosvg
        cairosvg.svg2png(url=str(svg_path), write_to=str(tmp),
                         output_width=CANVAS_W, output_height=CANVAS_H)
        logger.info("Base rasterized via cairosvg")
        return Image.open(tmp).convert("RGBA")
    except Exception as exc:
        logger.info("cairosvg unavailable (%s) — trying rsvg-convert", exc)
    # 2. rsvg-convert (local dev)
    if shutil.which("rsvg-convert"):
        try:
            subprocess.run(
                ["rsvg-convert", "-w", str(CANVAS_W), "-h", str(CANVAS_H),
                 "-b", "#FBF6EA", str(svg_path), "-o", str(tmp)],
                check=True, capture_output=True,
            )
            logger.info("Base rasterized via rsvg-convert")
            return Image.open(tmp).convert("RGBA")
        except Exception as exc:
            logger.warning("rsvg-convert failed: %s", exc)
    # 3. committed PNG fallback next to the SVG
    fallback = svg_path.with_suffix(".png")
    if fallback.exists():
        logger.info("Using committed fallback PNG: %s", fallback)
        return Image.open(fallback).convert("RGBA").resize((CANVAS_W, CANVAS_H))
    raise RuntimeError(
        "No SVG rasterizer available and no fallback PNG. "
        "Install cairosvg (+libcairo2) or commit manhole_template.png"
    )


# ---------------------------------------------------------------------------
# Data shaping
# ---------------------------------------------------------------------------

def _haversine(lat1, lng1, lat2, lng2) -> float:
    r = 6371.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = math.radians(lat2 - lat1)
    dl = math.radians(lng2 - lng1)
    a = (math.sin(dp / 2) ** 2
         + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2)
    return r * 2 * math.asin(math.sqrt(a))


def build_stats(manholes: list[dict]) -> dict:
    """Precompute exploration counts shared across all OGP cards."""
    pref_count: dict[str, int] = {}
    poke_count: dict[str, int] = {}
    coords: list[tuple[str, float, float]] = []
    for m in manholes:
        pref = m.get("prefecture", "")
        if pref:
            pref_count[pref] = pref_count.get(pref, 0) + 1
        for pk in _filter_pokemons(m.get("pokemons", [])):
            poke_count[pk] = poke_count.get(pk, 0) + 1
        lat, lng = m.get("lat"), m.get("lng")
        if lat is not None and lng is not None:
            coords.append((str(m.get("id", "")).strip(),
                           float(lat), float(lng)))
    return {"pref_count": pref_count, "poke_count": poke_count,
            "coords": coords}


def _nearby_count(mid: str, lat, lng, coords) -> int:
    if lat is None or lng is None:
        return 0
    lat, lng = float(lat), float(lng)
    n = 0
    for oid, olat, olng in coords:
        if oid == mid:
            continue
        if _haversine(lat, lng, olat, olng) <= 30.0:
            n += 1
    return n


def _filter_pokemons(raw: list) -> list[str]:
    return [p for p in raw if isinstance(p, str) and p.strip() and "ローカルActs" not in p]


def _format_pokemon_label(pokemons: list[str]) -> str:
    if not pokemons:
        return "ポケモン"
    if len(pokemons) <= 3:
        return "・".join(pokemons)
    return "・".join(pokemons[:3]) + " ほか"


def _location_name(manhole: dict) -> str:
    building = (manhole.get("building") or "").strip()
    if building:
        return building
    addr = (manhole.get("address") or "").strip()
    if addr:
        for pref in (manhole.get("prefecture", ""), ""):
            if pref and addr.startswith(pref):
                addr = addr[len(pref):]
        city = manhole.get("city", "")
        if city and addr.startswith(city):
            addr = addr[len(city):]
        return addr.lstrip("市区町村 ")
    return ""


def _shot_date(raw: str) -> str:
    if not raw or not isinstance(raw, str):
        return ""
    try:
        dt = datetime.datetime.fromisoformat(raw.replace("Z", "+00:00"))
        return f"{dt.year}年{dt.month}月{dt.day}日"
    except (ValueError, TypeError):
        return ""


def _resolve_comment(manhole, photo_meta, manhole_comments) -> tuple[str, str]:
    """Return (comment_text, author). Falls back to a generated intro."""
    mid = str(manhole.get("id", "")).strip()
    comment = (photo_meta.get("comment") or "").strip()
    author = (photo_meta.get("display_name") or "").strip()
    if not comment:
        thread = manhole_comments.get(mid) or manhole_comments.get(str(mid)) or []
        if thread:
            comment = (thread[0].get("content") or "").strip()
            author = author or (thread[0].get("display_name") or "").strip()
    if not comment:
        label = (manhole.get("city") or manhole.get("prefecture")
                 or manhole.get("title") or "この場所")
        loc = _location_name(manhole)
        pk = _format_pokemon_label(_filter_pokemons(manhole.get("pokemons", [])))
        where = f"の{loc}に" if loc else "に"
        comment = (f"{label}{where}設置されているポケふた。"
                   f"{pk}が描かれています。")
        author = ""
    return comment, author


# ---------------------------------------------------------------------------
# Drawing
# ---------------------------------------------------------------------------

def _paste_photo_circle(base: Image.Image, local_jpeg: Path) -> bool:
    try:
        src = Image.open(local_jpeg).convert("RGB")
        d = PHOTO_R * 2
        sw, sh = src.size
        side = min(sw, sh)
        src = src.crop(((sw - side) // 2, (sh - side) // 2,
                        (sw + side) // 2, (sh + side) // 2)).resize(
                            (d, d), Image.LANCZOS)
        # soft drop shadow
        shadow = Image.new("RGBA", base.size, (0, 0, 0, 0))
        sd = ImageDraw.Draw(shadow)
        sd.ellipse([PHOTO_CX - PHOTO_R + 6, PHOTO_CY - PHOTO_R + 14,
                    PHOTO_CX + PHOTO_R + 6, PHOTO_CY + PHOTO_R + 14],
                   fill=(58, 44, 31, 110))
        base.alpha_composite(shadow.filter(ImageFilter.GaussianBlur(12)))
        # white ring
        ring = ImageDraw.Draw(base)
        ring.ellipse([PHOTO_CX - PHOTO_R - 7, PHOTO_CY - PHOTO_R - 7,
                      PHOTO_CX + PHOTO_R + 7, PHOTO_CY + PHOTO_R + 7],
                     fill=(255, 255, 255, 255))
        mask = Image.new("L", (d, d), 0)
        ImageDraw.Draw(mask).ellipse([0, 0, d, d], fill=255)
        base.paste(src, (PHOTO_CX - PHOTO_R, PHOTO_CY - PHOTO_R), mask)
        return True
    except Exception as exc:
        logger.warning("Photo paste failed (%s): %s", local_jpeg, exc)
        return False


def _draw_pill(draw, x, y_top, text, font) -> int:
    """Rounded purple NEW pill. Returns its height."""
    tb = _bbox(draw, text, font)
    tw, th = tb[2] - tb[0], tb[3] - tb[1]
    h = th + 16
    draw.rounded_rectangle([x, y_top, x + tw + 32, y_top + h],
                           radius=h // 2, fill=(111, 85, 163))
    draw.text((x + 16, y_top + 8 - tb[1]), text, font=font,
              fill=(255, 255, 255))
    return h


def _draw_placeholder_circle(base: Image.Image, fonts: dict) -> None:
    d = ImageDraw.Draw(base)
    d.ellipse([PHOTO_CX - PHOTO_R, PHOTO_CY - PHOTO_R,
               PHOTO_CX + PHOTO_R, PHOTO_CY + PHOTO_R],
              fill=(*PH_CIRCLE, 235), outline=(255, 255, 255, 255), width=7)
    for i, (txt, fkey) in enumerate((("ポケふた写真", "ph"), ("準備中", "ph_sm"))):
        f = fonts[fkey]
        bb = _bbox(d, txt, f)
        d.text((PHOTO_CX - (bb[2] - bb[0]) // 2,
                PHOTO_CY - 22 + i * 40), txt, font=f, fill=(*PH_TEXT, 255))


def compose_manhole(
    base_template: Image.Image,
    manhole: dict,
    local_jpeg: Optional[Path],
    photo_meta: dict,
    pokemon_meta: dict,
    manhole_comments: dict,
    stats: dict,
    fonts: dict,
) -> Image.Image:
    img = base_template.copy()
    draw = ImageDraw.Draw(img)

    mid = str(manhole.get("id", "")).strip()
    pref = manhole.get("prefecture", "")
    city = manhole.get("city", "") or pref
    loc = _location_name(manhole)
    pokemons = _filter_pokemons(manhole.get("pokemons", []))
    pk_label = _format_pokemon_label(pokemons)
    comment, author = _resolve_comment(manhole, photo_meta, manhole_comments)

    # 見出し：都道府県（小）＋ 自治体/サイト名（大・紫）＋ NEW ピル
    title = manhole.get("title", "")
    main = city or pref or title or "ポケふた"
    sub = pref if (city and pref) else ""

    added = manhole.get("added_at") or manhole.get("first_seen") or ""
    try:
        ay = datetime.date.fromisoformat(added[:10]).year
    except (ValueError, TypeError):
        ay = None
    pill = f"NEW {ay}年設置" if (ay and ay >= datetime.date.today().year) else ""

    y = 92
    if sub:
        draw.text((LEFT_X, y), sub, font=fonts["pref"], fill=PREF_COLOR)
        if pill:
            _draw_pill(draw, LEFT_X + _w(draw, sub, fonts["pref"]) + 18,
                       y - 2, pill, fonts["label"])
        y += 46
    elif pill:
        y += _draw_pill(draw, LEFT_X, y, pill, fonts["label"]) + 12
    # 自治体/サイト名（大・紫）
    cf = fonts["city"]
    if _w(draw, main, cf) > TEXT_MAX_W:
        cf = fonts["city_sm"]
    draw.text((LEFT_X, y), main, font=cf, fill=CITY_COLOR)
    cb = _bbox(draw, main, cf)
    y += (cb[3] - cb[1]) + 18
    # 設置場所
    if loc:
        for ln in _wrap(draw, loc, fonts["loc"], TEXT_MAX_W, 1):
            draw.text((LEFT_X, y), ln, font=fonts["loc"], fill=LOC_COLOR)
        y += 40
    else:
        y += 8
    # 登場ポケモン
    draw.text((LEFT_X, y), "登場ポケモン", font=fonts["label"], fill=LABEL_COLOR)
    y += 28
    pf = fonts["poke"]
    if _w(draw, pk_label, pf) > TEXT_MAX_W:
        pf = fonts["poke_sm"]
    for ln in _wrap(draw, pk_label, pf, TEXT_MAX_W, 2):
        draw.text((LEFT_X, y), ln, font=pf, fill=POKE_COLOR)
        bb = _bbox(draw, ln, pf)
        y += (bb[3] - bb[1]) + 8

    # 3 exploration chip values (cards fixed at y 356..440 in the SVG)
    pref_total = stats["pref_count"].get(pref, 0)
    primary = pokemons[0] if pokemons else ""
    same_total = stats["poke_count"].get(primary, 0)
    nearby = _nearby_count(mid, manhole.get("lat"), manhole.get("lng"),
                           stats["coords"])
    chip_f = fonts["chip"]
    draw.text((78, 410), f"{pref_total}枚" if pref_total else "—",
              font=chip_f, fill=CHIP_VAL)
    draw.text((266, 410), f"{same_total}枚" if same_total else "—",
              font=chip_f, fill=CHIP_VAL)
    draw.text((454, 410), f"{nearby}件", font=chip_f, fill=CHIP_VAL)

    # コメント（本文・最大2行・末尾 ...、ブランド帯に被らない）
    draw.text((LEFT_X, 464), "コメント", font=fonts["label"], fill=LABEL_COLOR)
    cy = 490
    for ln in _wrap(draw, comment, fonts["comment"], TEXT_MAX_W, 2):
        draw.text((LEFT_X, cy), ln, font=fonts["comment"], fill=COMMENT_COLOR)
        cy += 27

    # 写真（円形・影）/ 写真なし（中立の準備中サークル）
    if local_jpeg and local_jpeg.exists() and _paste_photo_circle(img, local_jpeg):
        sd = _shot_date(photo_meta.get("shot_at", ""))
        cap = "　".join([p for p in (f"{author} さん撮影" if author else "", sd) if p])
        if cap:
            cd = ImageDraw.Draw(img)
            bb = _bbox(cd, cap, fonts["credit"])
            cd.text((PHOTO_CX - (bb[2] - bb[0]) // 2, PHOTO_CY + PHOTO_R + 16),
                    cap, font=fonts["credit"], fill=CREDIT_COLOR)
    else:
        _draw_placeholder_circle(img, fonts)

    return img.convert("RGB")


# ---------------------------------------------------------------------------
# Batch
# ---------------------------------------------------------------------------

def generate_all_ogp(
    manholes, image_dir: Path, output_dir: Path,
    photos: dict, pokemon_meta: dict, manhole_comments: dict,
    svg_path: Path, force: bool = False,
) -> tuple[int, int, int]:
    fonts = load_fonts()
    base = rasterize_base(svg_path)
    stats = build_stats(manholes)
    total = generated = skipped = 0
    for manhole in manholes:
        mid = str(manhole.get("id", "")).strip()
        if not mid:
            continue
        total += 1
        out = output_dir / f"{mid}.png"
        if not force and out.exists():
            skipped += 1
            continue
        cand = image_dir / f"{mid}_latest.jpeg"
        local = cand if cand.exists() else None
        pm = photos.get(mid) or photos.get(str(mid)) or {}
        try:
            img = compose_manhole(base, manhole, local, pm, pokemon_meta,
                                  manhole_comments, stats, fonts)
            out.parent.mkdir(parents=True, exist_ok=True)
            img.save(str(out), "PNG", optimize=True)
            generated += 1
        except Exception as exc:
            logger.warning("OGP failed for %s: %s", mid, exc)
    return total, generated, skipped


# ---------------------------------------------------------------------------
# Data loading
# ---------------------------------------------------------------------------

def load_manholes(path: Path) -> list[dict]:
    out: list[dict] = []
    if not path.exists():
        logger.warning("Manhole file not found: %s", path)
        return out
    for n, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if line.strip():
            try:
                out.append(json.loads(line))
            except json.JSONDecodeError as exc:
                logger.warning("Bad line %d: %s", n, exc)
    return out


def load_photos(path: Path) -> tuple[dict, dict]:
    if not path.exists():
        logger.warning("Photos file not found: %s", path)
        return {}, {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        logger.error("Bad photos JSON: %s", exc)
        return {}, {}
    photos = {str(k): v for k, v in (data.get("photos", {}) or {}).items()}
    comments = {str(k): v for k, v in (data.get("manhole_comments", {}) or {}).items()}
    logger.info("Loaded %d photo metas, %d comment threads",
                len(photos), len(comments))
    return photos, comments


def load_pokemon_metadata(path: Path) -> dict:
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}
    return {p["names"]["ja"]: p for p in data
            if isinstance(p, dict) and p.get("names", {}).get("ja")}


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--manholes",  default="docs/pokefuta.ndjson")
    ap.add_argument("--image-dir", default="dataset/manhole/image")
    ap.add_argument("--photos",    default="docs/latest-manhole-photos.json")
    ap.add_argument("--pokemon",   default="docs/pokemon_metadata.json")
    ap.add_argument("--template",  default=str(DEFAULT_SVG),
                    help="SVG template (rasterized to the OGP background)")
    ap.add_argument("--output",    default="dist/assets/ogp/manholes")
    ap.add_argument("--force",     action="store_true")
    ap.add_argument("--log-level", default="INFO",
                    choices=["DEBUG", "INFO", "WARNING", "ERROR"])
    args = ap.parse_args()

    logging.basicConfig(level=getattr(logging, args.log_level),
                        format="%(levelname)s: %(message)s")

    manholes = load_manholes(Path(args.manholes))
    if not manholes:
        logger.error("No manholes loaded — aborting.")
        return 1
    photos, manhole_comments = load_photos(Path(args.photos))
    pokemon_meta = load_pokemon_metadata(Path(args.pokemon))

    output_dir = Path(args.output)
    output_dir.mkdir(parents=True, exist_ok=True)

    total, generated, skipped = generate_all_ogp(
        manholes, Path(args.image_dir), output_dir,
        photos, pokemon_meta, manhole_comments,
        Path(args.template), force=args.force,
    )
    print(f"[generate_manhole_ogp] total: {total}  generated: {generated}  skipped: {skipped}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
