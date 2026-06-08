#!/usr/bin/env python3
"""Generate social post image (SVG + JPEG) and OGP PNG for today's post.

For `prefecture_rank`: builds a rich dark-theme SVG with prefecture map,
manhole photo thumbnails, and Pokémon stats — no template file needed.
For all other types: substitutes placeholders in docs/ogp_template/{type}.svg.

Outputs:
  docs/social-post-image.svg  — full-resolution SVG (all types)
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
import subprocess
import sys
import tempfile
import urllib.error
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
IMAGE_DIR = ROOT / "dataset" / "manhole" / "image"
NDJSON = ROOT / "pokefuta.ndjson"

GEOJSON_URL = "https://raw.githubusercontent.com/dataofjapan/land/master/japan.geojson"


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
# GeoJSON / RDP helpers
# ---------------------------------------------------------------------------

def _fetch_prefecture_outline(pref_name: str) -> list[list[float]]:
    """Return simplified [lng, lat] polygon for the given prefecture."""
    try:
        data = json.loads(urllib.request.urlopen(GEOJSON_URL, timeout=10).read())
    except (urllib.error.URLError, OSError) as e:
        print(f"[generate_social_ogp] GeoJSON取得失敗 ({e})", file=sys.stderr)
        return []
    feat = next(
        (f for f in data["features"] if f["properties"].get("nam_ja") == pref_name),
        None,
    )
    if feat is None:
        return []
    geom = feat["geometry"]
    coords = geom["coordinates"]
    if geom["type"] == "MultiPolygon":
        main_ring = sorted(coords, key=lambda p: len(p[0]), reverse=True)[0][0]
    else:
        main_ring = coords[0]  # Polygon: outer ring
    return _rdp(main_ring, 0.011)


def _rdp(pts: list, eps: float) -> list:
    if len(pts) < 3:
        return pts
    def _dist(p, a, b):
        ax, ay = a; bx, by = b; px, py = p
        dx, dy = bx - ax, by - ay
        if dx == 0 and dy == 0:
            return math.hypot(px - ax, py - ay)
        t = max(0.0, min(1.0, ((px - ax) * dx + (py - ay) * dy) / (dx * dx + dy * dy)))
        return math.hypot(px - (ax + t * dx), py - (ay + t * dy))
    dm, idx = 0.0, 0
    for i in range(1, len(pts) - 1):
        d = _dist(pts[i], pts[0], pts[-1])
        if d > dm:
            dm, idx = d, i
    if dm > eps:
        return _rdp(pts[: idx + 1], eps)[:-1] + _rdp(pts[idx:], eps)
    return [pts[0], pts[-1]]


# ---------------------------------------------------------------------------
# Prefecture-rank rich SVG builder
# ---------------------------------------------------------------------------

def _build_prefecture_rank_svg(raw: dict) -> str:
    pref: str = raw["pref"]
    count: int = raw["count"]
    total: int = raw["total"]
    rank: int = raw["rank"]
    percent: float = raw["percent"]

    # -- Prefecture outline ---------------------------------------------------
    outline_pts = _fetch_prefecture_outline(pref)

    # -- Manhole data for this prefecture ------------------------------------
    all_manholes: list[dict] = []
    if NDJSON.exists():
        for line in NDJSON.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            d = json.loads(line)
            if d.get("prefecture") == pref and d.get("lat") and d.get("lng"):
                all_manholes.append(d)

    # Pokemon stats
    pokemon_counter: Counter = Counter()
    for m in all_manholes:
        for p in m.get("pokemons", []):
            pokemon_counter[p] += 1
    top_pokemon = pokemon_counter.most_common(2)      # [(name, count), ...]
    other_pokemon = [p for p, _ in pokemon_counter.most_common(20)
                     if p not in {t[0] for t in top_pokemon}][:10]

    # Pick photo manholes (up to 8 with local images, spread geographically)
    image_ids = {f.stem.replace("_latest", "") for f in IMAGE_DIR.glob("*_latest.jpeg")}
    photo_candidates = [m for m in all_manholes if str(m["id"]) in image_ids]
    photo_manholes = _pick_spread(photo_candidates, n=8)

    # -- Coordinate system ---------------------------------------------------
    # Right panel: x 585..1185 (600 px wide), y 30..595 (565 px tall)
    PANEL_X, PANEL_Y, PANEL_W, PANEL_H = 585, 30, 600, 565
    PAD = 40

    if outline_pts:
        lngs = [p[0] for p in outline_pts]
        lats = [p[1] for p in outline_pts]
    else:
        lngs = [m["lng"] for m in all_manholes] or [130.0, 146.0]
        lats = [m["lat"] for m in all_manholes] or [30.0, 46.0]

    lng_min, lng_max = min(lngs), max(lngs)
    lat_min, lat_max = min(lats), max(lats)
    lng_range = max(lng_max - lng_min, 0.1)
    lat_range = max(lat_max - lat_min, 0.1)

    avail_w = PANEL_W - 2 * PAD
    avail_h = PANEL_H - 2 * PAD
    scale = min(avail_w / lng_range, avail_h / lat_range)
    map_w = lng_range * scale
    map_h = lat_range * scale
    x_off = PANEL_X + PAD + (avail_w - map_w) / 2
    y_off = PANEL_Y + PAD + (avail_h - map_h) / 2 + map_h

    def to_svg(lat: float, lng: float) -> tuple[float, float]:
        x = x_off + (lng - lng_min) * scale
        y = y_off - (lat - lat_min) * scale
        return round(x, 1), round(y, 1)

    # -- Build SVG fragments -------------------------------------------------
    R = 48  # photo circle radius

    path_d = ("M " + " L ".join(
        "{},{}".format(*to_svg(lat, lng)) for lng, lat in outline_pts
    ) + " Z") if outline_pts else ""

    # Place photo circles (greedy non-overlap)
    photo_placements: list[tuple] = []  # (id, label, lat, lng, px, py)
    placed_centers: list[tuple[float, float]] = []
    for m in photo_manholes:
        pid = str(m["id"])
        lat, lng = m["lat"], m["lng"]
        mx, my = to_svg(lat, lng)
        px, py = _find_placement(mx, my, placed_centers, R,
                                 PANEL_X, PANEL_X + PANEL_W, PANEL_Y, PANEL_Y + PANEL_H)
        placed_centers.append((px, py))
        photo_placements.append((pid, m.get("city", ""), lat, lng, px, py))

    photo_ids = {p[0] for p in photo_placements}

    clips = lines = imgs = lbls = ""
    for pid, label, lat, lng, px, py in photo_placements:
        mx, my = to_svg(lat, lng)
        b64 = base64.b64encode((IMAGE_DIR / f"{pid}_latest.jpeg").read_bytes()).decode()
        clips += f'<clipPath id="c{pid}"><circle cx="{px}" cy="{py}" r="{R}"/></clipPath>\n'
        lines += (f'<line x1="{mx}" y1="{my}" x2="{px}" y2="{py}" '
                  f'stroke="rgba(255,255,255,0.2)" stroke-width="1.2" stroke-dasharray="4 3"/>\n')
        imgs  += (f'<circle cx="{px}" cy="{py}" r="{R+3.5}" fill="#1a2a4a" '
                  f'stroke="#F5C842" stroke-width="2" stroke-opacity="0.6"/>\n')
        imgs  += (f'<image href="data:image/jpeg;base64,{b64}" '
                  f'x="{px-R}" y="{py-R}" width="{R*2}" height="{R*2}" '
                  f'clip-path="url(#c{pid})" preserveAspectRatio="xMidYMid slice"/>\n')
        lbls  += (f'<text x="{px}" y="{py+R+14}" class="jp" font-size="12" font-weight="700" '
                  f'fill="rgba(255,255,255,0.65)" text-anchor="middle">{_xe(label)}</text>\n')

    dots = ""
    for m in all_manholes:
        x, y = to_svg(m["lat"], m["lng"])
        pid = str(m["id"])
        if pid in photo_ids:
            dots += f'<circle cx="{x}" cy="{y}" r="4" fill="#FF6B6B" opacity="0.9"/>\n'
        else:
            dots += (f'<circle cx="{x}" cy="{y}" r="3.5" fill="#F5C842" '
                     f'fill-opacity="0.65" stroke="#F5C842" stroke-width="0.5" stroke-opacity="0.4"/>\n')

    # Pokemon bar + chip section
    BAR_W = 430
    pokemon_section = _build_pokemon_section(top_pokemon, other_pokemon, BAR_W)

    map_label = f"{pref}のポケふた設置マップ（{count}箇所）"

    return f'''<svg width="1200" height="630" viewBox="0 0 1200 630" xmlns="http://www.w3.org/2000/svg">
<defs>
  <linearGradient id="bg" x1="0" y1="0" x2="1200" y2="630" gradientUnits="userSpaceOnUse">
    <stop offset="0" stop-color="#0C1B33"/><stop offset="0.55" stop-color="#14103C"/><stop offset="1" stop-color="#0F1E42"/>
  </linearGradient>
  <radialGradient id="glow_r" cx="78%" cy="44%" r="42%">
    <stop offset="0" stop-color="#2E1780" stop-opacity="0.5"/><stop offset="1" stop-color="#0C1B33" stop-opacity="0"/>
  </radialGradient>
  <linearGradient id="gold" x1="0" y1="0" x2="0" y2="1">
    <stop offset="0" stop-color="#FFE566"/><stop offset="1" stop-color="#F5A623"/>
  </linearGradient>
  <radialGradient id="badge_glow" cx="50%" cy="50%" r="50%">
    <stop offset="0" stop-color="#F5C842" stop-opacity="0.22"/><stop offset="1" stop-color="#F5C842" stop-opacity="0"/>
  </radialGradient>
  <filter id="nglow" x="-25%" y="-25%" width="150%" height="150%">
    <feGaussianBlur stdDeviation="5" result="b"/>
    <feMerge><feMergeNode in="b"/><feMergeNode in="SourceGraphic"/></feMerge>
  </filter>
  <style>.jp{{font-family:'Hiragino Sans','Yu Gothic UI','Noto Sans CJK JP',sans-serif;}}.en{{font-family:'Helvetica Neue',Arial,sans-serif;}}</style>
  {clips}
</defs>
<rect width="1200" height="630" fill="url(#bg)"/>
<rect width="1200" height="630" fill="url(#glow_r)"/>
<g fill="white">
  <circle cx="72" cy="25" r="1.1" opacity="0.4"/><circle cx="138" cy="14" r="0.9" opacity="0.3"/>
  <circle cx="254" cy="20" r="1" opacity="0.35"/><circle cx="378" cy="12" r="1.2" opacity="0.4"/>
  <circle cx="420" cy="52" r="1.7" opacity="0.45"/><circle cx="514" cy="6" r="1.3" opacity="0.35"/>
  <circle cx="160" cy="58" r="1.3" opacity="0.3"/><circle cx="870" cy="18" r="1.4" opacity="0.25"/>
</g>
<line x1="578" y1="30" x2="578" y2="598" stroke="rgba(255,255,255,0.06)" stroke-width="1"/>
<!-- LEFT: text -->
<rect x="52" y="44" width="228" height="30" rx="15"
      fill="#F5C842" fill-opacity="0.1" stroke="#F5C842" stroke-opacity="0.45" stroke-width="1.5"/>
<text x="166" y="64" class="jp" font-size="13" font-weight="700" fill="#F5C842" text-anchor="middle">都道府県別ランキング</text>
<text x="48" y="175" class="jp" font-size="94" font-weight="900" fill="#FFFFFF" opacity="0.95">{pref}</text>
<text x="48" y="285" class="en" font-size="100" font-weight="900" fill="url(#gold)" filter="url(#nglow)">{count}</text>
<text x="{48 + len(str(count)) * 60}" y="272" class="jp" font-size="36" font-weight="700" fill="#F5C842">枚</text>
<circle cx="390" cy="250" r="52" fill="url(#badge_glow)"/>
<circle cx="390" cy="250" r="43" fill="#F5C842" fill-opacity="0.07" stroke="#F5C842" stroke-width="2" stroke-opacity="0.5"/>
<text x="390" y="234" class="jp" font-size="13" font-weight="700" fill="#F5C842" text-anchor="middle" opacity="0.8">全国</text>
<text x="390" y="264" class="en" font-size="33" font-weight="900" fill="#FFE566" text-anchor="middle" filter="url(#nglow)">{rank}</text>
<text x="390" y="283" class="jp" font-size="15" font-weight="700" fill="#F5C842" text-anchor="middle" opacity="0.85">位</text>
<text x="52" y="316" class="jp" font-size="16" fill="rgba(255,255,255,0.42)">全国{total}枚中　{percent}% を占める</text>
<rect x="52" y="326" width="{BAR_W}" height="1" fill="#F5C842" opacity="0.22"/>
{pokemon_section}
<!-- RIGHT: map -->
<path d="{path_d}" fill="rgba(90,150,220,0.09)" stroke="rgba(140,200,255,0.5)" stroke-width="1.8" stroke-linejoin="round"/>
{lines}{dots}{imgs}{lbls}
<text x="{PANEL_X + PANEL_W//2}" y="590" class="jp" font-size="11"
      fill="rgba(255,255,255,0.18)" text-anchor="middle">{map_label}</text>
<!-- FOOTER -->
<rect x="0" y="601" width="1200" height="29" fill="rgba(0,0,0,0.32)"/>
<line x1="0" y1="601" x2="1200" y2="601" stroke="#F5C842" stroke-width="1" stroke-opacity="0.15"/>
<circle cx="68" cy="615" r="7" fill="#F5C842" opacity="0.55"/>
<circle cx="68" cy="615" r="3.5" fill="#0C1B33"/>
<text x="83" y="620" class="jp" font-size="15" font-weight="700" fill="rgba(255,255,255,0.72)">ポケふたマップ</text>
<text x="228" y="620" class="jp" font-size="11" fill="rgba(255,255,255,0.28)">全国ポケモンマンホール情報サイト</text>
<text x="1142" y="620" class="en" font-size="13" font-weight="600" fill="rgba(255,255,255,0.35)" text-anchor="end">data.pokefuta.com</text>
</svg>'''


def _pick_spread(candidates: list[dict], n: int) -> list[dict]:
    """Pick up to n manholes spread geographically via greedy farthest-point."""
    if not candidates:
        return []
    if len(candidates) <= n:
        return candidates
    chosen = [candidates[0]]
    for _ in range(n - 1):
        best, best_d = None, -1.0
        for c in candidates:
            if c in chosen:
                continue
            d = min(math.hypot(c["lat"] - x["lat"], c["lng"] - x["lng"]) for x in chosen)
            if d > best_d:
                best_d, best = d, c
        if best:
            chosen.append(best)
    return chosen


def _find_placement(
    mx: float, my: float,
    placed: list[tuple[float, float]],
    R: int,
    x_min: float, x_max: float, y_min: float, y_max: float,
) -> tuple[float, float]:
    """Find a non-overlapping circle center near (mx, my)."""
    min_dist = R * 2 + 6
    for dist in range(30, 120, 12):
        for deg in range(0, 360, 20):
            rad = math.radians(deg)
            px = mx + dist * math.cos(rad)
            py = my + dist * math.sin(rad)
            if not (x_min + R < px < x_max - R and y_min + R < py < y_max - R):
                continue
            if all(math.hypot(px - ox, py - oy) >= min_dist for ox, oy in placed):
                return px, py
    return mx, my  # fallback


def _build_pokemon_section(
    top: list[tuple[str, int]],
    others: list[str],
    bar_w: int,
) -> str:
    out = '<text x="52" y="350" class="jp" font-size="13" font-weight="700" fill="rgba(255,255,255,0.38)">登場するポケモン</text>\n'

    colors = ["url(#gold)", "rgba(140,200,255,0.7)"]
    y = 370
    for i, (name, cnt) in enumerate(top[:2]):
        w = round(cnt / max(top[0][1], 1) * bar_w) if top else 0
        out += (f'<text x="52" y="{y+4}" class="jp" font-size="14" font-weight="700" '
                f'fill="rgba(255,255,255,0.75)">{_xe(name)}</text>\n')
        out += (f'<text x="{52+bar_w}" y="{y+4}" class="jp" font-size="13" '
                f'fill="#F5C842" text-anchor="end">{cnt}箇所</text>\n')
        out += f'<rect x="52" y="{y+8}" width="{bar_w}" height="9" rx="4.5" fill="rgba(255,255,255,0.1)"/>\n'
        out += f'<rect x="52" y="{y+8}" width="{w}" height="9" rx="4.5" fill="{colors[i]}" opacity="0.85"/>\n'
        y += 34

    if others:
        out += f'<text x="52" y="{y+12}" class="jp" font-size="12" fill="rgba(255,255,255,0.32)">その他の登場ポケモン</text>\n'
        cx, cy = 52, y + 32
        for name in others:
            w = len(name) * 14 + 18
            if cx + w > 530:
                cx, cy = 52, cy + 28
            out += (f'<rect x="{cx}" y="{cy-16}" width="{w}" height="22" rx="11" '
                    f'fill="rgba(100,160,230,0.12)" stroke="rgba(140,190,255,0.3)" stroke-width="1"/>\n')
            out += (f'<text x="{cx+w//2}" y="{cy}" class="jp" font-size="12" '
                    f'fill="rgba(255,255,255,0.6)" text-anchor="middle">{_xe(name)}</text>\n')
            cx += w + 6
    return out


# ---------------------------------------------------------------------------
# Template-based builders (other types)
# ---------------------------------------------------------------------------

def _placeholders_travel_trivia(raw: dict) -> dict:
    ft = raw["fact_type"]
    v = raw["values"]
    if ft == "total_count":
        line1, line2, line3, line4 = str(v["total"]), "全国ポケふた設置数", "", ""
    elif ft == "empty_prefs":
        line1 = f"{v['empty_count']}県"
        line2 = "ポケふた未設置の都道府県"
        line3 = "・".join(v["pref_names"])
        line4 = ""
    elif ft == "regional_top":
        line1, line2 = v["region"], "ポケふたが最も多い地方"
        line3, line4 = f"{v['count']}枚 / 全国{v['total']}枚", ""
    elif ft == "pokemon_variety":
        line1, line2, line3, line4 = str(v["species_count"]), "登場するポケモンの種類数", "", ""
    elif ft == "pokemon_widest_spread":
        line1 = str(v["city_count"])
        line2, line3, line4 = f"{v['ja_name']}の設置市区町村数", "全国最多の分布", ""
    elif ft == "top3_ranking":
        line1, line2 = "TOP3", "都道府県別ランキング"
        line3 = f"①{v['top3'][0]['pref']} {v['top3'][0]['count']}枚　②{v['top3'][1]['pref']} {v['top3'][1]['count']}枚"
        line4 = f"③{v['top3'][2]['pref']} {v['top3'][2]['count']}枚"
    else:
        line1 = line2 = line3 = line4 = ""
    return {"{{LINE1}}": line1, "{{LINE2}}": line2, "{{LINE3}}": line3, "{{LINE4}}": line4}


def _placeholders_latest_photo(raw: dict) -> dict:
    pokemon_str = "・".join(raw.get("pokemon_list", [raw["pokemon"]]))
    date_str = raw["created_at"][:10].replace("-", "/")
    photo_path = IMAGE_DIR / f"{raw['manhole_id']}_latest.jpeg"
    if photo_path.exists():
        b64 = base64.b64encode(photo_path.read_bytes()).decode()
        photo_elem = (
            f'<image href="data:image/jpeg;base64,{b64}" '
            f'x="770" y="157" width="310" height="310" '
            f'preserveAspectRatio="xMidYMid slice" clip-path="url(#photoClip)"/>'
        )
    else:
        photo_elem = ('<text x="925" y="318" class="reg" font-size="16" '
                      'fill="#9A7A3F" text-anchor="middle">写真なし</text>')
    return {
        "{{PREF}}": raw["pref"], "{{CITY}}": raw["city"],
        "{{POKEMON}}": pokemon_str, "{{DATE}}": date_str,
        "{{PHOTO_ELEMENT}}": photo_elem,
    }


def _placeholders_pokemon_rank(raw: dict) -> dict:
    return {
        "{{POKEMON}}": raw["ja_name"], "{{RANK}}": str(raw["rank"]),
        "{{COUNT}}": str(raw["count"]), "{{CITY_COUNT}}": str(raw["city_count"]),
    }


def _placeholders_rare_area(raw: dict) -> dict:
    return {"{{PREF}}": raw["pref"], "{{COUNT}}": str(raw["count"]), "{{TOTAL}}": str(raw["total"])}


def _placeholders_no_photo(raw: dict) -> dict:
    return {
        "{{PREF}}": raw["pref"],
        "{{NO_PHOTO_COUNT}}": str(raw["no_photo_count"]),
        "{{TOTAL_COUNT}}": str(raw["total_count"]),
    }


_TEMPLATE_BUILDERS = {
    "travel_trivia": _placeholders_travel_trivia,
    "latest_photo": _placeholders_latest_photo,
    "pokemon_rank": _placeholders_pokemon_rank,
    "rare_area": _placeholders_rare_area,
    "no_photo": _placeholders_no_photo,
}


# ---------------------------------------------------------------------------
# Area map SVG builder (michineki / remote_island)
# ---------------------------------------------------------------------------

def _build_area_map_svg(
    headline: str,
    subline: str,
    count: int,
    pref: str,
    manholes: list[dict],
    top_pokemons: list[str],
    special_point: dict | None = None,
    extra_label: str = "",
) -> str:
    """Dark-theme 2-panel SVG for area-based types (no prefecture outline)."""
    PANEL_X, PANEL_Y, PANEL_W, PANEL_H = 585, 30, 600, 565
    PAD = 50

    all_lats = [m["lat"] for m in manholes if m.get("lat")]
    all_lngs = [m["lng"] for m in manholes if m.get("lng")]
    if special_point:
        all_lats.append(special_point["lat"])
        all_lngs.append(special_point["lng"])
    if not all_lats:
        all_lats, all_lngs = [35.0], [136.0]

    lat_min, lat_max = min(all_lats), max(all_lats)
    lng_min, lng_max = min(all_lngs), max(all_lngs)
    if lat_max - lat_min < 0.05:
        mid = (lat_min + lat_max) / 2
        lat_min, lat_max = mid - 0.1, mid + 0.1
    if lng_max - lng_min < 0.05:
        mid = (lng_min + lng_max) / 2
        lng_min, lng_max = mid - 0.2, mid + 0.2

    lat_pad = (lat_max - lat_min) * 0.3
    lng_pad = (lng_max - lng_min) * 0.3
    lat_min -= lat_pad; lat_max += lat_pad
    lng_min -= lng_pad; lng_max += lng_pad

    lng_range = lng_max - lng_min
    lat_range = lat_max - lat_min
    avail_w = PANEL_W - 2 * PAD
    avail_h = PANEL_H - 2 * PAD
    scale = min(avail_w / lng_range, avail_h / lat_range)
    map_w = lng_range * scale
    map_h = lat_range * scale
    x_off = PANEL_X + PAD + (avail_w - map_w) / 2
    y_off = PANEL_Y + PAD + (avail_h - map_h) / 2 + map_h

    def to_svg(lat: float, lng: float) -> tuple[float, float]:
        x = x_off + (lng - lng_min) * scale
        y = y_off - (lat - lat_min) * scale
        return round(x, 1), round(y, 1)

    image_ids = {f.stem.replace("_latest", "") for f in IMAGE_DIR.glob("*_latest.jpeg")}
    photo_candidates = [m for m in manholes if str(m.get("id", "")) in image_ids and m.get("lat") and m.get("lng")]
    photo_manholes = _pick_spread(photo_candidates, n=5)

    R = 42
    clips = lines_svg = imgs = lbls = ""
    placed_centers: list[tuple[float, float]] = []
    photo_ids: set[str] = set()

    for m in photo_manholes:
        pid = str(m["id"])
        lat, lng = m["lat"], m["lng"]
        mx, my = to_svg(lat, lng)
        px, py = _find_placement(mx, my, placed_centers, R,
                                 PANEL_X, PANEL_X + PANEL_W, PANEL_Y, PANEL_Y + PANEL_H)
        placed_centers.append((px, py))
        photo_ids.add(pid)
        b64 = base64.b64encode((IMAGE_DIR / f"{pid}_latest.jpeg").read_bytes()).decode()
        clips += f'<clipPath id="c{pid}"><circle cx="{px}" cy="{py}" r="{R}"/></clipPath>\n'
        lines_svg += (f'<line x1="{mx}" y1="{my}" x2="{px}" y2="{py}" '
                      f'stroke="rgba(255,255,255,0.2)" stroke-width="1.2" stroke-dasharray="4 3"/>\n')
        imgs += (f'<circle cx="{px}" cy="{py}" r="{R+3.5}" fill="#1a2a4a" '
                 f'stroke="#F5C842" stroke-width="2" stroke-opacity="0.6"/>\n')
        imgs += (f'<image href="data:image/jpeg;base64,{b64}" '
                 f'x="{px-R}" y="{py-R}" width="{R*2}" height="{R*2}" '
                 f'clip-path="url(#c{pid})" preserveAspectRatio="xMidYMid slice"/>\n')
        city = m.get("city", "")
        lbls += (f'<text x="{px}" y="{py+R+14}" class="jp" font-size="12" font-weight="700" '
                 f'fill="rgba(255,255,255,0.65)" text-anchor="middle">{_xe(city)}</text>\n')

    dots = ""
    for m in manholes:
        if not m.get("lat") or not m.get("lng"):
            continue
        x, y = to_svg(m["lat"], m["lng"])
        if str(m.get("id", "")) in photo_ids:
            dots += f'<circle cx="{x}" cy="{y}" r="4" fill="#FF6B6B" opacity="0.9"/>\n'
        else:
            dots += (f'<circle cx="{x}" cy="{y}" r="5" fill="#F5C842" '
                     f'fill-opacity="0.7" stroke="#FFE566" stroke-width="1"/>\n')

    special_svg = ""
    if special_point:
        sx, sy = to_svg(special_point["lat"], special_point["lng"])
        label = _xe(special_point.get("label", ""))
        special_svg = (
            f'<circle cx="{sx}" cy="{sy}" r="12" fill="#00C875" opacity="0.9" stroke="white" stroke-width="2"/>\n'
            f'<text x="{sx}" y="{sy+5}" font-size="13" text-anchor="middle" fill="white" font-weight="700">★</text>\n'
            f'<text x="{sx}" y="{sy+28}" class="jp" font-size="11" fill="rgba(0,220,130,0.9)" text-anchor="middle">{label}</text>\n'
        )

    BAR_W = 430
    pokemon_chips = ""
    if top_pokemons:
        pokemon_chips += '<text x="52" y="415" class="jp" font-size="13" font-weight="700" fill="rgba(255,255,255,0.38)">登場するポケモン</text>\n'
        cx_p, cy_p = 52, 438
        for name in top_pokemons[:6]:
            w = len(name) * 14 + 18
            if cx_p + w > 530:
                cx_p, cy_p = 52, cy_p + 28
            pokemon_chips += (f'<rect x="{cx_p}" y="{cy_p-16}" width="{w}" height="22" rx="11" '
                              f'fill="rgba(100,160,230,0.12)" stroke="rgba(140,190,255,0.3)" stroke-width="1"/>\n')
            pokemon_chips += (f'<text x="{cx_p+w//2}" y="{cy_p}" class="jp" font-size="12" '
                              f'fill="rgba(255,255,255,0.6)" text-anchor="middle">{_xe(name)}</text>\n')
            cx_p += w + 6

    hl_len = len(headline)
    hl_size = "44" if hl_len >= 10 else ("52" if hl_len >= 7 else "64")

    return f'''<svg width="1200" height="630" viewBox="0 0 1200 630" xmlns="http://www.w3.org/2000/svg">
<defs>
  <linearGradient id="bg" x1="0" y1="0" x2="1200" y2="630" gradientUnits="userSpaceOnUse">
    <stop offset="0" stop-color="#0C1B33"/><stop offset="0.55" stop-color="#14103C"/><stop offset="1" stop-color="#0F1E42"/>
  </linearGradient>
  <radialGradient id="glow_r" cx="78%" cy="44%" r="42%">
    <stop offset="0" stop-color="#2E1780" stop-opacity="0.5"/><stop offset="1" stop-color="#0C1B33" stop-opacity="0"/>
  </radialGradient>
  <linearGradient id="gold" x1="0" y1="0" x2="0" y2="1">
    <stop offset="0" stop-color="#FFE566"/><stop offset="1" stop-color="#F5A623"/>
  </linearGradient>
  <filter id="nglow" x="-25%" y="-25%" width="150%" height="150%">
    <feGaussianBlur stdDeviation="5" result="b"/>
    <feMerge><feMergeNode in="b"/><feMergeNode in="SourceGraphic"/></feMerge>
  </filter>
  <style>.jp{{font-family:'Hiragino Sans','Yu Gothic UI','Noto Sans CJK JP',sans-serif;}}.en{{font-family:'Helvetica Neue',Arial,sans-serif;}}</style>
  {clips}
</defs>
<rect width="1200" height="630" fill="url(#bg)"/>
<rect width="1200" height="630" fill="url(#glow_r)"/>
<line x1="578" y1="30" x2="578" y2="598" stroke="rgba(255,255,255,0.06)" stroke-width="1"/>
<!-- LEFT -->
<rect x="52" y="44" width="228" height="30" rx="15"
      fill="#F5C842" fill-opacity="0.1" stroke="#F5C842" stroke-opacity="0.45" stroke-width="1.5"/>
<text x="166" y="64" class="jp" font-size="13" font-weight="700" fill="#F5C842" text-anchor="middle">{_xe(subline)}</text>
<text x="48" y="{130 + (64 - int(hl_size)) * 2}" class="jp" font-size="{hl_size}" font-weight="900" fill="#FFFFFF" opacity="0.95">{_xe(headline)}</text>
<text x="48" y="270" class="en" font-size="100" font-weight="900" fill="url(#gold)" filter="url(#nglow)">{count}</text>
<text x="{48 + len(str(count)) * 60}" y="257" class="jp" font-size="36" font-weight="700" fill="#F5C842">枚</text>
<text x="52" y="300" class="jp" font-size="16" fill="rgba(255,255,255,0.42)">{_xe(pref)}</text>
<text x="52" y="324" class="jp" font-size="14" fill="rgba(255,255,255,0.30)">{_xe(extra_label)}</text>
<rect x="52" y="338" width="{BAR_W}" height="1" fill="#F5C842" opacity="0.22"/>
{pokemon_chips}
<!-- RIGHT: map -->
{lines_svg}{dots}{special_svg}{imgs}{lbls}
<text x="{PANEL_X + PANEL_W//2}" y="590" class="jp" font-size="11"
      fill="rgba(255,255,255,0.18)" text-anchor="middle">{_xe(headline)}のポケふた設置マップ</text>
<!-- FOOTER -->
<rect x="0" y="601" width="1200" height="29" fill="rgba(0,0,0,0.32)"/>
<line x1="0" y1="601" x2="1200" y2="601" stroke="#F5C842" stroke-width="1" stroke-opacity="0.15"/>
<circle cx="68" cy="615" r="7" fill="#F5C842" opacity="0.55"/>
<circle cx="68" cy="615" r="3.5" fill="#0C1B33"/>
<text x="83" y="620" class="jp" font-size="15" font-weight="700" fill="rgba(255,255,255,0.72)">ポケふたマップ</text>
<text x="228" y="620" class="jp" font-size="11" fill="rgba(255,255,255,0.28)">全国ポケモンマンホール情報サイト</text>
<text x="1142" y="620" class="en" font-size="13" font-weight="600" fill="rgba(255,255,255,0.35)" text-anchor="end">data.pokefuta.com</text>
</svg>'''


def _build_michineki_svg(raw: dict) -> str:
    all_pokemons = [p for m in raw["manholes"] for p in m.get("pokemons", [])]
    top_pokemons = [p for p, _ in Counter(all_pokemons).most_common(6)]
    return _build_area_map_svg(
        headline=raw["station_name"],
        subline="道の駅チャレンジ",
        count=raw["manhole_count"],
        pref=raw["pref"],
        manholes=raw["manholes"],
        top_pokemons=top_pokemons,
        special_point={"lat": raw["lat"], "lng": raw["lng"], "label": "道の駅"},
        extra_label=f'半径{raw["radius_km"]}km以内に{raw["manhole_count"]}枚',
    )


def _build_remote_island_svg(raw: dict) -> str:
    return _build_area_map_svg(
        headline=raw["island_name"],
        subline="離島のポケふた",
        count=raw["manhole_count"],
        pref=raw["pref"],
        manholes=raw["manholes"],
        top_pokemons=raw.get("top_pokemons", []),
        special_point=None,
        extra_label=f'{raw["pref"]} {raw["city"]}',
    )


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    for path in (DAILY_JSON, CANDIDATES_JSON):
        if not path.exists():
            sys.exit(f"[generate_social_ogp] {path.name} が見つかりません。先に /social-post を実行してください。")

    daily = json.loads(DAILY_JSON.read_text(encoding="utf-8"))
    post_id = daily["id"]
    post_type = daily["type"]

    candidates = json.loads(CANDIDATES_JSON.read_text(encoding="utf-8"))
    candidate = next((c for c in candidates if c["id"] == post_id), None)
    if candidate is None:
        sys.exit(f"[generate_social_ogp] candidates に id={post_id} が見つかりません。")

    raw = candidate["raw_data"]

    # Generate SVG text
    if post_type == "prefecture_rank":
        print(f"[generate_social_ogp] {raw['pref']} の地図・写真データを取得中…")
        svg_text = _build_prefecture_rank_svg(raw)
    elif post_type == "michineki":
        print(f"[generate_social_ogp] {raw['station_name']} の地図を生成中…")
        svg_text = _build_michineki_svg(raw)
    elif post_type == "remote_island":
        print(f"[generate_social_ogp] {raw['island_name']} の地図を生成中…")
        svg_text = _build_remote_island_svg(raw)
    elif post_type in _TEMPLATE_BUILDERS:
        template_path = TEMPLATE_DIR / f"{post_type}.svg"
        if not template_path.exists():
            sys.exit(f"[generate_social_ogp] テンプレートが見つかりません: {template_path}")
        svg_text = template_path.read_text(encoding="utf-8")
        for key, value in _TEMPLATE_BUILDERS[post_type](raw).items():
            svg_text = svg_text.replace(key, value)
    else:
        sys.exit(f"[generate_social_ogp] 未対応タイプ: {post_type}")

    OUTPUT_SVG.write_text(svg_text, encoding="utf-8")
    print(f"[generate_social_ogp] SVG → {OUTPUT_SVG}")

    svg_to_jpg(OUTPUT_SVG, OUTPUT_JPG)
    print(f"[generate_social_ogp] JPG → {OUTPUT_JPG}")

    svg_to_png(svg_text.encode("utf-8"), OUTPUT_PNG)
    print(f"[generate_social_ogp] PNG → {OUTPUT_PNG}")


if __name__ == "__main__":
    main()
