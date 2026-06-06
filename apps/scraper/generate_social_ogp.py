#!/usr/bin/env python3
"""Generate OGP PNG (1200×630) for today's social post.

Reads docs/social-post-daily.json (id, type) and docs/social-post-candidates.json
(raw_data), substitutes placeholders in docs/ogp_template/{type}.svg, then
converts to docs/social-post-ogp.png via rsvg-convert.

Usage:
    python3 apps/scraper/generate_social_ogp.py
"""
from __future__ import annotations

import base64
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DAILY_JSON = ROOT / "docs" / "social-post-daily.json"
CANDIDATES_JSON = ROOT / "docs" / "social-post-candidates.json"
TEMPLATE_DIR = ROOT / "docs" / "ogp_template"
OUTPUT_PNG = ROOT / "docs" / "social-post-ogp.png"
IMAGE_DIR = ROOT / "dataset" / "manhole" / "image"


# ---------------------------------------------------------------------------
# SVG → PNG conversion
# ---------------------------------------------------------------------------

def svg_to_png(svg_bytes: bytes, out_path: Path) -> None:
    result = subprocess.run(
        ["rsvg-convert", "-f", "png", "-w", "1200", "-h", "630", "-o", str(out_path), "-"],
        input=svg_bytes,
        capture_output=True,
    )
    if result.returncode != 0:
        raise RuntimeError(f"rsvg-convert failed: {result.stderr.decode()}")


# ---------------------------------------------------------------------------
# Placeholder builders per type
# ---------------------------------------------------------------------------

def _placeholders_prefecture_rank(raw: dict) -> dict:
    bar_width = max(4, int(float(raw["percent"]) / 100 * 540))
    return {
        "{{PREF}}": raw["pref"],
        "{{RANK}}": str(raw["rank"]),
        "{{COUNT}}": str(raw["count"]),
        "{{TOTAL}}": str(raw["total"]),
        "{{PERCENT}}": str(raw["percent"]),
        "{{BAR_WIDTH}}": str(bar_width),
    }


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
    return {
        "{{LINE1}}": line1,
        "{{LINE2}}": line2,
        "{{LINE3}}": line3,
        "{{LINE4}}": line4,
    }


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
        photo_elem = (
            '<text x="925" y="318" class="reg" font-size="16" '
            'fill="#9A7A3F" text-anchor="middle">写真なし</text>'
        )

    return {
        "{{PREF}}": raw["pref"],
        "{{CITY}}": raw["city"],
        "{{POKEMON}}": pokemon_str,
        "{{DATE}}": date_str,
        "{{PHOTO_ELEMENT}}": photo_elem,
    }


def _placeholders_pokemon_rank(raw: dict) -> dict:
    return {
        "{{POKEMON}}": raw["ja_name"],
        "{{RANK}}": str(raw["rank"]),
        "{{COUNT}}": str(raw["count"]),
        "{{CITY_COUNT}}": str(raw["city_count"]),
    }


def _placeholders_rare_area(raw: dict) -> dict:
    return {
        "{{PREF}}": raw["pref"],
        "{{COUNT}}": str(raw["count"]),
        "{{TOTAL}}": str(raw["total"]),
    }


def _placeholders_no_photo(raw: dict) -> dict:
    return {
        "{{PREF}}": raw["pref"],
        "{{NO_PHOTO_COUNT}}": str(raw["no_photo_count"]),
        "{{TOTAL_COUNT}}": str(raw["total_count"]),
    }


_BUILDERS = {
    "prefecture_rank": _placeholders_prefecture_rank,
    "travel_trivia": _placeholders_travel_trivia,
    "latest_photo": _placeholders_latest_photo,
    "pokemon_rank": _placeholders_pokemon_rank,
    "rare_area": _placeholders_rare_area,
    "no_photo": _placeholders_no_photo,
}


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    if not DAILY_JSON.exists():
        sys.exit("[generate_social_ogp] docs/social-post-daily.json が見つかりません。先に /social-post を実行してください。")

    daily = json.loads(DAILY_JSON.read_text())
    post_id = daily["id"]
    post_type = daily["type"]

    candidates = [json.loads(l) for l in CANDIDATES_JSON.read_text().splitlines() if l.strip()] \
        if CANDIDATES_JSON.suffix == ".ndjson" \
        else json.loads(CANDIDATES_JSON.read_text())

    candidate = next((c for c in candidates if c["id"] == post_id), None)
    if candidate is None:
        sys.exit(f"[generate_social_ogp] candidates に id={post_id} が見つかりません。")

    raw = candidate["raw_data"]
    builder = _BUILDERS.get(post_type)
    if builder is None:
        sys.exit(f"[generate_social_ogp] 未対応タイプ: {post_type}")

    placeholders = builder(raw)

    template_path = TEMPLATE_DIR / f"{post_type}.svg"
    if not template_path.exists():
        sys.exit(f"[generate_social_ogp] テンプレートが見つかりません: {template_path}")

    svg_text = template_path.read_text()
    for key, value in placeholders.items():
        svg_text = svg_text.replace(key, value)

    svg_bytes = svg_text.encode("utf-8")
    svg_to_png(svg_bytes, OUTPUT_PNG)
    print(f"[generate_social_ogp] 生成完了 → {OUTPUT_PNG}")


if __name__ == "__main__":
    main()
