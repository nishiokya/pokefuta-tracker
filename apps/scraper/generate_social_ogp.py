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

import json
import os
import re
import subprocess
import sys
import tempfile
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

_ACCENT_COLOR = {
    "trivia":  "#57E0BE",
    "ranking": "#F2C24C",
    "rare":    "#FF9466",
}


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

    # Hero pin relocation
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
    lat, lng = _PREF_LATLNG.get(pref, (35.69, 139.69))
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
        "heroLat": lat,
        "heroLng": lng,
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
    return base


def _vars_rare_area(raw: dict) -> dict:
    pref = raw["pref"]
    lat, lng = _PREF_LATLNG.get(pref, (35.69, 139.69))
    percent = round(raw["count"] / max(raw["total"], 1) * 100, 1)
    return {
        "categoryLabel": "RARE",
        "titleLine1": f"{pref}の",
        "titleLine2": "ポケふた",
        "kicker": "まだ少ない地域",
        "mainNumber": str(raw["count"]),
        "mainUnit": "枚",
        "chips": [],
        "description": f"全国{raw['total']}枚中 {percent}%",
        "mapCaption": f"{pref}設置マップ",
        "heroLat": lat,
        "heroLng": lng,
    }


def _vars_no_photo(raw: dict) -> dict:
    pref = raw["pref"]
    lat, lng = _PREF_LATLNG.get(pref, (35.69, 139.69))
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
        "heroLat": lat,
        "heroLng": lng,
    }


def _vars_latest_photo(raw: dict) -> dict:
    pokemon_list = raw.get("pokemon_list", [raw.get("pokemon", "")])
    date_str = raw.get("created_at", "")[:10].replace("-", "/")
    return {
        "categoryLabel": "TRIVIA",
        "titleLine1": f"{raw['pref']} {raw['city']}",
        "titleLine2": "新着ポケふた",
        "kicker": f"投稿: {date_str}",
        "mainNumber": str(len(pokemon_list)),
        "mainUnit": "種",
        "chips": pokemon_list[:6],
        "description": "最新ポケふた情報",
        "mapCaption": f"{raw['city']}マップ",
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


_DESIGN_THEME: dict[str, str] = {
    "prefecture_rank": "ranking",
    "pokemon_rank":    "ranking",
    "travel_trivia":   "trivia",
    "rare_area":       "rare",
    "no_photo":        "rare",
    "latest_photo":    "trivia",
    "michineki":       "ranking",
    "remote_island":   "rare",
}

_DESIGN_VAR_BUILDERS = {
    "prefecture_rank": _vars_prefecture_rank,
    "pokemon_rank":    _vars_pokemon_rank,
    "travel_trivia":   _vars_travel_trivia,
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

    print(f"[generate_social_ogp] {post_type} → {theme} テンプレートで生成中…")
    vars_dict = var_builder(raw)
    svg_text = _render_design_template(theme, vars_dict)

    OUTPUT_SVG.write_text(svg_text, encoding="utf-8")
    print(f"[generate_social_ogp] SVG → {OUTPUT_SVG}")

    svg_to_jpg(OUTPUT_SVG, OUTPUT_JPG)
    print(f"[generate_social_ogp] JPG → {OUTPUT_JPG}")

    svg_to_png(svg_text.encode("utf-8"), OUTPUT_PNG)
    print(f"[generate_social_ogp] PNG → {OUTPUT_PNG}")


if __name__ == "__main__":
    main()
