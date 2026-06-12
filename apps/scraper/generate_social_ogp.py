#!/usr/bin/env python3
"""Generate social post image (SVG + JPEG) and OGP PNG for today's post.

Loads the Claude Design theme SVG (trivia/ranking/rare), replaces text
elements by ID, recalculates chip layout, and rasterises to JPEG + PNG.

Outputs:
  docs/social-post-image.svg  — full-resolution SVG
  docs/social-post-image.jpg  — JPEG for Twitter/X attachment
  docs/social-post-ogp.png    — OGP PNG (1200×630) for link previews

Usage:
    python3 apps/scraper/generate_social_ogp.py
"""
from __future__ import annotations

import base64
import json
import math
import os
import re
import subprocess
import sys
import tempfile
import urllib.request
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DAILY_JSON = ROOT / "docs" / "social-post-daily.json"
CANDIDATES_JSON = ROOT / "docs" / "social-post-candidates.json"
TEMPLATE_DIR = ROOT / "docs" / "ogp_template"
OUTPUT_SVG = ROOT / "docs" / "social-post-image.svg"
OUTPUT_JPG = ROOT / "docs" / "social-post-image.jpg"
OUTPUT_PNG = ROOT / "docs" / "social-post-ogp.png"
NDJSON = ROOT / "pokefuta.ndjson"
MANHOLE_IMAGE_DIR = ROOT / "dataset" / "manhole" / "image"
PREF_BOUNDARY_DIR = ROOT / "dataset" / "prefecture_boundaries"
_JAPAN_GEOJSON_URL = "https://raw.githubusercontent.com/dataofjapan/land/master/japan.geojson"
_WIRE_PHOTO_LIMIT = 15  # embed photo circles when <= this many manholes in the prefecture

_ACCENT_COLOR = {
    "trivia":  "#57E0BE",
    "ranking": "#F2C24C",
    "rare":    "#FF9466",
}
_ACCENT_BRIGHT = {
    "trivia":  "#7CF2D6",
    "ranking": "#FFD86B",
    "rare":    "#FFB088",
}

_REGION_PREFIXES = ["アローラ", "ガラル", "ヒスイ", "パルデア"]


def _poke_base_name(p: str) -> str:
    for pfx in _REGION_PREFIXES:
        p = p.replace(pfx, "").strip()
    return p


def _poke_short_label(p: str) -> str:
    for pfx in _REGION_PREFIXES:
        if p.startswith(pfx):
            return pfx
    return _poke_base_name(p)


def _poke_sub_label(p: str) -> str:
    for pfx in _REGION_PREFIXES:
        if p.startswith(pfx):
            return f"{pfx}版"
    return "通常版"


# ---------------------------------------------------------------------------
# Image conversion helpers
# ---------------------------------------------------------------------------

def svg_to_png(svg_bytes: bytes, out_path: Path) -> None:
    try:
        subprocess.run(
            ["rsvg-convert", "-f", "png", "-w", "1200", "-h", "630", "-o", str(out_path), "-"],
            input=svg_bytes, capture_output=True, check=True,
        )
    except FileNotFoundError:
        sys.exit("[generate_social_ogp] rsvg-convert が見つかりません。brew install librsvg")
    except subprocess.CalledProcessError as e:
        sys.exit(f"[generate_social_ogp] rsvg-convert failed: {e.stderr.decode()}")


def svg_to_jpg(svg_path: Path, out_path: Path) -> None:
    """SVG → PNG (tmp) → JPEG via rsvg-convert + sips (macOS)."""
    with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tmp:
        tmp_path = tmp.name
    try:
        subprocess.run(
            ["rsvg-convert", "-f", "png", "-w", "1200", "-h", "630", "-o", tmp_path, str(svg_path)],
            capture_output=True, check=True,
        )
        subprocess.run(
            ["sips", "-s", "format", "jpeg", tmp_path, "--out", str(out_path)],
            capture_output=True, check=True,
        )
    except FileNotFoundError as e:
        print(f"[generate_social_ogp] JPEG変換スキップ ({e})", file=sys.stderr)
    except subprocess.CalledProcessError as e:
        print(f"[generate_social_ogp] JPEG変換失敗: {e.stderr.decode()}", file=sys.stderr)
    finally:
        os.unlink(tmp_path) if os.path.exists(tmp_path) else None


def _xe(s: str) -> str:
    """Minimal XML/SVG text escaping."""
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


# ---------------------------------------------------------------------------
# Prefecture coordinates (for hero pin on dot-matrix Japan map)
# ---------------------------------------------------------------------------

_PREF_LATLNG: dict[str, tuple[float, float]] = {
    "北海道": (43.06, 141.35), "青森県": (40.82, 140.74), "岩手県": (39.70, 141.15),
    "宮城県": (38.27, 140.87), "秋田県": (39.72, 140.10), "山形県": (38.24, 140.36),
    "福島県": (37.75, 140.47), "茨城県": (36.34, 140.45), "栃木県": (36.57, 139.88),
    "群馬県": (36.39, 139.06), "埼玉県": (35.86, 139.65), "千葉県": (35.60, 140.12),
    "東京都": (35.69, 139.69), "神奈川県": (35.45, 139.64), "新潟県": (37.90, 139.02),
    "富山県": (36.70, 137.21), "石川県": (36.59, 136.63), "福井県": (36.07, 136.22),
    "山梨県": (35.66, 138.57), "長野県": (36.65, 138.18), "岐阜県": (35.39, 136.72),
    "静岡県": (34.98, 138.38), "愛知県": (35.18, 137.15), "三重県": (34.73, 136.51),
    "滋賀県": (35.00, 135.87), "京都府": (35.02, 135.76), "大阪府": (34.69, 135.50),
    "兵庫県": (34.69, 135.18), "奈良県": (34.69, 135.83), "和歌山県": (34.23, 135.17),
    "鳥取県": (35.50, 134.24), "島根県": (35.47, 133.06), "岡山県": (34.66, 133.93),
    "広島県": (34.40, 132.46), "山口県": (34.19, 131.47), "徳島県": (34.07, 134.56),
    "香川県": (34.34, 134.04), "愛媛県": (33.84, 132.77), "高知県": (33.56, 133.53),
    "福岡県": (33.61, 130.42), "佐賀県": (33.24, 130.30), "長崎県": (32.74, 129.87),
    "熊本県": (32.79, 130.74), "大分県": (33.24, 131.61), "宮崎県": (31.91, 131.42),
    "鹿児島県": (31.56, 130.56), "沖縄県": (26.21, 127.68),
}


def _latlon_to_hero_xy(lat: float, lng: float) -> tuple[float, float]:
    """Convert lat/lng to dot-matrix map hero pin pixel coords.

    Calibrated from BUILD_NOTES pin positions:
      hokkaido [32,2], sendai [28,8], tokyo [25,13], osaka [18,17], fukuoka [7,22]
    col = 1.856*lng + 0.350*lat - 246.78
    row = -0.695*lng - 1.205*lat + 153.10
    gx  = 688 + col*10 + 5
    gy  = 124 + row*(380/31) + (380/31)/2
    """
    col = max(0.0, min(39.0, 1.856 * lng + 0.350 * lat - 246.78))
    row = max(0.0, min(30.0, -0.695 * lng - 1.205 * lat + 153.10))
    ch = 380 / 31
    return round(688 + col * 10 + 5, 1), round(124 + row * ch + ch / 2, 1)


# ---------------------------------------------------------------------------
# Prefecture wire-frame map helpers
# ---------------------------------------------------------------------------

def _simplify_ring(ring: list, max_pts: int = 250) -> list:
    n = len(ring)
    if n <= max_pts:
        return ring
    step = max(2, n // max_pts)
    simplified = ring[::step]
    if simplified[0] != simplified[-1]:
        simplified.append(ring[-1])
    return simplified


def _load_pref_rings(pref: str) -> tuple[list, tuple]:
    """Load prefecture boundary polygon rings from cache or download.

    Returns (all_polygons, bounds) where:
      all_polygons: list of polygons; each polygon is [exterior_ring, *hole_rings]
      bounds: (min_lng, min_lat, max_lng, max_lat)
    """
    cache_path = PREF_BOUNDARY_DIR / f"{pref}.json"
    if cache_path.exists():
        data = json.loads(cache_path.read_text(encoding="utf-8"))
        return data["polygons"], tuple(data["bounds"])

    PREF_BOUNDARY_DIR.mkdir(parents=True, exist_ok=True)

    japan_cache = PREF_BOUNDARY_DIR / "_japan.geojson"
    if not japan_cache.exists():
        print("[generate_social_ogp] japan.geojson をダウンロード中…", file=sys.stderr)
        req = urllib.request.Request(
            _JAPAN_GEOJSON_URL, headers={"User-Agent": "pokefuta-ogp/1.0"},
        )
        with urllib.request.urlopen(req, timeout=60) as resp:
            japan_cache.write_bytes(resp.read())

    japan = json.loads(japan_cache.read_text(encoding="utf-8"))
    feature = next(
        (f for f in japan["features"] if f["properties"].get("nam_ja") == pref), None,
    )
    if not feature:
        raise RuntimeError(f"都道府県が見つかりません: {pref}")

    geom = feature["geometry"]
    all_polygons = [geom["coordinates"]] if geom["type"] == "Polygon" else geom["coordinates"]
    all_polygons = [[_simplify_ring(ring) for ring in poly] for poly in all_polygons]

    flat = [c for poly in all_polygons for ring in poly for c in ring]
    lngs = [c[0] for c in flat]
    lats = [c[1] for c in flat]
    bounds = (min(lngs), min(lats), max(lngs), max(lats))

    cache_path.write_text(
        json.dumps({"polygons": all_polygons, "bounds": list(bounds)}, separators=(",", ":")),
        encoding="utf-8",
    )
    return all_polygons, bounds


_MAP_PANEL_X, _MAP_PANEL_Y, _MAP_PANEL_W, _MAP_PANEL_H = 688, 124, 400, 380
_MAP_PAD = 22


def _geo_to_panel_xy(lng: float, lat: float, bounds: tuple) -> tuple[float, float]:
    """Project GeoJSON [lng, lat] into the SVG map panel pixel space."""
    min_lng, min_lat, max_lng, max_lat = bounds
    avail_w = _MAP_PANEL_W - 2 * _MAP_PAD
    avail_h = _MAP_PANEL_H - 2 * _MAP_PAD
    lng_range = max(max_lng - min_lng, 0.01)
    lat_range = max(max_lat - min_lat, 0.01)
    scale = min(avail_w / lng_range, avail_h / lat_range)
    map_w = lng_range * scale
    map_h = lat_range * scale
    x_off = _MAP_PANEL_X + _MAP_PAD + (avail_w - map_w) / 2
    y_off = _MAP_PANEL_Y + _MAP_PAD + (avail_h - map_h) / 2 + map_h
    return (
        round(x_off + (lng - min_lng) * scale, 1),
        round(y_off - (lat - min_lat) * scale, 1),
    )


def _manhole_zoom_bounds(manholes: list[dict], pref_bounds: tuple) -> tuple:
    """Compute view bounds centered on the manhole cluster.

    When manholes are tightly clustered (photos mode), zoom into them while
    keeping the view proportional.  Padding is 5× the cluster span so the
    prefecture outline provides context without overwhelming the thumbnails.
    """
    m_lngs = [m["lng"] for m in manholes]
    m_lats = [m["lat"] for m in manholes]
    lng_span = max(max(m_lngs) - min(m_lngs), 0.015)
    lat_span = max(max(m_lats) - min(m_lats), 0.015)
    # Keep aspect ratio consistent with a square-ish cluster view
    span = max(lng_span, lat_span) * 5.0
    cx = (min(m_lngs) + max(m_lngs)) / 2
    cy = (min(m_lats) + max(m_lats)) / 2
    # Clamp to prefecture extent so we don't zoom outside the polygon
    min_lng, min_lat, max_lng, max_lat = pref_bounds
    return (
        max(cx - span, min_lng),
        max(cy - span, min_lat),
        min(cx + span, max_lng),
        min(cy + span, max_lat),
    )


def _render_pref_wire_map(svg: str, pref: str, manholes: list[dict], theme: str) -> str:
    """Replace map panel with wire-frame prefecture boundary + manhole circles."""
    accent = _ACCENT_COLOR.get(theme, "#F2C24C")
    bright = _ACCENT_BRIGHT.get(theme, "#FFD86B")

    all_polygons, pref_bounds = _load_pref_rings(pref)

    use_photos = len(manholes) <= _WIRE_PHOTO_LIMIT
    # Zoom to manhole cluster for photo mode; use full prefecture for dot mode
    bounds = _manhole_zoom_bounds(manholes, pref_bounds) if use_photos else pref_bounds

    path_parts: list[str] = []
    for poly in all_polygons:
        d = ""
        for ring in poly:
            pts = [_geo_to_panel_xy(c[0], c[1], bounds) for c in ring]
            d += f"M{pts[0][0]} {pts[0][1]}"
            for x, y in pts[1:]:
                d += f"L{x} {y}"
            d += "Z"
        path_parts.append(
            f'<path d="{d}" fill="{accent}" fill-opacity="0.07" '
            f'stroke="{accent}" stroke-opacity="0.7" stroke-width="1.5" '
            f'stroke-linejoin="round" stroke-linecap="round"/>'
        )

    defs: list[str] = []
    circles: list[str] = []
    r = 18

    for m in manholes:
        x, y = _geo_to_panel_xy(m["lng"], m["lat"], bounds)
        mid = str(m.get("id", ""))
        img_path = MANHOLE_IMAGE_DIR / f"{mid}_latest.jpeg"
        if use_photos and mid and img_path.exists():
            clip_id = f"wmc{mid}"
            b64 = base64.b64encode(img_path.read_bytes()).decode("ascii")
            defs.append(
                f'<clipPath id="{clip_id}"><circle cx="{x}" cy="{y}" r="{r}"/></clipPath>'
            )
            circles.append(
                f'<circle cx="{x}" cy="{y}" r="{r + 2.5}" fill="#FFFFFF" opacity="0.9"/>'
                f'<image href="data:image/jpeg;base64,{b64}" '
                f'x="{x - r}" y="{y - r}" width="{r * 2}" height="{r * 2}" '
                f'clip-path="url(#{clip_id})" preserveAspectRatio="xMidYMid slice"/>'
            )
        else:
            circles.append(
                f'<circle cx="{x}" cy="{y}" r="4.5" fill="{bright}" opacity="0.92"/>'
            )

    defs_svg = f'<defs>{"".join(defs)}</defs>' if defs else ""
    new_group = (
        f'<g id="map-dots">{defs_svg}'
        f'{"".join(path_parts)}'
        f'{"".join(circles)}</g>'
    )
    svg = _replace_group(svg, "map-dots", new_group)
    svg = _replace_group(svg, "map-route", '<g id="map-route"></g>')
    return svg


# ---------------------------------------------------------------------------
# SVG mutation helpers
# ---------------------------------------------------------------------------

def _set_text(svg: str, element_id: str, content: str) -> str:
    """Replace text element content by id (assumes no nested tspan)."""
    return re.sub(
        rf'(<text[^>]*id="{element_id}"[^>]*>)[^<]*(</text>)',
        lambda m: m.group(1) + _xe(content) + m.group(2),
        svg,
    )


def _set_main_unit_x(svg: str, unit_x: int) -> str:
    """Update x attr on #main-unit text element."""
    idx = svg.find('id="main-unit"')
    if idx == -1:
        return svg
    tag_start = svg.rfind("<text", 0, idx)
    tag_end = svg.find(">", idx)
    if tag_start == -1 or tag_end == -1:
        return svg
    old_tag = svg[tag_start : tag_end + 1]
    new_tag = re.sub(r'\bx="[^"]*"', f'x="{unit_x}"', old_tag)
    return svg[:tag_start] + new_tag + svg[tag_end + 1 :]


def _set_hero_pin(svg: str, hx: float, hy: float) -> str:
    """Move teardrop hero-pin group to given SVG pixel coords."""
    idx = svg.find("M0 4C")
    if idx == -1:
        return svg
    g_start = svg.rfind("<g", 0, idx)
    g_end = svg.find(">", g_start)
    if g_start == -1 or g_end == -1:
        return svg
    old_tag = svg[g_start : g_end + 1]
    new_tag = re.sub(r"translate\([^)]+\)", f"translate({hx} {hy})", old_tag)
    return svg[:g_start] + new_tag + svg[g_end + 1 :]


def _replace_group(svg: str, group_id: str, new_content: str) -> str:
    """Replace an entire <g id="group_id">...</g> block with new_content."""
    idx = svg.find(f'id="{group_id}"')
    if idx == -1:
        return svg
    g_start = svg.rfind("<g", 0, idx)
    depth, i = 1, g_start + 3
    while i < len(svg) and depth > 0:
        if svg[i : i + 2] == "<g":
            depth += 1
            i += 2
        elif svg[i : i + 4] == "</g>":
            depth -= 1
            i += 4
        else:
            i += 1
    return svg[:g_start] + new_content + svg[i:]


def _replace_map_with_pref_dots(svg: str, manholes: list[dict], theme: str, map_pref: str = "") -> str:
    """Replace map-dots + map-route groups with prefecture manhole point map.

    When map_pref is provided, renders a GeoJSON wire-frame outline first.
    Falls back to scaled dot map on any error.
    """
    if not manholes:
        return svg

    if map_pref:
        try:
            return _render_pref_wire_map(svg, map_pref, manholes, theme)
        except Exception as e:
            print(f"[generate_social_ogp] ワイヤーマップ失敗（{map_pref}: {e}）、ドットで代替", file=sys.stderr)

    accent = _ACCENT_COLOR.get(theme, "#F2C24C")
    bright = _ACCENT_BRIGHT.get(theme, "#FFD86B")

    # Map panel coordinate space (from BUILD_NOTES)
    MAPX, MAPY, MAPW, MAPH = 688, 124, 400, 380
    PAD = 22

    lats = [m["lat"] for m in manholes]
    lngs = [m["lng"] for m in manholes]
    lat_c = (min(lats) + max(lats)) / 2
    lng_c = (min(lngs) + max(lngs)) / 2

    lat_range = max(max(lats) - min(lats), 0.08)
    lng_range = max(max(lngs) - min(lngs), 0.12)
    pad_factor = 0.18
    lat_min = lat_c - lat_range * (0.5 + pad_factor)
    lat_max = lat_c + lat_range * (0.5 + pad_factor)
    lng_min = lng_c - lng_range * (0.5 + pad_factor)
    lng_max = lng_c + lng_range * (0.5 + pad_factor)
    lat_range = lat_max - lat_min
    lng_range = lng_max - lng_min

    avail_w = MAPW - 2 * PAD
    avail_h = MAPH - 2 * PAD
    scale = min(avail_w / lng_range, avail_h / lat_range)
    map_w = lng_range * scale
    map_h = lat_range * scale
    x_off = MAPX + PAD + (avail_w - map_w) / 2
    y_off = MAPY + PAD + (avail_h - map_h) / 2 + map_h

    def to_xy(lat: float, lng: float) -> tuple[float, float]:
        return round(x_off + (lng - lng_min) * scale, 1), round(y_off - (lat - lat_min) * scale, 1)

    dots: list[str] = []
    for n, m in enumerate(manholes):
        x, y = to_xy(m["lat"], m["lng"])
        if n % 4 == 0:
            dots.append(f'<circle cx="{x}" cy="{y}" r="4.5" fill="{bright}" opacity="0.92"></circle>')
        else:
            dots.append(f'<circle cx="{x}" cy="{y}" r="3.2" fill="{accent}" opacity="0.55"></circle>')

    svg = _replace_group(svg, "map-dots", f'<g id="map-dots">{"".join(dots)}</g>')
    svg = _replace_group(svg, "map-route", '<g id="map-route"></g>')
    return svg


def _replace_chips_section(svg: str, chips: list[str], theme: str) -> str:
    """Replace entire chips group with new chip data using proper widths.

    Chip width formula: len(text)*21 + 42  (21px/char for Japanese + 15*2 pad + 12 dot+margin)
    """
    accent = _ACCENT_COLOR.get(theme, "#57E0BE")
    start_tag = '<g id="chips">'
    chips_start = svg.find(start_tag)
    if chips_start == -1:
        return svg

    # Find matching closing </g> by depth counting
    depth = 1
    i = chips_start + len(start_tag)
    while i < len(svg) and depth > 0:
        if svg[i] == "<":
            if svg[i : i + 4] == "</g>":
                depth -= 1
                i += 4
            elif svg[i : i + 2] == "<g":
                depth += 1
                i += 2
            else:
                i += 1
        else:
            i += 1
    chips_end = i

    new_chips = '<g id="chips">'
    x = 76
    for ci, chip_text in enumerate(chips[:6], 1):
        if not chip_text:
            continue
        chip_w = len(chip_text) * 21 + 42
        new_chips += (
            f'<g><rect id="chip-bg-{ci}" x="{x}" y="504" width="{chip_w}" height="38" rx="19" '
            f'fill="#FFFFFF" fill-opacity="0.06" stroke="{accent}" stroke-opacity="0.5"></rect>'
            f'<circle cx="{x + 14}" cy="523" r="3.2" fill="{accent}"></circle>'
            f'<text id="chip-{ci}" class="jp" x="{x + 25}" y="530" font-size="21" font-weight="700" fill="#EAF0FF">'
            f"{_xe(chip_text)}</text></g>"
        )
        x += chip_w + 11
    new_chips += "</g>"

    return svg[:chips_start] + new_chips + svg[chips_end:]


# ---------------------------------------------------------------------------
# NDJSON helper
# ---------------------------------------------------------------------------

def _load_pref_manholes(pref: str) -> list[dict]:
    """Load all manholes with lat/lng for a prefecture from NDJSON."""
    result = []
    if NDJSON.exists():
        for line in NDJSON.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            d = json.loads(line)
            if d.get("prefecture") == pref and d.get("lat") and d.get("lng"):
                result.append(d)
    return result


def _top_pokemons_for_pref(pref: str, n: int = 6) -> list[str]:
    counter: Counter = Counter()
    if NDJSON.exists():
        for line in NDJSON.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            d = json.loads(line)
            if d.get("prefecture") == pref:
                for p in d.get("pokemons", []):
                    counter[p] += 1
    return [p for p, _ in counter.most_common(n)]


# ---------------------------------------------------------------------------
# Design template renderer
# ---------------------------------------------------------------------------

def _render_design_template(theme: str, v: dict) -> str:
    """Load pokefuta_ogp_{theme}.svg and substitute content by element ID.

    Required keys in v: categoryLabel, titleLine1, titleLine2, kicker,
      mainNumber, mainUnit, chips (list[str] max 6), description, mapCaption.
    Optional: heroLat, heroLng (float) — relocates the teardrop hero pin.
    """
    tmpl_path = TEMPLATE_DIR / f"pokefuta_ogp_{theme}.svg"
    if not tmpl_path.exists():
        sys.exit(f"[generate_social_ogp] テンプレートが見つかりません: {tmpl_path}")

    svg = tmpl_path.read_text(encoding="utf-8")

    main_num = str(v.get("mainNumber", ""))
    svg = _set_text(svg, "cat-label",          v.get("categoryLabel", ""))
    svg = _set_text(svg, "title-1",            v.get("titleLine1", ""))
    svg = _set_text(svg, "title-2",            v.get("titleLine2", ""))
    svg = _set_text(svg, "num-kicker",         v.get("kicker", ""))
    svg = _set_text(svg, "main-number",        main_num)
    svg = _set_text(svg, "main-number-glow",   main_num)
    svg = _set_text(svg, "main-unit",          v.get("mainUnit", ""))
    svg = _set_text(svg, "description",        v.get("description", ""))
    svg = _set_text(svg, "map-caption",        v.get("mapCaption", ""))
    svg = _set_text(svg, "footer-name",        v.get("footerLabel", "ポケふたマップ"))
    svg = _set_text(svg, "footer-url",         v.get("footerUrl", "data.pokefuta.com"))

    # main-unit x: 74 + digit_count*70 + 14
    digits = len(main_num.lstrip("-+")) or 1
    svg = _set_main_unit_x(svg, 74 + digits * 70 + 14)

    # Chips: rebuild with correct widths
    svg = _replace_chips_section(svg, v.get("chips", []), theme)

    # Prefecture-specific dot map (overrides Japan dot matrix when present)
    manholes = v.get("manholes")
    map_pref = v.get("mapPref", "")
    if manholes:
        svg = _replace_map_with_pref_dots(svg, manholes, theme, map_pref)
    else:
        # Default: move teardrop hero pin to target lat/lng
        hero_lat = v.get("heroLat")
        hero_lng = v.get("heroLng")
        if hero_lat is not None and hero_lng is not None:
            hx, hy = _latlon_to_hero_xy(hero_lat, hero_lng)
            svg = _set_hero_pin(svg, hx, hy)

    return svg


# ---------------------------------------------------------------------------
# Per-type variable builders
# ---------------------------------------------------------------------------

def _vars_prefecture_rank(raw: dict) -> dict:
    pref = raw["pref"]
    manholes = _load_pref_manholes(pref)
    return {
        "categoryLabel": "RANKING",
        "titleLine1": f"{pref}の",
        "titleLine2": "ポケふた",
        "kicker": f"都道府県別ランキング 全国{raw['rank']}位",
        "mainNumber": str(raw["count"]),
        "mainUnit": "枚",
        "chips": _top_pokemons_for_pref(pref),
        "description": f"全国{raw['total']}枚中 {raw['percent']}%",
        "mapCaption": f"{pref}設置マップ",
        "manholes": manholes,
        "mapPref": pref,
    }


def _vars_pokemon_rank(raw: dict) -> dict:
    return {
        "categoryLabel": "RANKING",
        "titleLine1": raw["ja_name"],
        "titleLine2": "の設置数",
        "kicker": f"ポケモン別ランキング 全国{raw['rank']}位",
        "mainNumber": str(raw["count"]),
        "mainUnit": "枚",
        "chips": [],
        "description": f"{raw['city_count']}市区町村に設置",
        "mapCaption": "全国マップ",
    }


def _vars_travel_trivia(raw: dict) -> dict:
    ft = raw["fact_type"]
    v = raw["values"]
    base: dict = {
        "categoryLabel": "TRIVIA",
        "mainUnit": "",
        "chips": [],
        "description": "",
        "mapCaption": "全国マップ",
    }
    if ft == "total_count":
        base.update({
            "titleLine1": "全国ポケふた",
            "titleLine2": "設置総数",
            "kicker": "現在のデータより",
            "mainNumber": str(v["total"]),
            "mainUnit": "枚",
            "description": "全国ポケモンマンホール情報",
        })
    elif ft == "empty_prefs":
        base.update({
            "titleLine1": "ポケふた未設置の",
            "titleLine2": "都道府県",
            "kicker": f"{v['empty_count']}県が現在未設置",
            "mainNumber": str(v["empty_count"]),
            "mainUnit": "県",
            "chips": v.get("pref_names", [])[:6],
            "description": "設置エリア拡大を期待！",
        })
    elif ft == "regional_top":
        base.update({
            "titleLine1": v["region"],
            "titleLine2": "地方が最多",
            "kicker": f"全国{v['total']}枚中",
            "mainNumber": str(v["count"]),
            "mainUnit": "枚",
            "description": f"{v['region']}地方に集中",
        })
    elif ft == "pokemon_variety":
        base.update({
            "titleLine1": "登場ポケモン",
            "titleLine2": "種類数",
            "kicker": "全国集計",
            "mainNumber": str(v["species_count"]),
            "mainUnit": "種",
            "description": "多彩なポケモンが全国に",
        })
    elif ft == "pokemon_widest_spread":
        base.update({
            "titleLine1": v["ja_name"],
            "titleLine2": "が最多分布",
            "kicker": "設置市区町村 全国1位",
            "mainNumber": str(v["city_count"]),
            "mainUnit": "市区町村",
            "description": f"{v['ja_name']}は全国最多分布",
        })
    elif ft == "top3_ranking":
        top3 = v["top3"]
        base.update({
            "titleLine1": "都道府県別",
            "titleLine2": "TOP3",
            "kicker": f"1位: {top3[0]['pref']} {top3[0]['count']}枚",
            "mainNumber": str(top3[0]["count"]),
            "mainUnit": "枚",
            "chips": [
                f"①{top3[0]['pref']} {top3[0]['count']}枚",
                f"②{top3[1]['pref']} {top3[1]['count']}枚",
                f"③{top3[2]['pref']} {top3[2]['count']}枚",
            ],
            "description": "都道府県別ランキング",
        })
    elif ft == "first_pokefuta":
        base.update({
            "categoryLabel": "FIRST",
            "_theme": "first_pokefuta",
        })
    elif ft == "ibusuki_eevee_9":
        manholes = _load_pref_manholes("鹿児島県")
        base.update({
            "titleLine1": "イーブイ系",
            "titleLine2": "コンプリート",
            "kicker": "全国唯一・全9種が鹿児島県指宿市に集結",
            "mainNumber": str(v["count"]),
            "mainUnit": "枚",
            "chips": ["イーブイ", "シャワーズ", "ブースター", "サンダース", "エーフィ", "ブラッキー"],
            "description": f"鹿児島県{v['city']}に全9種が揃う全国唯一の場所",
            "manholes": manholes,
            "_theme": "ibusuki_eevee_complete",
        })
    return base


def _vars_rare_area(raw: dict) -> dict:
    pref = raw["pref"]
    lat, lng = _PREF_LATLNG.get(pref, (35.69, 139.69))
    percent = round(raw["count"] / max(raw["total"], 1) * 100, 1)
    manholes = _load_pref_manholes(pref)

    base = {
        "categoryLabel": "RARE",
        "titleLine1": f"{pref}の",
        "titleLine2": "ポケふた",
        "kicker": "まだ少ない地域",
        "mainNumber": str(raw["count"]),
        "mainUnit": "枚",
        "chips": [],
        "description": f"全国{raw['total']}枚中 {percent}%",
        "mapCaption": f"{pref}設置マップ",
        "manholes": manholes,
        "mapPref": pref,
        "heroLat": lat,
        "heroLng": lng,
    }

    # Detect "all same base pokemon" variant family (e.g. ニャース3兄弟)
    if 2 <= len(manholes) <= 5:
        first_pokemons = [(m.get("pokemons") or [""])[0] for m in manholes]
        base_names = {_poke_base_name(p) for p in first_pokemons if p}

        if len(base_names) == 1:
            base_poke = list(base_names)[0]
            pref_short = pref[:-1] if pref[-1] in "都道府県" else pref
            first_city = manholes[0].get("city", "") if manholes else ""
            # Build kicker from the actual variant prefixes present
            found_pfx = [pfx for pfx in _REGION_PREFIXES if any(p.startswith(pfx) for p in first_pokemons)]
            has_normal = any(not any(p.startswith(pfx) for pfx in _REGION_PREFIXES) for p in first_pokemons if p)
            regions = (["通常"] if has_normal else []) + found_pfx
            kicker = "・".join(regions) + " 地域変種がひとつの市に集合"
            base.update({
                "titleLine1": f"{pref_short}の{raw['count']}枚、",
                "titleLine2": f"全部{base_poke}",
                "kicker": kicker,
                "description": f"{pref}{first_city}",
                "chips": first_pokemons,
                "pokeLabels":    [_poke_short_label(p) for p in first_pokemons],
                "pokeSubLabels": [_poke_sub_label(p)   for p in first_pokemons],
                "stampText":  "地域変種\nコンプリート",
                "footerCta":  f"全国{raw['total']}枚から、次の旅先を探す",
                "_theme": "rare_few",
            })
            # 佐賀-specific: ニャース × 気球 overrides
            if pref == "佐賀県" and base_poke == "ニャース":
                base.update({
                    "kicker": "しかも全部、気球デザイン。",
                    "categoryLabel": "佐賀市限定",
                    "stampText": "佐賀市\n限定",
                    "hasBalloons": True,
                })

    return base


def _vars_no_photo(raw: dict) -> dict:
    pref = raw["pref"]
    lat, lng = _PREF_LATLNG.get(pref, (35.69, 139.69))
    manholes = _load_pref_manholes(pref)
    return {
        "categoryLabel": "RARE",
        "titleLine1": f"{pref}の",
        "titleLine2": "写真募集中",
        "kicker": "写真未投稿マンホール",
        "mainNumber": str(raw["no_photo_count"]),
        "mainUnit": "枚",
        "chips": [],
        "description": f"設置{raw['total_count']}枚中 {raw['no_photo_count']}枚が未投稿",
        "mapCaption": f"{pref}マップ",
        "manholes": manholes,
        "mapPref": pref,
        "heroLat": lat,
        "heroLng": lng,
    }


def _vars_latest_photo(raw: dict) -> dict:
    pokemon_list = raw.get("pokemon_list", [raw.get("pokemon", "")])
    pokemon_str = " × ".join(p for p in pokemon_list if p)
    date_str = raw.get("created_at", "")[:10].replace("-", "/")
    return {
        "_theme": "latest_photo",
        "pref":         raw.get("pref", ""),
        "city":         raw.get("city", ""),
        "pokemon":      pokemon_str,
        "date":         date_str,
        "display_name": raw.get("display_name", ""),
        "photo_rank":   raw.get("photo_rank", "recent"),
        "image_url":    raw.get("image_url", ""),
    }


def _vars_michineki(raw: dict) -> dict:
    all_pokemons = [p for m in raw["manholes"] for p in m.get("pokemons", [])]
    chips = [p for p, _ in Counter(all_pokemons).most_common(6)]
    station_name = raw["station_name"]
    if len(station_name) > 12:
        station_name = station_name[:12] + "…"
    return {
        "categoryLabel": "RANKING",
        "titleLine1": station_name,
        "titleLine2": "道の駅チャレンジ",
        "kicker": f"半径{raw['radius_km']}km以内",
        "mainNumber": str(raw["manhole_count"]),
        "mainUnit": "枚",
        "chips": chips,
        "description": f"{raw['pref']}のポケふた",
        "mapCaption": "設置エリアマップ",
        "heroLat": raw["lat"],
        "heroLng": raw["lng"],
    }


def _vars_remote_island(raw: dict) -> dict:
    return {
        "categoryLabel": "RARE",
        "titleLine1": raw["island_name"],
        "titleLine2": "のポケふた",
        "kicker": f"{raw['pref']} {raw['city']}",
        "mainNumber": str(raw["manhole_count"]),
        "mainUnit": "枚",
        "chips": raw.get("top_pokemons", [])[:6],
        "description": "離島のポケモンマンホール",
        "mapCaption": "日本マップ",
    }


def _render_rare_few_horizontal(v: dict) -> str:
    """Render rare_area posts with ≤5 manholes: 3-photo horizontal card layout.

    Photos are evenly distributed across the right panel.
    Pokemon name + variant label shown below each photo.
    """
    tmpl_path = TEMPLATE_DIR / "pokefuta_ogp_rare.svg"
    svg = tmpl_path.read_text(encoding="utf-8")

    # --- Left-side text ---
    main_num = str(v.get("mainNumber", ""))
    cat_label = v.get("categoryLabel", "RARE")
    svg = _set_text(svg, "cat-label",        cat_label)
    svg = _set_text(svg, "title-1",          v.get("titleLine1", ""))
    svg = _set_text(svg, "title-2",          v.get("titleLine2", ""))
    svg = _set_text(svg, "num-kicker",       v.get("kicker", ""))
    svg = _set_text(svg, "main-number",      main_num)
    svg = _set_text(svg, "main-number-glow", main_num)
    svg = _set_text(svg, "main-unit",        v.get("mainUnit", "枚"))
    svg = _set_text(svg, "description",      v.get("description", ""))
    svg = _set_text(svg, "map-caption",      "")
    svg = _set_text(svg, "footer-name",      "ポケふたマップ")
    svg = _set_text(svg, "footer-url",       "data.pokefuta.com")
    svg = _set_text(svg, "footer-note",      v.get("footerCta", "全国470枚から、次の旅先を探す"))
    svg = _set_main_unit_x(svg, 74 + len(main_num) * 70 + 14)
    svg = _replace_chips_section(svg, v.get("chips", []), "rare")
    if cat_label != "RARE":
        # Approximate badge width: text_x(114) - rect_x(76) + JP char width(19) × chars + padding(16)
        badge_w = max(96, 38 + len(cat_label) * 19 + 16)
        svg = svg.replace(
            'x="76" y="84" width="96" height="44" rx="22" fill="#FF9466" fill-opacity="0.14"',
            f'x="76" y="84" width="{badge_w}" height="44" rx="22" fill="#FF9466" fill-opacity="0.14"',
        )

    accent = "#FF9466"
    bright = "#FFB088"
    gold = "#FFD86B"

    manholes     = v.get("manholes", [])
    poke_labels  = v.get("pokeLabels", [])
    poke_subs    = v.get("pokeSubLabels", [])
    n = max(len(manholes), 1)

    defs: list[str] = []
    elems: list[str] = []

    # Dim prefecture wireframe as background texture
    pref = v.get("mapPref", "")
    if pref:
        try:
            all_polys, bounds = _load_pref_rings(pref)
            for poly in all_polys:
                d = ""
                for ring in poly:
                    pts = [_geo_to_panel_xy(c[0], c[1], bounds) for c in ring]
                    d += f"M{pts[0][0]} {pts[0][1]}"
                    for x, y in pts[1:]:
                        d += f"L{x} {y}"
                    d += "Z"
                elems.append(
                    f'<path d="{d}" fill="{accent}" fill-opacity="0.05" '
                    f'stroke="{bright}" stroke-opacity="0.14" stroke-width="0.8"/>'
                )
        except Exception as e:
            print(f"[generate_social_ogp] 背景マップスキップ: {e}", file=sys.stderr)

    # Hot air balloons above each photo (佐賀 ニャース variant)
    if v.get("hasBalloons"):
        PANEL_X_B, PANEL_W_B = 648, 480
        bsec_w = PANEL_W_B / n
        BCY, BRX, BRY = 132, 19, 26
        for i in range(n):
            bcx = round(PANEL_X_B + bsec_w * (i + 0.5), 1)
            brope_y = BCY + BRY           # 158
            bgond_y = brope_y + 14         # 172
            bcid = f"bclip{i}"
            defs.append(
                f'<clipPath id="{bcid}"><ellipse cx="{bcx}" cy="{BCY}" rx="{BRX}" ry="{BRY}"/></clipPath>'
            )
            elems.extend([
                # Envelope fill
                f'<ellipse cx="{bcx}" cy="{BCY}" rx="{BRX}" ry="{BRY}" fill="#F4A040" stroke="#C47820" stroke-width="1.5"/>',
                # Top red cap
                f'<path d="M{bcx-BRX},{BCY} Q{bcx},{BCY - int(BRY*1.25)} {bcx+BRX},{BCY} Z" '
                f'fill="#CC2200" opacity="0.62" clip-path="url(#{bcid})"/>',
                # Vertical stripe lines
                f'<line x1="{bcx - BRX//3}" y1="{BCY - BRY}" x2="{bcx - BRX//3}" y2="{BCY + BRY}" '
                f'stroke="#FFE070" stroke-width="1.3" clip-path="url(#{bcid})" opacity="0.75"/>',
                f'<line x1="{bcx + BRX//3}" y1="{BCY - BRY}" x2="{bcx + BRX//3}" y2="{BCY + BRY}" '
                f'stroke="#FFE070" stroke-width="1.3" clip-path="url(#{bcid})" opacity="0.75"/>',
                # Ropes
                f'<line x1="{bcx - BRX + 5}" y1="{brope_y}" x2="{bcx - 9}" y2="{bgond_y}" stroke="#B8902A" stroke-width="1.2"/>',
                f'<line x1="{bcx + BRX - 5}" y1="{brope_y}" x2="{bcx + 9}" y2="{bgond_y}" stroke="#B8902A" stroke-width="1.2"/>',
                # Gondola
                f'<rect x="{bcx - 11}" y="{bgond_y}" width="22" height="10" rx="2" fill="#7A4820" stroke="#5A3410" stroke-width="1"/>',
            ])

    # Photo row: divide panel into N equal sections
    PANEL_X, PANEL_W = 648, 480
    section_w = PANEL_W / n
    PHOTO_Y  = 262
    LABEL_Y  = 340
    SUB_Y    = 362
    R = 57

    for i, m in enumerate(manholes):
        cx = round(PANEL_X + section_w * (i + 0.5), 1)
        mid = str(m.get("id", ""))
        img_path = MANHOLE_IMAGE_DIR / f"{mid}_latest.jpeg"
        label = poke_labels[i] if i < len(poke_labels) else ""
        sub   = poke_subs[i]   if i < len(poke_subs)   else ""

        if mid and img_path.exists():
            cid = f"rfw{mid}"
            b64 = base64.b64encode(img_path.read_bytes()).decode("ascii")
            defs.append(f'<clipPath id="{cid}"><circle cx="{cx}" cy="{PHOTO_Y}" r="{R}"/></clipPath>')
            elems.append(
                f'<circle cx="{cx}" cy="{PHOTO_Y}" r="{R + 3}" fill="#FFFFFF" opacity="0.88"/>'
                f'<image href="data:image/jpeg;base64,{b64}" '
                f'x="{cx - R}" y="{PHOTO_Y - R}" width="{R * 2}" height="{R * 2}" '
                f'clip-path="url(#{cid})" preserveAspectRatio="xMidYMid slice"/>'
            )
        else:
            elems.append(f'<circle cx="{cx}" cy="{PHOTO_Y}" r="{R}" fill="{bright}" opacity="0.5"/>')

        if label:
            elems.append(
                f'<text class="jp" x="{cx}" y="{LABEL_Y}" text-anchor="middle" '
                f'font-size="20" font-weight="800" fill="{gold}">{_xe(label)}</text>'
            )
        if sub:
            elems.append(
                f'<text class="jp" x="{cx}" y="{SUB_Y}" text-anchor="middle" '
                f'font-size="14" font-weight="600" fill="#B3A9D6" opacity="0.85">{_xe(sub)}</text>'
            )

    # Stamp rendered last inside map-dots so it draws on top of balloons
    stamp_text = v.get("stampText", "地域変種\nコンプリート")
    line1, _, line2 = stamp_text.partition("\n")
    elems.append(
        f'<g transform="translate(1038 132) rotate(-10)">'
        f'<circle cx="0" cy="0" r="60" fill="#120C36" fill-opacity="0.55" '
        f'stroke="{bright}" stroke-width="3" stroke-dasharray="8 5"/>'
        f'<text class="jp" x="0" y="-8" text-anchor="middle" font-size="16" '
        f'font-weight="900" fill="{bright}">{_xe(line1)}</text>'
        f'<text class="jp" x="0" y="22" text-anchor="middle" font-size="16" '
        f'font-weight="900" fill="#FFFFFF">{_xe(line2)}</text>'
        f'</g>'
    )

    defs_svg = f'<defs>{"".join(defs)}</defs>' if defs else ""
    svg = _replace_group(svg, "map-dots",  f'<g id="map-dots">{defs_svg}{"".join(elems)}</g>')
    svg = _replace_group(svg, "map-route", '<g id="map-route"></g>')
    svg = _replace_group(svg, "map-caption-pill", '<g id="map-caption-pill"></g>')
    svg = _replace_group(svg, "stamp", '<g id="stamp"></g>')

    return svg


def _render_ibusuki_eevee_complete(v: dict) -> str:
    """Render ibusuki_eevee_9 OGP: circular manhole photo arrangement.

    Center: Eevee.  Outer ring (clockwise from top): 8 evolutions.
    Dim Ibusuki peninsula wireframe as background texture.
    """
    tmpl_path = TEMPLATE_DIR / "pokefuta_ogp_rare.svg"
    svg = tmpl_path.read_text(encoding="utf-8")

    # --- Left-side text ---
    main_num = str(v.get("mainNumber", "9"))
    svg = _set_text(svg, "cat-label",        "COMPLETE")
    svg = _set_text(svg, "title-1",          v.get("titleLine1", "イーブイ系"))
    svg = _set_text(svg, "title-2",          v.get("titleLine2", "コンプリート"))
    svg = _set_text(svg, "num-kicker",       v.get("kicker", "全9種 鹿児島県指宿市に集結"))
    svg = _set_text(svg, "main-number",      main_num)
    svg = _set_text(svg, "main-number-glow", main_num)
    svg = _set_text(svg, "main-unit",        "枚")
    svg = _set_text(svg, "description",      v.get("description", ""))
    svg = _set_text(svg, "map-caption",      "鹿児島県 指宿市")
    svg = _set_text(svg, "footer-name",      "ポケふたマップ")
    svg = _set_text(svg, "footer-url",       "data.pokefuta.com")
    svg = _set_main_unit_x(svg, 74 + 1 * 70 + 14)
    svg = _replace_chips_section(svg, v.get("chips", []), "rare")
    # Widen category badge rect for "COMPLETE"
    svg = svg.replace(
        'x="76" y="84" width="96" height="44" rx="22" fill="#FF9466" fill-opacity="0.14"',
        'x="76" y="84" width="184" height="44" rx="22" fill="#FF9466" fill-opacity="0.14"',
    )

    # --- Manhole ordering: Eevee center, 8 evolutions clockwise from top ---
    _OUTER_ORDER = [
        "シャワーズ", "ブースター", "サンダース", "エーフィ",
        "ブラッキー", "リーフィア", "グレイシア", "ニンフィア",
    ]

    def first_pokemon(m: dict) -> str:
        return (m.get("pokemons") or [""])[0]

    manholes = v.get("manholes", [])
    center_m = next((m for m in manholes if first_pokemon(m) == "イーブイ"), None)
    remaining = [m for m in manholes if first_pokemon(m) != "イーブイ"]
    outer_ms: list[dict] = []
    pool = list(remaining)
    for name in _OUTER_ORDER:
        match = next((m for m in pool if first_pokemon(m) == name), None)
        if match:
            outer_ms.append(match)
            pool.remove(match)
    outer_ms.extend(pool)

    # --- Circle geometry ---
    CX, CY = 888, 278
    OUTER_R = 143   # distance: center → outer photo center
    R_CENTER = 62   # Eevee photo radius
    R_OUTER = 44    # evolution photo radius
    bright = "#FFB088"
    gold = "#FFD86B"

    defs: list[str] = []
    elems: list[str] = []

    # Ibusuki peninsula wireframe as dim background (Satsuma Peninsula bbox)
    try:
        all_polys, _ = _load_pref_rings("鹿児島県")
        IB_BOUNDS = (130.40, 31.00, 131.00, 31.70)
        min_lng, min_lat, max_lng, max_lat = IB_BOUNDS
        PX, PY, PW, PH, IPAD = 648, 84, 480, 446, 28
        avail_w = PW - 2 * IPAD
        avail_h = PH - 2 * IPAD
        ib_scale = min(avail_w / (max_lng - min_lng), avail_h / (max_lat - min_lat))
        ib_mw = (max_lng - min_lng) * ib_scale
        ib_mh = (max_lat - min_lat) * ib_scale
        ib_xoff = PX + IPAD + (avail_w - ib_mw) / 2
        ib_yoff = PY + IPAD + (avail_h - ib_mh) / 2 + ib_mh

        def ib_xy(lng: float, lat: float) -> tuple[float, float]:
            return (
                round(ib_xoff + (lng - min_lng) * ib_scale, 1),
                round(ib_yoff - (lat - min_lat) * ib_scale, 1),
            )

        for poly in all_polys:
            d = ""
            for ring in poly:
                pts = [ib_xy(c[0], c[1]) for c in ring]
                d += f"M{pts[0][0]} {pts[0][1]}"
                for x, y in pts[1:]:
                    d += f"L{x} {y}"
                d += "Z"
            elems.append(
                f'<path d="{d}" fill="#FF9466" fill-opacity="0.03" '
                f'stroke="{bright}" stroke-opacity="0.12" stroke-width="0.8"/>'
            )
    except Exception as e:
        print(f"[generate_social_ogp] 指宿背景マップスキップ: {e}", file=sys.stderr)

    # Outer completion ring (dashed circle around all photos)
    ring_r = OUTER_R + R_OUTER + 10
    elems.append(
        f'<circle cx="{CX}" cy="{CY}" r="{ring_r}" fill="none" '
        f'stroke="{bright}" stroke-width="1.5" stroke-opacity="0.28" '
        f'stroke-dasharray="5 9"/>'
    )

    # Ray lines: center → outer photo positions
    for i in range(8):
        angle = math.radians(-90 + i * 45)
        ox = round(CX + OUTER_R * math.cos(angle), 1)
        oy = round(CY + OUTER_R * math.sin(angle), 1)
        elems.append(
            f'<line x1="{CX}" y1="{CY}" x2="{ox}" y2="{oy}" '
            f'stroke="{bright}" stroke-width="1" stroke-opacity="0.18" stroke-dasharray="4 7"/>'
        )

    # Outer photos (8 evolutions, clockwise from top)
    for i, m in enumerate(outer_ms[:8]):
        angle = math.radians(-90 + i * 45)
        ox = round(CX + OUTER_R * math.cos(angle), 1)
        oy = round(CY + OUTER_R * math.sin(angle), 1)
        mid = str(m.get("id", ""))
        img_path = MANHOLE_IMAGE_DIR / f"{mid}_latest.jpeg"
        if mid and img_path.exists():
            cid = f"eec{mid}"
            b64 = base64.b64encode(img_path.read_bytes()).decode("ascii")
            defs.append(f'<clipPath id="{cid}"><circle cx="{ox}" cy="{oy}" r="{R_OUTER}"/></clipPath>')
            elems.append(
                f'<circle cx="{ox}" cy="{oy}" r="{R_OUTER + 2.5}" fill="#FFFFFF" opacity="0.85"/>'
                f'<image href="data:image/jpeg;base64,{b64}" '
                f'x="{ox - R_OUTER}" y="{oy - R_OUTER}" '
                f'width="{R_OUTER * 2}" height="{R_OUTER * 2}" '
                f'clip-path="url(#{cid})" preserveAspectRatio="xMidYMid slice"/>'
            )
        else:
            elems.append(f'<circle cx="{ox}" cy="{oy}" r="{R_OUTER}" fill="{bright}" opacity="0.5"/>')

    # Center photo (Eevee) — larger, gold ring
    if center_m:
        mid = str(center_m.get("id", ""))
        img_path = MANHOLE_IMAGE_DIR / f"{mid}_latest.jpeg"
        if mid and img_path.exists():
            cid = f"eec{mid}"
            b64 = base64.b64encode(img_path.read_bytes()).decode("ascii")
            defs.append(f'<clipPath id="{cid}"><circle cx="{CX}" cy="{CY}" r="{R_CENTER}"/></clipPath>')
            elems.append(
                f'<circle cx="{CX}" cy="{CY}" r="{R_CENTER + 4}" fill="#FFFFFF" opacity="0.95"/>'
                f'<image href="data:image/jpeg;base64,{b64}" '
                f'x="{CX - R_CENTER}" y="{CY - R_CENTER}" '
                f'width="{R_CENTER * 2}" height="{R_CENTER * 2}" '
                f'clip-path="url(#{cid})" preserveAspectRatio="xMidYMid slice"/>'
                f'<circle cx="{CX}" cy="{CY}" r="{R_CENTER + 4}" '
                f'fill="none" stroke="{gold}" stroke-width="3" opacity="0.95"/>'
            )

    # Replace map-dots and map-route
    defs_svg = f'<defs>{"".join(defs)}</defs>' if defs else ""
    svg = _replace_group(svg, "map-dots", f'<g id="map-dots">{defs_svg}{"".join(elems)}</g>')
    svg = _replace_group(svg, "map-route", '<g id="map-route"></g>')

    # Replace RARE stamp → ALL 9 badge (upper-right, clear of the photo ring)
    new_stamp = (
        '<g id="stamp" transform="translate(1068 122)">'
        f'<circle cx="0" cy="0" r="50" fill="#120C36" fill-opacity="0.65" '
        f'stroke="{bright}" stroke-width="3" stroke-dasharray="8 5"/>'
        f'<text class="mono" x="0" y="-5" text-anchor="middle" font-size="11" '
        f'font-weight="900" letter-spacing="0.18em" fill="{bright}">ALL</text>'
        f'<text class="en" x="0" y="28" text-anchor="middle" font-size="36" '
        f'font-weight="900" fill="#FFFFFF">9</text>'
        '</g>'
    )
    svg = _replace_group(svg, "stamp", new_stamp)

    return svg


def _render_latest_photo_template(v: dict) -> str:
    """Render latest_photo.svg by mustache-style {{KEY}} substitution."""
    tmpl_path = TEMPLATE_DIR / "latest_photo.svg"
    if not tmpl_path.exists():
        sys.exit(f"[generate_social_ogp] テンプレートが見つかりません: {tmpl_path}")
    svg = tmpl_path.read_text(encoding="utf-8")

    svg = svg.replace("{{PREF}}",    _xe(v.get("pref", "")))
    svg = svg.replace("{{CITY}}",    _xe(v.get("city", "")))
    svg = svg.replace("{{POKEMON}}", _xe(v.get("pokemon", "")))
    svg = svg.replace("{{DATE}}",    _xe(v.get("date", "")))

    image_url = v.get("image_url", "")
    photo_el = ""
    if image_url:
        try:
            with urllib.request.urlopen(image_url, timeout=15) as resp:
                b64 = base64.b64encode(resp.read()).decode("ascii")
            photo_el = (
                f'<image x="770" y="157" width="310" height="310" '
                f'clip-path="url(#photoClip)" preserveAspectRatio="xMidYMid slice" '
                f'href="data:image/jpeg;base64,{b64}"/>'
            )
        except Exception as e:
            print(f"[generate_social_ogp] 写真取得スキップ: {e}", file=sys.stderr)

    svg = svg.replace("{{PHOTO_ELEMENT}}", photo_el)
    return svg


def _vars_pref_trivia(raw: dict) -> dict:
    v = raw["values"]
    pref = v.get("prefecture", "")
    pokemon = v.get("pokemon", "")
    return {
        "categoryLabel": "TRIVIA",
        "titleLine1": f"{pref}の",
        "titleLine2": "応援ポケモン",
        "kicker": "都道府県キャラクター",
        "mainNumber": pokemon,
        "mainUnit": "",
        "chips": [],
        "description": v.get("summary", f"{pref}のポケモンマンホール"),
        "mapCaption": f"{pref}のポケふた",
    }


_DESIGN_THEME: dict[str, str] = {
    "prefecture_rank": "ranking",
    "pokemon_rank":    "ranking",
    "travel_trivia":   "trivia",
    "pref_trivia":     "trivia",
    "rare_area":       "rare",
    "no_photo":        "rare",
    "latest_photo":    "latest_photo",
    "michineki":       "ranking",
    "remote_island":   "rare",
}

_DESIGN_VAR_BUILDERS = {
    "prefecture_rank": _vars_prefecture_rank,
    "pokemon_rank":    _vars_pokemon_rank,
    "travel_trivia":   _vars_travel_trivia,
    "pref_trivia":     _vars_pref_trivia,
    "rare_area":       _vars_rare_area,
    "no_photo":        _vars_no_photo,
    "latest_photo":    _vars_latest_photo,
    "michineki":       _vars_michineki,
    "remote_island":   _vars_remote_island,
}


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    for path in (DAILY_JSON, CANDIDATES_JSON):
        if not path.exists():
            sys.exit(
                f"[generate_social_ogp] {path.name} が見つかりません。先に /social-post を実行してください。"
            )

    daily = json.loads(DAILY_JSON.read_text(encoding="utf-8"))
    post_id = daily["id"]
    post_type = daily["type"]

    candidates = json.loads(CANDIDATES_JSON.read_text(encoding="utf-8"))
    candidate = next((c for c in candidates if c["id"] == post_id), None)
    if candidate is None:
        sys.exit(f"[generate_social_ogp] candidates に id={post_id} が見つかりません。")

    raw = candidate["raw_data"]

    theme = _DESIGN_THEME.get(post_type)
    var_builder = _DESIGN_VAR_BUILDERS.get(post_type)
    if theme is None or var_builder is None:
        sys.exit(f"[generate_social_ogp] 未対応タイプ: {post_type}")

    vars_dict = var_builder(raw)
    theme = vars_dict.pop("_theme", theme)
    print(f"[generate_social_ogp] {post_type} → {theme} テンプレートで生成中…")
    if theme == "latest_photo":
        svg_text = _render_latest_photo_template(vars_dict)
    elif theme == "ibusuki_eevee_complete":
        svg_text = _render_ibusuki_eevee_complete(vars_dict)
    elif theme == "rare_few":
        svg_text = _render_rare_few_horizontal(vars_dict)
    else:
        svg_text = _render_design_template(theme, vars_dict)

    OUTPUT_SVG.write_text(svg_text, encoding="utf-8")
    print(f"[generate_social_ogp] SVG → {OUTPUT_SVG}")

    svg_to_jpg(OUTPUT_SVG, OUTPUT_JPG)
    print(f"[generate_social_ogp] JPG → {OUTPUT_JPG}")

    svg_to_png(svg_text.encode("utf-8"), OUTPUT_PNG)
    print(f"[generate_social_ogp] PNG → {OUTPUT_PNG}")


if __name__ == "__main__":
    main()
