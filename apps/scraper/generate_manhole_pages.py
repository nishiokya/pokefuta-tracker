#!/usr/bin/env python3
"""Generate static SEO-optimized HTML pages for individual manholes.

This script creates /manholes/{id}/index.html for each manhole in the dataset.
Each page includes unique title, description, h1, canonical URL, JSON-LD,
photos, Pokemon metadata, and CTAs for map navigation with GA4 tracking.
"""

from __future__ import annotations

import argparse
import datetime
import json
import logging
import math
import re
import sys
from pathlib import Path
from typing import Any, Optional
from urllib.parse import quote, urlparse
from xml.sax.saxutils import escape

sys.path.insert(0, str(Path(__file__).parent))
from display_names import compose_display_name, landmark_label, municipality_label  # noqa: E402
from generate_pokemon_pages import _FORM_PREFIX, _normalize_katakana  # noqa: E402
from generate_pokemon_pages import load_pokemon_metadata as load_pokemon_metadata_with_forms  # noqa: E402
from manhole_page_css import PAGE_CSS  # noqa: E402
from photo_caption import (  # noqa: E402
    format_display_name,
    format_photo_date,
    poster_profile_url,
)

try:
    from apps.scraper.municipalities import page_paths as municipality_page_paths  # noqa: E402
    from apps.scraper.prefectures import MANHOLE_PAGE_LANGS, PREFECTURE_SLUGS  # noqa: E402
    from apps.scraper.tag_meta import load_tag_meta  # noqa: E402
except ModuleNotFoundError as exc:
    if exc.name != "apps":
        raise
    from municipalities import page_paths as municipality_page_paths  # noqa: E402
    from prefectures import MANHOLE_PAGE_LANGS, PREFECTURE_SLUGS  # noqa: E402
    from tag_meta import load_tag_meta  # noqa: E402

# Constants
BASE_URL = "https://data.pokefuta.com/"

# 補助タグの絵文字とラベルは dataset/tag_meta.json（`icon_only`）が正。
# 以前はここに手書きの辞書があり、同じタグを地図と詳細ページで
# 別の絵文字・別の呼び名にしていた（史跡・観光・博物館など）。
_TAG_META = load_tag_meta()
SECONDARY_TAG_LABELS: dict[str, tuple[str, str]] = {
    tag["slug"]: (tag.get("emoji", ""), tag.get("label", tag["slug"]))
    for tag in _TAG_META.tags
    if tag.get("icon_only")
}

# 近くのデザインマンホール（ガンダム・キャラクターマンホール・写真館投稿）
DESIGN_STUDIO_LIST_URL = "https://pokefuta.com/design-manholes"
DESIGN_NEARBY_RADIUS_KM = 20.0
# 近くのデザインマンホールはメインではないので小さいタイルで4件（スマホ2列×2行、PC 4列×1行）
DESIGN_NEARBY_MAX = 4
# 近接判定に使ってよい座標ソース（manhole_titles.json の運用ルールと同じ）
CHARACTER_COORD_METHODS = {"official_google_map_link", "municipal_google_map_link"}
# 🎨近接称号は本文のデザインマンホールセクションへアンカーで飛ばす
DESIGN_ANCHOR_TITLE_KEYS = {"near_character_manhole", "near_gundam_manhole"}


def build_ja_to_slug(raw_data: list) -> dict[str, str]:
    """Build ja_name → slug map with regional form and katakana normalization."""
    result: dict[str, str] = {}
    for pokemon in raw_data:
        if not isinstance(pokemon, dict):
            continue
        names = pokemon.get("names", {})
        ja_name = names.get("ja", "")
        slug = pokemon.get("slug", "")
        form = pokemon.get("form") or ""
        if not ja_name or not slug:
            continue
        if ja_name not in result or not form:
            result[ja_name] = slug
        prefix = _FORM_PREFIX.get(form, "")
        if prefix:
            combined = prefix + ja_name
            if combined not in result:
                result[combined] = slug
    for key in list(result.keys()):
        normalized = _normalize_katakana(key)
        if normalized != key and normalized not in result:
            result[normalized] = result[key]
    return result

PREFECTURE_EN: dict[str, str] = {
    "北海道": "Hokkaido",
    "青森県": "Aomori Prefecture",
    "岩手県": "Iwate Prefecture",
    "宮城県": "Miyagi Prefecture",
    "秋田県": "Akita Prefecture",
    "山形県": "Yamagata Prefecture",
    "福島県": "Fukushima Prefecture",
    "茨城県": "Ibaraki Prefecture",
    "栃木県": "Tochigi Prefecture",
    "群馬県": "Gunma Prefecture",
    "埼玉県": "Saitama Prefecture",
    "千葉県": "Chiba Prefecture",
    "東京都": "Tokyo",
    "神奈川県": "Kanagawa Prefecture",
    "新潟県": "Niigata Prefecture",
    "富山県": "Toyama Prefecture",
    "石川県": "Ishikawa Prefecture",
    "福井県": "Fukui Prefecture",
    "山梨県": "Yamanashi Prefecture",
    "長野県": "Nagano Prefecture",
    "岐阜県": "Gifu Prefecture",
    "静岡県": "Shizuoka Prefecture",
    "愛知県": "Aichi Prefecture",
    "三重県": "Mie Prefecture",
    "滋賀県": "Shiga Prefecture",
    "京都府": "Kyoto Prefecture",
    "大阪府": "Osaka Prefecture",
    "兵庫県": "Hyogo Prefecture",
    "奈良県": "Nara Prefecture",
    "和歌山県": "Wakayama Prefecture",
    "鳥取県": "Tottori Prefecture",
    "島根県": "Shimane Prefecture",
    "岡山県": "Okayama Prefecture",
    "広島県": "Hiroshima Prefecture",
    "山口県": "Yamaguchi Prefecture",
    "徳島県": "Tokushima Prefecture",
    "香川県": "Kagawa Prefecture",
    "愛媛県": "Ehime Prefecture",
    "高知県": "Kochi Prefecture",
    "福岡県": "Fukuoka Prefecture",
    "佐賀県": "Saga Prefecture",
    "長崎県": "Nagasaki Prefecture",
    "熊本県": "Kumamoto Prefecture",
    "大分県": "Oita Prefecture",
    "宮崎県": "Miyazaki Prefecture",
    "鹿児島県": "Kagoshima Prefecture",
    "沖縄県": "Okinawa Prefecture",
}

# SVG icon symbols sourced from design/pokefuta_detail_ui_icons.svg
_SVG_DEFS = (
    '<svg width="0" height="0" style="position:absolute" aria-hidden="true"><defs>'
    # --- detail section heading icons ---
    '<symbol id="icon-detail-location" viewBox="0 0 96 96">'
    '<path fill="#FFF3D6" d="M17 24h48l14 14v34H17z"/>'
    '<path fill="none" stroke="#6A4B36" stroke-linecap="round" stroke-linejoin="round" stroke-width="7" d="M17 24h48l14 14v34H17zM65 24v14h14"/>'
    '<path fill="#6F55A3" d="M48 68s17-17 17-32a17 17 0 1 0-34 0c0 15 17 32 17 32z"/>'
    '<circle cx="48" cy="36" r="7" fill="#fff"/>'
    "</symbol>"
    '<symbol id="icon-detail-nearby" viewBox="0 0 96 96">'
    '<circle cx="48" cy="48" r="31" fill="#F8F1E2"/>'
    '<path fill="none" stroke="#6F55A3" stroke-linecap="round" stroke-linejoin="round" stroke-width="5" d="M48 14v10M48 72v10M14 48h10M72 48h10"/>'
    '<path fill="#6F55A3" d="M48 68s18-18 18-34a18 18 0 1 0-36 0c0 16 18 34 18 34z"/>'
    '<circle cx="48" cy="34" r="7" fill="#fff"/>'
    '<path fill="none" stroke="#F0A44A" stroke-width="5" stroke-linecap="round" d="M23 65s6-8 14-6 12 10 22 7 14-11 14-11"/>'
    "</symbol>"
    '<symbol id="icon-detail-same-pref" viewBox="0 0 96 96">'
    '<rect x="13" y="17" width="70" height="58" rx="12" fill="#FFF3D6"/>'
    '<rect x="13" y="17" width="70" height="58" rx="12" fill="none" stroke="#6A4B36" stroke-linecap="round" stroke-linejoin="round" stroke-width="7"/>'
    '<path fill="#BFAF98" opacity="0.45" d="M25 62l8-23 14 8 11-16 12 31z"/>'
    '<path fill="#6F55A3" d="M63 54s11-11 11-21a11 11 0 1 0-22 0c0 10 11 21 11 21z"/>'
    '<circle cx="63" cy="33" r="4" fill="#fff"/>'
    '<path fill="none" stroke="#6F55A3" stroke-linecap="round" stroke-linejoin="round" stroke-width="5" d="M28 30h15M28 43h12M28 56h20"/>'
    "</symbol>"
    # --- link grid icons ---
    '<symbol id="icon-link-google-map" viewBox="0 0 96 96">'
    '<rect x="12" y="16" width="72" height="64" rx="14" fill="#FFF3D6"/>'
    '<path fill="none" stroke="#6A4B36" stroke-linecap="round" stroke-linejoin="round" stroke-width="7" d="M12 16h72v64H12z"/>'
    '<path fill="none" stroke="#89CFF0" stroke-linecap="round" stroke-linejoin="round" stroke-width="5" d="M22 63c13-18 28-18 52-41"/>'
    '<path fill="none" stroke="#2D8F46" stroke-linecap="round" stroke-linejoin="round" stroke-width="5" d="M20 36h56"/>'
    '<path fill="#6F55A3" d="M50 70s18-20 18-36a18 18 0 1 0-36 0c0 16 18 36 18 36z"/>'
    '<circle cx="50" cy="34" r="7" fill="#fff"/>'
    "</symbol>"
    '<symbol id="icon-link-official" viewBox="0 0 96 96">'
    '<path fill="none" stroke="#2D8F46" stroke-linecap="round" stroke-linejoin="round" stroke-width="7" d="M33 19h44v44M75 21L38 58"/>'
    '<rect x="18" y="34" width="44" height="43" rx="8" fill="none" stroke="#6A4B36" stroke-linecap="round" stroke-linejoin="round" stroke-width="7"/>'
    '<path fill="#F0A44A" opacity="0.35" d="M25 25l10 9 12-16 8 17 16-7-7 16 17 8-19 6-2 19-14-13-17 10 3-19-16-9 18-4z"/>'
    "</symbol>"
    '<symbol id="icon-link-prefecture" viewBox="0 0 96 96">'
    '<rect x="15" y="17" width="66" height="62" rx="12" fill="#FFF3D6"/>'
    '<path fill="none" stroke="#6F55A3" stroke-linecap="round" stroke-linejoin="round" stroke-width="7" d="M15 17h66v62H15z"/>'
    '<path fill="#BFAF98" opacity="0.5" d="M28 62l10-30 16 11 13-19 11 38z"/>'
    '<circle cx="68" cy="31" r="8" fill="#2D8F46"/>'
    '<path fill="none" stroke="#6A4B36" stroke-linecap="round" stroke-linejoin="round" stroke-width="5" d="M26 68h42"/>'
    "</symbol>"
    '<symbol id="icon-link-map" viewBox="0 0 96 96">'
    '<path fill="none" stroke="#6F55A3" stroke-linecap="round" stroke-linejoin="round" stroke-width="7" d="M13 24l22-9 26 9 22-9v57l-22 9-26-9-22 9zM35 15v57M61 24v57"/>'
    '<circle cx="61" cy="43" r="8" fill="#F0A44A"/>'
    "</symbol>"
    '<symbol id="icon-link-photo" viewBox="0 0 96 96">'
    '<rect x="15" y="28" width="66" height="48" rx="12" fill="#FFF3D6"/>'
    '<path fill="none" stroke="#6A4B36" stroke-linecap="round" stroke-linejoin="round" stroke-width="7" d="M15 28h66v48H15zM35 28l6-10h14l6 10"/>'
    '<circle cx="48" cy="52" r="14" fill="#fff" stroke="#6F55A3" stroke-width="7"/>'
    '<circle cx="70" cy="39" r="4" fill="#6F55A3"/>'
    "</symbol>"
    '<symbol id="icon-link-share" viewBox="0 0 96 96">'
    '<circle cx="28" cy="48" r="12" fill="#E73A51"/>'
    '<circle cx="68" cy="24" r="12" fill="#E73A51"/>'
    '<circle cx="68" cy="72" r="12" fill="#E73A51"/>'
    '<path fill="none" stroke="#E73A51" stroke-linecap="round" stroke-linejoin="round" stroke-width="5" d="M38 42l20-12M38 54l20 12"/>'
    "</symbol>"
    '<symbol id="icon-share-x" viewBox="0 0 24 24">'
    '<path fill="currentColor" d="M18.244 2.25h3.308l-7.227 8.26 8.502 11.24H16.17l-4.714-6.231-5.401 6.231H2.766l7.73-8.835L1.254 2.25H8.08l4.259 5.622zm-1.161 17.52h1.833L7.084 4.126H5.117z"/>'
    "</symbol>"
    '<symbol id="icon-share-line" viewBox="0 0 24 24">'
    '<path fill="currentColor" d="M19.365 9.863c.349 0 .63.285.63.631 0 .345-.281.63-.63.63H17.61v1.125h1.755c.349 0 .63.283.63.63 0 .344-.281.629-.63.629h-2.386c-.345 0-.627-.285-.627-.629V8.108c0-.345.282-.63.63-.63h2.386c.346 0 .627.285.627.63 0 .349-.281.63-.63.63H17.61v1.125h1.755zm-3.855 3.016c0 .27-.174.51-.432.596-.064.021-.133.031-.199.031-.211 0-.391-.09-.51-.25l-2.443-3.317v2.94c0 .344-.279.629-.631.629-.346 0-.626-.285-.626-.629V8.108c0-.27.173-.51.43-.595.06-.023.136-.033.194-.033.195 0 .375.104.495.254l2.462 3.33V8.108c0-.345.282-.63.63-.63.345 0 .63.285.63.63v4.771zm-5.741 0c0 .344-.282.629-.631.629-.345 0-.627-.285-.627-.629V8.108c0-.345.282-.63.63-.63.346 0 .628.285.628.63v4.771zm-2.466.629H4.917c-.345 0-.63-.285-.63-.629V8.108c0-.345.285-.63.63-.63.348 0 .63.285.63.63v4.141h1.756c.348 0 .629.283.629.63 0 .344-.281.629-.629.629M24 10.314C24 4.943 18.615.572 12 .572S0 4.943 0 10.314c0 4.811 4.27 8.842 10.035 9.608.391.082.923.258 1.058.59.12.301.079.766.038 1.08l-.164 1.02c-.045.301-.24 1.186 1.049.645 1.291-.539 6.916-4.078 9.436-6.975C23.176 14.393 24 12.458 24 10.314"/>'
    "</symbol>"
    "</defs></svg>"
)


def hreflang_links(manhole_id: str) -> str:
    """日本語版と訳した言語の詳細ページを相互に指す。x-default は日本語版。"""
    path = f"manholes/{quote(manhole_id)}/"
    links = [f'<link rel="alternate" hreflang="ja" href="{BASE_URL}{path}">']
    links += [
        f'<link rel="alternate" hreflang="{lang}" href="{BASE_URL}{lang}/{path}">'
        for lang in MANHOLE_PAGE_LANGS
    ]
    links.append(f'<link rel="alternate" hreflang="x-default" href="{BASE_URL}{path}">')
    return "\n  ".join(links)


def _icon(symbol_id: str, extra_class: str = "") -> str:
    cls = f"icon {extra_class}".strip()
    return f'<svg class="{cls}" aria-hidden="true"><use href="#{symbol_id}"/></svg>'

logger = logging.getLogger(__name__)


def haversine(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    """Return great-circle distance in km."""
    R = 6371.0
    dlat = math.radians(lat2 - lat1)
    dlng = math.radians(lng2 - lng1)
    a = (math.sin(dlat / 2) ** 2
         + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2))
         * math.sin(dlng / 2) ** 2)
    return R * 2 * math.asin(math.sqrt(min(1.0, max(0.0, a))))


def normalize_id(value: Any) -> str:
    """Normalize manhole ID for consistent joining across datasets."""
    if value is None:
        return ""
    s = str(value).strip()
    # Remove leading zeros for comparison but keep original format
    return s.lstrip('0') or '0'


def load_manholes(path: Path) -> list[dict]:
    """Load manholes from NDJSON file."""
    manholes = []
    if not path.exists():
        logger.warning(f"Manhole data file not found: {path}")
        return manholes

    for line_num, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        try:
            record = json.loads(line)
            manholes.append(record)
        except json.JSONDecodeError as e:
            logger.warning(f"Failed to parse line {line_num}: {e}")

    logger.info(f"Loaded {len(manholes)} manholes from {path}")
    return manholes


def _escape_attr_value(value: object) -> str:
    """Escape text for embedding inside single- or double-quoted HTML attributes.

    xml.sax.saxutils.escape はデフォルトでクォートを変換しないため、
    NDJSON由来の値を属性に埋め込むときはこちらを使う。
    """
    return escape(str(value), {"'": "&#39;", '"': "&quot;"})


def _safe_pokefuta_url(value: object) -> str:
    """Allow only https URLs on pokefuta.com (写真館) — anything else becomes ''."""
    url = str(value or "")
    return url if url.startswith("https://pokefuta.com/") else ""


def _spot_coords(row: dict) -> tuple[float, float] | None:
    """Parse lat/lng leniently; None when missing or non-numeric."""
    try:
        return float(row["lat"]), float(row["lng"])
    except (KeyError, TypeError, ValueError):
        return None


def _read_ndjson(path: Path) -> list[dict]:
    """Read an NDJSON file leniently (missing file / broken lines → skip)."""
    rows: list[dict] = []
    if not path.exists():
        logger.warning(f"NDJSON file not found: {path}")
        return rows
    for line_num, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError as e:
            logger.warning(f"Failed to parse {path.name} line {line_num}: {e}")
            continue
        if isinstance(row, dict):
            rows.append(row)
    return rows


def load_design_spots(
    gundam_path: Path,
    character_path: Path,
    submissions_path: Path,
) -> list[dict]:
    """Load design-manhole spots for the nearby section.

    Sources:
      - gundam_path: docs/gmanhole.ndjson (g-manhole.net master)
      - character_path: dataset/aichi_character_manholes.ndjson
      - submissions_path: docs/design_manholes.ndjson (写真館の公開投稿)

    写真館投稿は canonical_ref / nearby_refs でマスタ蓋に合流させ、
    合流先の studio_url（写真館詳細）と photo_url として使う。
    どのマスタにも紐づかない投稿は独立スポットとして扱う。
    """
    spots: list[dict] = []

    for row in _read_ndjson(gundam_path):
        if row.get("status", "active") != "active":
            continue
        gid = str(row.get("id", "")).strip()
        coords = _spot_coords(row)
        if not gid or coords is None:
            continue
        spots.append({
            "ref": f"gundam:{gid}",
            "kind": "gundam",
            "title": str(row.get("title") or "").strip() or "ガンダムマンホール",
            "work": "ガンダムマンホール",
            "prefecture": row.get("prefecture", "") or "",
            "city": row.get("city", "") or "",
            "lat": coords[0],
            "lng": coords[1],
            "studio_url": "",
            "photo_url": "",
        })

    for row in _read_ndjson(character_path):
        if row.get("status") != "active" or row.get("installation_status") != "installed":
            continue
        if row.get("coordinate_method") not in CHARACTER_COORD_METHODS:
            continue
        cid = str(row.get("id", "")).strip()
        coords = _spot_coords(row)
        if not cid or coords is None:
            continue
        spots.append({
            "ref": f"character:{cid}",
            "kind": "character",
            "title": str(row.get("title") or "").strip() or "キャラクターマンホール",
            "work": str(row.get("work") or "").strip(),
            "prefecture": row.get("prefecture", "") or "",
            "city": row.get("city", "") or "",
            "lat": coords[0],
            "lng": coords[1],
            "studio_url": "",
            "photo_url": "",
        })

    by_ref = {s["ref"]: s for s in spots}
    for row in _read_ndjson(submissions_path):
        if row.get("status") != "active":
            continue
        coords = _spot_coords(row)
        if coords is None:
            continue
        refs: list[str] = []
        if row.get("canonical_ref"):
            refs.append(str(row["canonical_ref"]))
        refs += [
            str(r.get("ref", ""))
            for r in (row.get("nearby_refs") or [])
            if isinstance(r, dict) and r.get("ref")
        ]
        matched = next((by_ref[r] for r in refs if r in by_ref), None)
        if matched is not None:
            # マスタ蓋の写真館リンク・写真として合流（最初の投稿を採用）
            if not matched["studio_url"]:
                matched["studio_url"] = _safe_pokefuta_url(row.get("source_url"))
                matched["photo_url"] = _safe_pokefuta_url(row.get("photo_url"))
            continue
        if any(r.startswith("pokefuta:") for r in refs):
            # ポケふた至近の投稿はポケふた自体の写真とみなし、デザインマンホールとしては出さない
            continue
        sid = str(row.get("id", "")).strip()
        if not sid:
            continue
        spots.append({
            "ref": sid,
            "kind": "studio",
            "title": str(row.get("title") or "").strip() or "デザインマンホール",
            "work": str(row.get("work") or "").strip(),
            "prefecture": row.get("prefecture", "") or "",
            "city": row.get("city", "") or "",
            "lat": coords[0],
            "lng": coords[1],
            "studio_url": _safe_pokefuta_url(row.get("source_url")),
            "photo_url": _safe_pokefuta_url(row.get("photo_url")),
        })

    logger.info(
        "Loaded %d design spots (with studio link: %d)",
        len(spots),
        sum(1 for s in spots if s["studio_url"]),
    )
    return spots


def load_photos(path: Path) -> dict[str, dict]:
    """Load manhole photos data."""
    if not path.exists():
        logger.warning(f"Photos file not found: {path}")
        return {}

    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        photos = data.get("photos", {})
        logger.info(f"Loaded {len(photos)} photo entries from {path}")

        # Normalize keys
        normalized = {}
        for manhole_id, photo_data in photos.items():
            norm_id = normalize_id(manhole_id)
            normalized[norm_id] = photo_data

        return normalized
    except json.JSONDecodeError as e:
        logger.error(f"Failed to parse photos JSON: {e}")
        return {}


def load_pokemon_metadata(path: Path) -> dict[str, dict]:
    """Load Pokemon metadata indexed by Japanese name (regional forms included).

    ポケモンページと同じ索引を使う。メタデータの日本語名は通常種もリージョンフォームも
    「ロコン」なので、日本語名だけで引くと通常のロコンがアローラのタイプ・世代になる。
    """
    return load_pokemon_metadata_with_forms(path)


def filter_pokemons(pokemons: list) -> list[str]:
    """Filter out prefecture site links from Pokemon list."""
    if not isinstance(pokemons, list):
        return []

    return [
        p for p in pokemons
        if isinstance(p, str) and p.strip() and "ローカルActs" not in p
    ]


def format_pokemon_label(pokemons: list[str]) -> str:
    """Pokemon name label for OGP/social meta: max 3 names, then ' ほか'."""
    if not pokemons:
        return "ポケモン"
    if len(pokemons) <= 3:
        return "・".join(pokemons)
    return "・".join(pokemons[:3]) + " ほか"


def manhole_label(manhole: dict) -> str:
    """Build a plain-text display label for a manhole (for use in link text)."""
    pokes = "・".join(filter_pokemons(manhole.get("pokemons", []))) or "ポケモン"
    location = compose_display_name(manhole) or "所在地不明"
    return f"{location}のポケふた（{pokes}）"


def _attr_json(data: dict) -> str:
    """Serialize dict as JSON safe for use inside an HTML double-quoted onclick attribute.

    json.dumps produces valid JSON strings; escape() with the quotes mapping
    converts all " to &quot; so they don't terminate the enclosing HTML attribute.
    Browsers decode &quot; → " before evaluating onclick, so the JS receives
    a proper object literal.
    """
    return escape(json.dumps(data, ensure_ascii=False), {'"': '&quot;'})


def _js_json(value) -> str:
    """Serialize value as JSON safe for embedding inside an inline <script> block.

    json.dumps alone does NOT escape the </script> sequence, which a browser
    HTML parser treats as closing the script tag regardless of JS context — a
    potential XSS / page-break vector. Replacing '</' with '<\\/' is the
    standard workaround: browsers parse the escaped form as a literal '</'
    inside the JS string, so the runtime value is unchanged.
    """
    return json.dumps(value, ensure_ascii=False).replace("</", "<\\/")


def _trip_leg_label(km: float) -> str:
    if km < 0.1:
        return "次はすぐ近く"
    if km < 1:
        return f"次まで約{round(km * 1000, -1):.0f}m"
    return f"次まで約{km:.1f}km"


def _trip_section_html(trip: dict, manhole_id: str, id_to_image_url: dict[str, str]) -> str:
    """この蓋が入っている「ポケふた旅」のエリアを、trip ページと同じ順番・時間で出す。"""
    items = ""
    for index, other in enumerate(trip["route"]):
        oid = str(other.get("id", "")).strip()
        leg = trip["legs"][index] if index < len(trip["legs"]) else None
        badges = ""
        if oid == manhole_id:
            badges += "<span class='trip-here'>このポケふた</span>"
        badges += f"<span class='distance'>{escape(_trip_leg_label(leg))}</span>" if leg is not None else ""
        params = _attr_json({
            "surface": "manhole_trip",
            "from_manhole_id": manhole_id,
            "to_manhole_id": oid,
            "position": index + 1,
        })
        items += _render_related_card(
            other, id_to_image_url, extra_html=badges, event_name="click_trip_stop", onclick_params=params,
        )
    order_note = "よく回られる順番です。" if trip.get("common") else "直線距離がいちばん短くなる順番です。"
    more_params = _attr_json({"surface": "manhole_trip", "from_manhole_id": manhole_id})
    return (
        f"<section class='nearby-section trip-section section-card'>"
        f"<h2>{_icon('icon-detail-nearby', 'icon-lg')} "
        f"{escape(trip['name'])}のポケふた{trip['count']}枚を回る</h2>"
        f"<p class='design-note'>{escape(trip['text'])}{order_note}</p>"
        f"<ol class='related-list related-list--cards trip-stops'>{items}</ol>"
        f"<a class='gallery-more' href='{_escape_attr_value(trip['path'])}'"
        f" onclick=\"trackEvent('click_trip_from_manhole', {more_params})\">"
        f"地図と回り方を見る（ポケふた旅） →</a>"
        f"</section>"
    )


def _render_related_card(
    other: dict,
    id_to_image_url: dict[str, str],
    extra_html: str = "",
    event_name: str = "",
    onclick_params: str = "",
) -> str:
    """Build a related-manhole list item with local thumbnail and pin icon."""
    oid = str(other.get("id", "")).strip()
    label = manhole_label(other)
    thumb_url = id_to_image_url.get(oid, "")
    thumb_html = (
        f'<div class="related-card-thumb">'
        f'<img src="{escape(thumb_url)}" alt="" loading="lazy"'
        f' onerror="this.closest(\'.related-card-thumb\').remove()">'
        f"</div>"
    ) if thumb_url else ""
    onclick_attr = (
        f' onclick="trackEvent({escape(json.dumps(event_name), {chr(34): "&quot;"})}, {onclick_params})"'
        if event_name and onclick_params else ""
    )
    return (
        f"<li class='related-card'>{thumb_html}"
        f"<div class='related-card-body'>"
        f'{_icon("icon-detail-location", "icon-sm")}'
        f"<a href='/manholes/{quote(oid, safe='')}/'{onclick_attr}>{escape(label)}</a>"
        f"</div>{extra_html}</li>"
    )


def generate_html(
    manhole: dict,
    photo: Optional[dict],
    pokemon_meta: dict[str, dict],
    nearby: list[tuple[dict, float]],
    same_pref: list[dict],
    pref_total: int,
    same_pokemon: list[dict],
    id_to_image_url: dict[str, str],
    city_total: int = 0,
    same_pokemon_total: int = 0,
    nearby_count: int = 0,
    ogp_dir: Optional[Path] = None,
    ja_to_slug: dict[str, str] | None = None,
    nearby_design: list[tuple[dict, float]] | None = None,
    municipality_path: str | None = None,
    trip: dict | None = None,
) -> str:
    """Generate complete HTML for a manhole detail page.

    trip: この蓋が入っている /trip/ エリア（generate_trip_pages.trips_by_manhole）。あれば「次に寄れるポケふた」の
    代わりに、そのエリアだけを trip ページと同じ順番・時間で出す（ほかのエリアの蓋は混ぜない）。

    municipality_path: この蓋の市区町村ページ（/municipalities/...）。ページがある自治体だけ渡す。
    """
    manhole_id = str(manhole.get("id", "")).strip()
    prefecture = manhole.get("prefecture", "")
    city = manhole.get("city", "")
    address = manhole.get("address", "")
    # 地図の見出し（place_label）と同じ規則で整えた施設名。h1 と「施設・場所」欄で使う
    building = landmark_label(manhole, municipality_label(manhole))
    access = manhole.get("access", "")
    pokemons = filter_pokemons(manhole.get("pokemons", []))
    detail_url = manhole.get("detail_url", "")
    lat = manhole.get("lat")
    lng = manhole.get("lng")

    # Generate unique title and description
    pokemon_text = "・".join(pokemons) if pokemons else "ポケモン"
    # Meta-only label: max 3 names + ' ほか'. Used solely in og:/twitter: tags.
    pokemon_label = format_pokemon_label(pokemons)
    # 自治体名が欠落する場合は都道府県名を優先（og:/twitter: タイトル用）
    city_label = city if city else prefecture

    title = f"{prefecture}{city}のポケふた｜{pokemon_text}｜ポケふた図鑑"

    description = (
        f"{prefecture}{city}に設置されているポケふた。"
        f"{pokemon_text}が描かれています。"
        f"場所・写真・地図・周辺のポケふた情報を掲載。"
    )

    # og:/twitter: meta tags — inject top title when available
    titles: list[dict] = manhole.get("titles", []) or []
    _top = titles[0] if titles else None
    if _top:
        _top_prefix = f"{_top['emoji']} " if _top.get('emoji') else ""
        _top_label = f"{_top_prefix}{_top['label']}"
        _og_title = f"{_top_label}｜{city_label}のポケふた（{pokemon_label}）｜ポケふた図鑑"
        _og_desc = f"{_top_label}！{prefecture}{city}に設置されている{pokemon_label}のポケふた。場所・写真・地図で確認できます。"
        _tw_title = f"{_top_label}｜{city_label}のポケふた（{pokemon_label}）"
        _tw_desc = f"{_top_label}！{prefecture}{city}のポケふたを地図で確認できます。"
    else:
        _og_title = f"{city_label}のポケふた｜{pokemon_label}｜ポケふた図鑑"
        _og_desc = f"{prefecture}{city}に設置されている{pokemon_label}のポケふた。場所・写真・地図で確認できます。"
        _tw_title = f"{city_label}のポケふた｜{pokemon_label}"
        _tw_desc = f"{prefecture}{city}のポケふたを地図で確認できます。"

    # <title> と og: は検索向けに「県市のポケふた」の形を保つので、施設名は h1 だけに入れる
    h1 = f"{compose_display_name(manhole) or city_label}のポケふた"
    # place_ambiguous な蓋は名前にポケモン名が入っているので、二重に付けない
    if pokemons and not manhole.get("place_ambiguous"):
        h1 += f"（{pokemon_text}）"

    canonical_url = f"{BASE_URL}manholes/{quote(manhole_id)}/"
    map_url = f"{BASE_URL}?manhole={quote(manhole_id)}"
    pref_page_slug = PREFECTURE_SLUGS.get(prefecture, "")
    pref_url = f"/prefectures/{quote(pref_page_slug)}/" if pref_page_slug else f"{BASE_URL}?pref={quote(prefecture)}"

    # _js_json() serializes values for safe embedding inside <script> blocks:
    # json.dumps handles quotes/backslashes; the </  → <\/ replacement prevents
    # premature </script> tag closure from scraped data values.
    manhole_id_js = _js_json(manhole_id)
    prefecture_js = _js_json(prefecture)
    city_js = _js_json(city)
    pref_slug = PREFECTURE_EN.get(prefecture, "").lower().replace(" prefecture", "")

    # _attr_json() serializes dicts as JSON with " escaped to &quot; so they
    # are safe inside HTML double-quoted onclick attributes.
    onclick_params = _attr_json(
        {"surface": "manhole_links", "manhole_id": manhole_id, "prefecture": prefecture, "city": city}
    )

    # Source-differentiated params for Google Maps — same event name but
    # distinguishable in GA4 by where the tap came from.
    _base = {"manhole_id": manhole_id, "prefecture": prefecture, "city": city}
    gmaps_onclick_hero  = _attr_json({**_base, "surface": "hero"})
    gmaps_onclick_links = _attr_json({**_base, "surface": "links"})

    # Build Pokemon info with metadata
    pokemon_info_html = ""
    if pokemons:
        pokemon_info_html = "<section class='pokemon-section section-card'><h2>登場ポケモン</h2><div class='pokemon-list'>"
        for poke_name in pokemons:
            meta = pokemon_meta.get(poke_name) or pokemon_meta.get(_normalize_katakana(poke_name)) or {}
            names = meta.get("names", {})
            en_name = names.get("en", "")
            types_data = meta.get("types", [])
            types_ja = [t.get("ja", "") for t in types_data if isinstance(t, dict)]
            generation = meta.get("generation")

            ko_name = names.get("ko", "")
            zh_hans = names.get("zh-Hans", "")
            zh_hant = names.get("zh-Hant", "")
            multilingual_parts = [n for n in [en_name, ko_name, zh_hans, zh_hant] if n]

            _jts = ja_to_slug or {}
            _slug = _jts.get(poke_name) or _jts.get(_normalize_katakana(poke_name), "")
            pokemon_info_html += f"<div class='pokemon-card'>"
            if _slug:
                pokemon_info_html += f"<h3><a href='/pokemon/{quote(_slug)}/'>{escape(poke_name)}</a></h3>"
            else:
                pokemon_info_html += f"<h3>{escape(poke_name)}</h3>"
            if multilingual_parts:
                pokemon_info_html += f"<p class='multilingual-names'>{escape(' / '.join(multilingual_parts))}</p>"
            if types_ja:
                pokemon_info_html += f"<p class='types'>タイプ: {escape('・'.join(types_ja))}</p>"
            if generation:
                pokemon_info_html += f"<p class='generation'>第{generation}世代</p>"
            if same_pokemon:
                pokemon_info_html += "<a class='pokemon-same-link' href='#same-pokemon'>同じポケふたを見る →</a>"
            pokemon_info_html += "</div>"

        pokemon_info_html += "</div></section>"

    # photo_url is the single source of truth for whether a real photo exists.
    # has_photo_bool, og_image, and hero rendering all derive from this value.
    og_image = f"{BASE_URL}assets/ogp/pokefuta_map_ogp.png"
    photo_url = (photo.get("url", "") or photo.get("original_url", "")) if photo else ""
    has_photo_bool = bool(photo_url)
    has_photo_js = json.dumps(has_photo_bool)

    is_preinstall = manhole.get("installed") is False
    if is_preinstall:
        _preinstall_note = manhole.get("installation_note") or ""
        _preinstall_note_html = escape(_preinstall_note) if _preinstall_note else "設置予定"
        hero_photo_html = (
            f"<div class='hero-photo-placeholder hero-photo-preinstall'>"
            f"<span class='placeholder-camera' aria-hidden='true'>🚧</span>"
            f"<span class='placeholder-title'>設置前のポケふたです</span>"
            f"<span class='placeholder-sub'>{_preinstall_note_html}</span>"
            f"</div>"
        )
    else:
        hero_photo_html = (
            f"<a class='hero-photo-placeholder' href='https://pokefuta.com/upload?manhole_id={manhole_id}&amp;from=data'"
            f" target='_blank' rel='noopener noreferrer'"
            f" onclick=\"trackEvent('click_photo_upload_placeholder', {_attr_json({'surface': 'manhole_gallery', 'manhole_id': manhole_id, 'prefecture': prefecture, 'city': city, 'has_photo': False})})\">"
            f"<span class='placeholder-camera' aria-hidden='true'>📷</span>"
            f"<span class='placeholder-title'>まだ写真がありません</span>"
            f"<span class='placeholder-sub'>最初の旅写真を投稿する</span>"
            f"</a>"
        )

    if photo_url:
        og_image = photo_url

        display_name = format_display_name(photo.get("display_name"))

        raw_comment = photo.get("comment") or ""
        comment = " ".join(str(raw_comment).split())  # normalize whitespace
        if len(comment) > 100:
            comment = comment[:97] + "…"

        # 撮影日（shot_at）優先、欠損時は投稿日（created_at）にフォールバック。
        # 撮影日は古い場合があるため年付き表記を維持する。
        shot_date = format_photo_date(
            photo.get("shot_at") or photo.get("created_at"), "ja", with_year=True
        )

        credit_parts = []
        if display_name:
            _profile_url = poster_profile_url(photo.get("public_user_id"))
            if _profile_url:
                _poster_onclick = _attr_json({"manhole_id": manhole_id, "surface": "hero"})
                credit_parts.append(
                    f"<a class='poster-link' href='{_profile_url}'"
                    f" target='_blank' rel='noopener noreferrer'"
                    f" onclick=\"trackEvent('click_poster_profile', {_poster_onclick})\">"
                    f"📷 {escape(display_name)}</a>"
                )
            else:
                credit_parts.append(f"📷 {escape(display_name)}")
        if shot_date:
            credit_parts.append(shot_date)
        if credit_parts:
            inner = "".join(f"<span>{p}</span>" for p in credit_parts)
            credit_html = f"<div class='photo-credit'>{inner}</div>"
        else:
            credit_html = ""

        comment_html = (
            f"<div class='photo-comment'>{escape(comment)}</div>"
            if comment else ""
        )

        hero_photo_html = (
            f"<div class='hero-photo'>"
            # ヒーロー写真は LCP 要素なので lazy にしない。
            # ギャラリーと関連カードのサムネは lazy のままでよい。
            f"<img src=\"{escape(photo_url)}\" alt=\"{escape(h1)}の写真\""
            f" loading=\"eager\" fetchpriority=\"high\">"
            f"{credit_html}"
            f"{comment_html}"
            f"</div>"
        )

    # "みんなの写真" gallery: extra local thumbnails beyond the hero photo
    gallery_html = ""
    gallery_items = (photo.get("gallery_local") or []) if photo else []
    if gallery_items:
        thumbs = ""
        for g in gallery_items:
            g_credit = format_display_name(g.get("display_name"))
            # ギャラリーは overlay が小さいため年なしの短形式（撮影日→投稿日フォールバック）
            g_date = format_photo_date(g.get("shot_at") or g.get("created_at"), "ja")
            if g_credit:
                g_label = f"📷 {escape(g_credit)}"
                if g_date:
                    g_label += f" · {escape(g_date)}"
                _g_profile_url = poster_profile_url(g.get("public_user_id"))
                if _g_profile_url:
                    _g_poster_onclick = _attr_json({"manhole_id": manhole_id, "surface": "gallery"})
                    credit_span = (
                        f"<a class='gallery-credit poster-link' href='{_g_profile_url}'"
                        f" target='_blank' rel='noopener noreferrer'"
                        f" onclick=\"trackEvent('click_poster_profile', {_g_poster_onclick})\">"
                        f"{g_label}</a>"
                    )
                else:
                    credit_span = f"<span class='gallery-credit'>{g_label}</span>"
            elif g_date:
                credit_span = f"<span class='gallery-credit'>📷 {escape(g_date)}</span>"
            else:
                credit_span = ""
            thumbs += (
                f"<figure class='gallery-item'>"
                f"<img src=\"{escape(g['url'])}\" alt=\"{escape(h1)}の写真\" loading=\"lazy\">"
                f"{credit_span}"
                f"</figure>"
            )
        _gallery_more_onclick = _attr_json(
            {"surface": "manhole_gallery", "manhole_id": manhole_id, "prefecture": prefecture, "city": city}
        )
        gallery_html = (
            f"<section class='gallery-section section-card'>"
            f"<h2>みんなの写真</h2>"
            f"<div class='gallery-grid'>{thumbs}</div>"
            f"<a class='gallery-more' href='https://pokefuta.com/manhole/{quote(manhole_id)}'"
            f" target='_blank' rel='noopener noreferrer'"
            f" onclick=\"trackEvent('click_gallery_more', {_gallery_more_onclick})\">"
            f"すべての写真を見る →</a>"
            f"</section>"
        )

    # Per-manhole generated OGP takes priority over photo URL
    _ogp_path = (ogp_dir / f"{manhole_id}.png") if ogp_dir else None
    if _ogp_path is not None and _ogp_path.exists():
        og_image = f"{BASE_URL}assets/ogp/manholes/{manhole_id}.png"

    # HERO card: region label（県・市区町村ページへのパンくずを兼ねる。JSON-LD の BreadcrumbList と同じ並び）
    region_parts: list[str] = []
    breadcrumb_items: list[dict] = [{"name": "ポケふた図鑑", "item": BASE_URL}]
    if prefecture:
        if pref_page_slug:
            region_parts.append(f'<a href="{escape(pref_url)}">{escape(prefecture)}</a>')
            breadcrumb_items.append({"name": prefecture, "item": f"{BASE_URL}prefectures/{quote(pref_page_slug)}/"})
        else:
            region_parts.append(f"<span>{escape(prefecture)}</span>")
    if city:
        if municipality_path:
            region_parts.append(f'<a href="{escape(municipality_path)}">{escape(municipality_label(manhole))}</a>')
            breadcrumb_items.append({
                "name": municipality_label(manhole),
                "item": f"{BASE_URL}{municipality_path.lstrip('/')}",
            })
        else:
            region_parts.append(f"<span>{escape(city)}</span>")
    breadcrumb_items.append({"name": h1})
    region_html = "".join(region_parts)
    pref_en = PREFECTURE_EN.get(prefecture, "")
    region_en_html = f"<div class='hero-region-en'>{escape(pref_en)}</div>" if pref_en else ""

    # HERO card: pokemon tags
    pokemon_tags_html = ""
    if pokemons:
        _jts_hero = ja_to_slug or {}
        def _hero_tag(p: str) -> str:
            _slug = _jts_hero.get(p) or _jts_hero.get(_normalize_katakana(p), "")
            if _slug:
                return f"<a class='hero-tag' href='/pokemon/{quote(_slug)}/'>{escape(p)}</a>"
            return f"<span class='hero-tag'>{escape(p)}</span>"
        tags = "".join(_hero_tag(p) for p in pokemons)
        pokemon_tags_html = f"<div class='hero-pokemon-tags'>{tags}</div>"

    # HERO card: stats badges
    title_keys: set[str] = {t["key"] for t in titles}
    badges: list[str] = []
    if is_preinstall:
        badges.append("<span class='hero-badge hero-badge-pre'>🚧 設置前</span>")
    added_at = manhole.get("added_at", "") or ""
    try:
        added_year = datetime.date.fromisoformat(added_at[:10]).year
        if added_year >= datetime.date.today().year:
            badges.append(f"<span class='hero-badge hero-badge-new'>NEW {added_year}年設置</span>")
    except (ValueError, TypeError):
        pass
    # Title badges (all, from pokefuta.ndjson) — prepended before stats badges
    for t in titles:
        label = f"{escape(t['emoji'])} {escape(t['label'])}" if t.get("emoji") else escape(t["label"])
        if t.get("key") in DESIGN_ANCHOR_TITLE_KEYS and nearby_design:
            # 🎨近接称号は本文の「近くのデザインマンホール」へ飛べるようにする
            badges.append(
                f"<a class='hero-badge hero-badge-title hero-badge-anchor' href='#design-manholes'>{label}</a>"
            )
        else:
            badges.append(f"<span class='hero-badge hero-badge-title'>{label}</span>")
    # Secondary tag badges (tourism/park/museum/history/food/rail_access_good/river/in_station)
    for tag in (manhole.get("tags") or []):
        if tag in SECONDARY_TAG_LABELS:
            em, lbl = SECONDARY_TAG_LABELS[tag]
            badges.append(f"<span class='hero-badge hero-badge-secondary'>{escape(em)} {escape(lbl)}</span>")
    # Stats badges with suppression rules (§2.3)
    suppress_pref = title_keys & {"only_in_pref", "unique_pokemon"}
    suppress_nearby = "lone" in title_keys
    if pref_total > 0 and prefecture and not suppress_pref:
        badges.append(f"<span class='hero-badge'>{escape(prefecture)} {pref_total}枚</span>")
    if city_total >= 2 and city and municipality_path:
        badges.append(
            f"<a class='hero-badge hero-badge-anchor' href=\"{escape(municipality_path)}\">"
            f"{escape(municipality_label(manhole))} {city_total}枚</a>"
        )
    elif city_total >= 2 and city:
        badges.append(f"<span class='hero-badge'>{escape(city)} {city_total}枚</span>")
    if same_pokemon_total > 0:
        badges.append(f"<span class='hero-badge'>同じポケモン {same_pokemon_total}枚</span>")
    if nearby_count > 0 and not suppress_nearby:
        badges.append(f"<span class='hero-badge'>30km以内に{nearby_count}件</span>")
    stats_html = f"<div class='hero-stats'>{''.join(badges)}</div>" if badges else ""

    # HERO card: share JS data (Python-serialized to avoid injection)
    _title_hashtags = " ".join(t["hashtag"] for t in titles if t.get("hashtag"))
    _base_hashtags = f"{_title_hashtags} #ポケふた #ポケモンマンホール".strip()
    if is_preinstall and pokemons:
        _x_text = (
            f"設置前のポケふた（{pokemon_text}）。\n\n"
            f"{prefecture}{city}に設置予定です。設置されたら会いに行こう！\n\n"
            f"{_base_hashtags}"
        )
    elif has_photo_bool and pokemons:
        _x_text = (
            f"{prefecture}{city}のポケふたを発見！\n\n"
            f"登場ポケモン: {pokemon_text}\n"
            f"近くのポケふたも地図で探せます。\n\n"
            f"{_base_hashtags}"
        )
    else:
        _x_text = (
            f"{prefecture}{city}のポケふた、旅写真を募集中！\n\n"
            f"近くに行ったら投稿してみませんか？\n"
            f"{_base_hashtags}"
        )
    share_x_url = (
        f"https://twitter.com/intent/tweet"
        f"?text={quote(_x_text)}&url={quote(canonical_url)}"
    )
    share_line_url = f"https://social-plugins.line.me/lineit/share?url={quote(canonical_url)}"
    share_url_json = _js_json(canonical_url)
    # Web Share API (used by shareManhole in links_grid)
    _share_title = f"{city}のポケふた（{pokemon_text}）"
    _top_title_line = (
        f"{_top_prefix}{_top['label']}のポケふた！\n" if _top else ""
    )
    _share_text = (
        f"{_top_title_line}"
        f"{prefecture}{city}のポケふた（{pokemon_text}）を見つけました。\n"
        f"{prefecture}には{pref_total}枚のポケふたがあります。"
    ) if prefecture else f"{h1}を見つけました。"
    share_title_json = _js_json(_share_title)
    share_text_json = _js_json(_share_text)

    # Validate official URL (used for links-grid cards)
    _parsed = urlparse(detail_url) if detail_url else None
    has_official_url = _parsed and _parsed.scheme == "https" and _parsed.hostname == "local.pokemon.jp"

    # Location info
    location_html = f"""
<section class='location-section section-card'>
  <h2>設置場所</h2>
  <dl>
    <dt>都道府県</dt>
    <dd>{escape(prefecture)}</dd>
    <dt>市区町村</dt>
    <dd>{escape(city)}</dd>
"""
    if building:
        location_html += f"""
    <dt>施設・場所</dt>
    <dd>{escape(building)}</dd>
"""
    if address:
        location_html += f"""
    <dt>住所</dt>
    <dd>{escape(address)}</dd>
"""
    if access:
        location_html += f"""
    <dt>アクセス</dt>
    <dd>{escape(access)}</dd>
"""
    location_html += """
  </dl>
</section>
"""

    # JSON-LD structured data
    jsonld = {
        "@context": "https://schema.org",
        "@type": "TouristAttraction",
        "name": h1,
        "description": description,
        "url": canonical_url,
        "address": {
            "@type": "PostalAddress",
            "addressRegion": prefecture,
            "addressLocality": city,
            "streetAddress": address
        }
    }

    if lat is not None and lng is not None:
        jsonld["geo"] = {
            "@type": "GeoCoordinates",
            "latitude": lat,
            "longitude": lng
        }

    if photo:
        photo_image_url = photo.get("url") or photo.get("original_url")
        if photo_image_url:
            jsonld["image"] = photo_image_url

    breadcrumb_jsonld = {
        "@context": "https://schema.org",
        "@type": "BreadcrumbList",
        "itemListElement": [
            {"@type": "ListItem", "position": i, **entry} for i, entry in enumerate(breadcrumb_items, 1)
        ],
    }
    jsonld_str = json.dumps([jsonld, breadcrumb_jsonld], ensure_ascii=False, indent=2)

    # Links grid: external + internal + photo upload (移設統合)
    link_cards: list[str] = []
    # Share first: X / LINE / Web Share
    _share_onclick = _attr_json(
        {"surface": "manhole_share", "manhole_id": manhole_id, "prefecture": prefecture, "city": city}
    )
    link_cards.append(
        f"<a class='link-card link-card--share-x' href=\"{escape(share_x_url)}\""
        f" target=\"_blank\" rel=\"noopener noreferrer\""
        f" onclick=\"trackEvent('click_share_x', {_share_onclick})\">"
        f"{_icon('icon-share-x', 'link-card-icon')}<span>Xで共有</span></a>"
    )
    link_cards.append(
        f"<a class='link-card link-card--share-line' href=\"{escape(share_line_url)}\""
        f" target=\"_blank\" rel=\"noopener noreferrer\""
        f" onclick=\"trackEvent('click_share_line', {_share_onclick})\">"
        f"{_icon('icon-share-line', 'link-card-icon')}<span>LINEで送る</span></a>"
    )
    link_cards.append(
        f"<button type='button' class='link-card link-card--share' onclick='shareManhole()'>"
        f"{_icon('icon-link-share', 'link-card-icon')}<span>共有</span></button>"
    )
    # ポケふた写真館（pokefuta.com）の同ふたページ。ギャラリー未表示のふたでも写真館へ飛べるよう常設
    _photo_studio_onclick = _attr_json({"manhole_id": manhole_id, "surface": "links_photo_studio"})
    link_cards.append(
        f"<a class='link-card link-card--internal' href='https://pokefuta.com/manhole/{quote(manhole_id, safe='')}'"
        f" target='_blank' rel='noopener noreferrer'"
        f" onclick=\"trackEvent('click_photo_studio', {_photo_studio_onclick})\">"
        f"{_icon('icon-link-photo', 'link-card-icon')}<span>ポケふた写真館</span></a>"
    )
    # Navigation: Official / Prefecture / Same Pref / National Map
    if has_official_url:
        link_cards.append(
            f"<a class='link-card link-card--official' href=\"{escape(detail_url)}\""
            f" target=\"_blank\" rel=\"noopener noreferrer\""
            f" onclick=\"trackEvent('click_official_site', {onclick_params})\">"
            f"{_icon('icon-link-official', 'link-card-icon')}<span>公式サイト</span></a>"
        )
    if prefecture:
        link_cards.append(
            f"<a class='link-card link-card--internal' href=\"{escape(pref_url)}\">"
            f"{_icon('icon-detail-same-pref', 'link-card-icon')}<span>同じ都道府県</span></a>"
        )
    if municipality_path:
        link_cards.append(
            f"<a class='link-card link-card--internal' href=\"{escape(municipality_path)}\">"
            f"{_icon('icon-detail-same-pref', 'link-card-icon')}"
            f"<span>{escape(municipality_label(manhole))}のポケふた</span></a>"
        )
    _map_onclick = _attr_json({"manhole_id": manhole_id, "surface": "links_map"})
    link_cards.append(
        f"<a class='link-card link-card--internal' href=\"{escape(BASE_URL)}\""
        f" onclick=\"trackEvent('click_map_internal', {_map_onclick})\">"
        f"{_icon('icon-link-map', 'link-card-icon')}<span>全国マップ</span></a>"
    )
    links_grid_html = (
        f"<section class='links-section section-card'>"
        f"<h2>リンク</h2>"
        f"<div class='link-grid'>{''.join(link_cards)}</div>"
        f"</section>"
    ) if link_cards else ""

    # Nearby design manholes section (gundam / character / 写真館投稿)
    design_html = ""
    if nearby_design:
        design_items = ""
        for spot, dist in nearby_design:
            dist_str = f"{dist * 1000:.0f} m" if dist < 1.0 else f"{dist:.1f} km"
            # 写真館URL以外（不正スキーム等）は一覧へフォールバック
            studio_url = _safe_pokefuta_url(spot.get("studio_url"))
            has_studio = bool(studio_url)
            href = studio_url or DESIGN_STUDIO_LIST_URL
            _d_params = _attr_json({
                "surface": "manhole_design_nearby",
                "from_manhole_id": manhole_id,
                "design_ref": spot.get("ref", ""),
                "distance_km": round(dist, 1),
                "has_studio_page": has_studio,
            })
            photo_url = _safe_pokefuta_url(spot.get("photo_url"))
            thumb_html = (
                f"<span class='design-tile-thumb'>"
                f'<img src="{_escape_attr_value(photo_url)}" alt="" loading="lazy" onerror="this.remove()">'
                f"</span>"
                if photo_url
                else "<span class='design-tile-thumb design-tile-thumb--empty'>📷 写真募集中</span>"
            )
            work = spot.get("work", "")
            work_html = f"<span class='design-work'>{escape(work)}</span>" if work else ""
            design_items += (
                f"<li class='design-tile'>"
                f"<a href='{_escape_attr_value(href)}' target='_blank' rel='noopener noreferrer'"
                f" onclick=\"trackEvent('click_nearby_design_manhole', {_d_params})\">"
                f"{thumb_html}"
                f"<span class='design-tile-title'>{escape(spot.get('title', ''))}</span>"
                f"{work_html}"
                f"<span class='distance'>{escape(dist_str)}</span>"
                f"</a></li>"
            )
        _design_more_onclick = _attr_json({"manhole_id": manhole_id, "surface": "design_section"})
        design_html = (
            f"<section id='design-manholes' class='design-section section-card'>"
            f"<h2>🎨 近くのデザインマンホール</h2>"
            f"<p class='design-note'>ポケふたと一緒に巡れる、ご当地のデザインマンホールです。</p>"
            f"<ul class='design-tiles'>{design_items}</ul>"
            f"<a class='gallery-more' href='{escape(DESIGN_STUDIO_LIST_URL)}'"
            f" target='_blank' rel='noopener noreferrer'"
            f" onclick=\"trackEvent('click_design_studio_list', {_design_more_onclick})\">"
            f"写真館でデザインマンホールを見る →</a>"
            f"</section>"
        )

    # 「近くのデザインマンホール」と「ポケふた（回る/次に寄れる）」は、いちばん近い蓋がある方を上に出す
    def _nearest_pokefuta_km() -> float | None:
        if trip:
            lat, lng = manhole.get("lat"), manhole.get("lng")
            if lat is None or lng is None:
                return None
            dists = [
                haversine(float(lat), float(lng), float(r["lat"]), float(r["lng"]))
                for r in trip["route"] if str(r.get("id", "")).strip() != manhole_id
            ]
            return min(dists) if dists else None
        return nearby[0][1] if nearby else None

    # Nearby manholes section（/trip/ のエリアに入っている蓋は、そのエリアの回り方に差し替える）
    nearby_html = _trip_section_html(trip, manhole_id, id_to_image_url) if trip else ""
    if nearby and not trip:
        nearby_html = (
            f"<section class='nearby-section section-card'>"
            f"<h2>{_icon('icon-detail-nearby', 'icon-lg')} 次に寄れるポケふた</h2>"
            f"<ul class='related-list related-list--cards'>"
        )
        for other, dist in nearby:
            dist_str = f"{dist:.1f} km"
            _nearby_params = _attr_json({
                "surface": "manhole_related_nearby",
                "from_manhole_id": manhole_id,
                "to_manhole_id": str(other.get("id", "")).strip(),
                "distance_km": round(dist, 1),
            })
            nearby_html += _render_related_card(
                other, id_to_image_url,
                extra_html=f"<span class='distance'>{escape(dist_str)}</span>",
                event_name="click_nearby_manhole",
                onclick_params=_nearby_params,
            )
        nearby_html += "</ul></section>"

    _pokefuta_km = _nearest_pokefuta_km()
    _design_km = nearby_design[0][1] if nearby_design else None
    if nearby_html and design_html and _pokefuta_km is not None and (
        _design_km is None or _pokefuta_km < _design_km
    ):
        first_travel_html, second_travel_html = nearby_html, design_html
    else:
        first_travel_html, second_travel_html = design_html, nearby_html

    # Same pokemon manholes section
    same_pokemon_html = ""
    if same_pokemon:
        same_pokemon_html = (
            "<section id='same-pokemon' class='same-pokemon-section section-card'>"
            "<h2>同じポケモンのポケふた</h2>"
            "<ul class='related-list related-list--cards'>"
        )
        _current_poke_set = set(pokemons)
        for other in same_pokemon:
            _other_pokemons = filter_pokemons(other.get("pokemons", []))
            _shared = [p for p in _other_pokemons if p in _current_poke_set]
            _sp_params = _attr_json({
                "surface": "manhole_related_pokemon",
                "from_manhole_id": manhole_id,
                "to_manhole_id": str(other.get("id", "")).strip(),
                "pokemon_names": ",".join(_shared) if _shared else "",
            })
            same_pokemon_html += _render_related_card(
                other, id_to_image_url,
                event_name="click_same_pokemon_manhole",
                onclick_params=_sp_params,
            )
        same_pokemon_html += "</ul></section>"

    # Same prefecture section
    pref_section_html = ""
    if prefecture and same_pref:
        pref_section_html = (
            f"<section class='prefecture-section section-card'>"
            f"<h2>{_icon('icon-detail-same-pref', 'icon-lg')} {escape(prefecture)}のポケふた</h2>"
            f"<p>{escape(prefecture)}には現在{pref_total}枚のポケふたがあります。</p>"
            f"<ul class='related-list related-list--cards'>"
        )
        for other in same_pref:
            _pref_params = _attr_json({
                "surface": "manhole_related_prefecture",
                "from_manhole_id": manhole_id,
                "to_manhole_id": str(other.get("id", "")).strip(),
                "prefecture": prefecture,
            })
            pref_section_html += _render_related_card(
                other, id_to_image_url,
                event_name="click_prefecture_manhole",
                onclick_params=_pref_params,
            )
        pref_section_html += "</ul></section>"

    current_year = datetime.date.today().year

    # X (Twitter) follow section
    _follow_onclick = _attr_json(
        {"surface": "manhole_follow", "manhole_id": manhole_id, "prefecture": prefecture}
    )
    follow_x_html = (
        f"<section class='follow-section'>"
        f"<a href='https://x.com/pokemonmanhole'"
        f" target='_blank' rel='noopener noreferrer'"
        f" class='follow-x-card'"
        f" onclick=\"trackEvent('click_follow_x', {_follow_onclick})\">"
        f"<div class='follow-x-title'>最新のポケふた旅情報</div>"
        f"<div class='follow-x-body'>新設ポケふた・旅写真・全国の発見情報を更新中</div>"
        f"<div class='follow-x-cta'>Xでフォローする →</div>"
        f"</a></section>"
    )

    # Back button HTML
    _back_onclick = _attr_json({"manhole_id": manhole_id, "surface": "back_btn"})
    back_btn_html = (
        f"<a href=\"{escape(map_url)}\" class=\"back-btn\""
        f" onclick=\"trackEvent('click_map_internal', {_back_onclick})\">"
        f"← 全国マップへ戻る</a>"
    )

    # Hero photo upload CTA — suppressed entirely for 設置前 (notice is already shown in hero_photo_html)
    _photo_event = "click_photo_upload" if has_photo_bool else "click_photo_upload_placeholder"
    _photo_label = "写真を投稿" if has_photo_bool else "最初の旅写真を投稿する"
    _photo_cta_onclick = _attr_json(
        {
            "surface": "manhole_hero",
            "manhole_id": manhole_id,
            "prefecture": prefecture,
            "city": city,
            "has_photo": has_photo_bool,
        }
    )
    hero_actions_html = (
        ""
        if is_preinstall
        else (
            f'<div class="hero-actions">'
            f'<a class="btn-photo-upload" href="https://pokefuta.com/upload?manhole_id={manhole_id}&amp;from=data" target="_blank" rel="noopener noreferrer" onclick="trackEvent(\'{_photo_event}\', {_photo_cta_onclick})">{_icon("icon-link-photo", "action-icon")}<span>{escape(_photo_label)}</span></a>'
            f'<p class="photo-upload-note">投稿はポケふた写真館で受付（無料ログイン・GPS付き写真が必要）</p>'
            f'</div>'
        )
    )

    # Visit CTA (Google Maps full-width card)
    visit_cta_html = ""
    if lat is not None and lng is not None:
        gmaps_url = f"https://www.google.com/maps?q={lat},{lng}"
        visit_cta_html = (
            f'<a href="{escape(gmaps_url)}" class="visit-cta"'
            f' target="_blank" rel="noopener noreferrer"'
            f' onclick="trackEvent(\'click_google_maps\', {gmaps_onclick_hero})">'
            f'<span class="visit-cta-icon">{_icon("icon-link-google-map", "visit-cta-map-icon")}</span>'
            f'<span class="visit-cta-body">'
            f'<span class="visit-cta-main">Google Mapsで行き方を見る</span>'
            f'<span class="visit-cta-sub">現地への訪問ルートを確認する</span>'
            f'</span></a>'
        )

    # HERO card HTML
    hero_card_html = f"""
<div class="hero-card">
  {hero_photo_html}
  <div class="hero-body">
    <nav class="hero-region" aria-label="パンくず">{region_html}</nav>
    {region_en_html}
    <h1 class="hero-title">{escape(h1)}</h1>
    {pokemon_tags_html}
    {stats_html}
    {hero_actions_html}
  </div>
</div>
"""

    # Complete HTML
    html = f"""<!doctype html>
<html lang="ja">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{escape(title)}</title>
  <meta name="description" content="{escape(description)}">
  <meta name="robots" content="index,follow,max-image-preview:large">
  <link rel="canonical" href="{escape(canonical_url)}">
  {hreflang_links(manhole_id)}

  <meta property="og:type" content="article">
  <meta property="og:locale" content="ja_JP">
  <meta property="og:site_name" content="ポケふた図鑑">
  <meta property="og:title" content="{escape(_og_title)}">
  <meta property="og:description" content="{escape(_og_desc)}">
  <meta property="og:url" content="{escape(canonical_url)}">
  <meta property="og:image" content="{escape(og_image)}">

  <meta name="twitter:card" content="summary_large_image">
  <meta name="twitter:title" content="{escape(_tw_title)}">
  <meta name="twitter:description" content="{escape(_tw_desc)}">
  <meta name="twitter:image" content="{escape(og_image)}">

  <script type="application/ld+json">
{jsonld_str}
  </script>

  <!-- Google Analytics -->
  <script src="/assets/analytics.js?v=20261018a"></script>
  <script>
    window.PokefutaAnalytics.init({{
      'page_path': '/manholes/' + {manhole_id_js} + '/',
      site_type: 'map',
      page_type: 'map_manhole',
      prefecture: '{pref_slug}',
    }});
    gtag('event', 'view_manhole_detail', {{
      surface: 'manhole_detail',
      manhole_id: {manhole_id_js},
      prefecture: {prefecture_js},
      city: {city_js},
      pokemon_count: {len(pokemons)},
      has_photo: {has_photo_js}
    }});

    function shareManhole() {{
      var _sp = {{
        surface: 'manhole_share',
        manhole_id: {manhole_id_js},
        prefecture: {prefecture_js},
        city: {city_js}
      }};
      trackEvent('click_share', _sp);
      if (navigator.share) {{
        navigator.share({{
          title: {share_title_json},
          text: {share_text_json},
          url: {share_url_json}
        }}).then(function() {{
          trackEvent('complete_share', _sp);
        }}).catch(function() {{}});
      }} else if (navigator.clipboard && navigator.clipboard.writeText) {{
        navigator.clipboard.writeText({share_url_json}).then(function() {{
          trackEvent('share_copy_url', _sp);
          var _t = document.createElement('div');
          _t.textContent = 'URLをコピーしました';
          _t.style.cssText = 'position:fixed;bottom:24px;left:50%;transform:translateX(-50%);background:rgba(0,0,0,.8);color:#fff;padding:8px 20px;border-radius:20px;font-size:14px;z-index:9999;pointer-events:none';
          document.body.appendChild(_t);
          setTimeout(function() {{ document.body.removeChild(_t); }}, 2000);
        }}).catch(function() {{ alert({share_url_json}); }});
      }} else {{
        alert({share_url_json});
      }}
    }}
  </script>

  <style>
{PAGE_CSS}  </style>
</head>
<body>
  {_SVG_DEFS}
  <div class="container">
    {back_btn_html}

    {hero_card_html}

    {gallery_html}

    {visit_cta_html}

    <!-- adsense:manhole -->

    {location_html}

    {first_travel_html}

    {second_travel_html}

    {pokemon_info_html}

    {same_pokemon_html}

    {pref_section_html}

    {links_grid_html}

    {follow_x_html}

    <footer class="page-credit">
      <p>&copy; 2025-{current_year} data.pokefuta.com | ポケふた情報はポケモン公式サイトを参照しています</p>
    </footer>
  </div>
</body>
</html>
"""

    return html


class RelatedIndex:
    """詳細ページの「近く・同じ県・同じ自治体・同じポケモン」を引くための索引。訳したページも使う。"""

    def __init__(self, manholes: list[dict]) -> None:
        self.manholes = manholes
        self.pref: dict[str, list[dict]] = {}
        self.city: dict[str, list[dict]] = {}
        self.pokemon: dict[str, list[dict]] = {}
        for m in manholes:
            pref = m.get("prefecture", "")
            city = m.get("city", "")
            if pref:
                self.pref.setdefault(pref, []).append(m)
            if pref or city:
                self.city.setdefault(f"{pref}_{city}", []).append(m)
            for pk in filter_pokemons(m.get("pokemons", [])):
                self.pokemon.setdefault(pk, []).append(m)

    def related(self, manhole: dict) -> dict:
        """generate_html に渡す関連データ（nearby / same_pref / pref_total / same_pokemon / 件数）。"""
        manhole_id = str(manhole.get("id", "")).strip()
        prefecture = manhole.get("prefecture", "")
        city = manhole.get("city", "")
        lat = manhole.get("lat")
        lng = manhole.get("lng")

        # Nearby manholes (requires lat/lng)
        nearby: list[tuple[dict, float]] = []
        if lat is not None and lng is not None:
            for other in self.manholes:
                if str(other.get("id", "")) == manhole_id:
                    continue
                olat, olng = other.get("lat"), other.get("lng")
                if olat is None or olng is None:
                    continue
                dist = haversine(float(lat), float(lng), float(olat), float(olng))
                nearby.append((other, dist))
            nearby.sort(key=lambda x: x[1])
        nearby = [(m, d) for m, d in nearby if d <= 30.0]

        # Same prefecture manholes (stable sort: city then id)
        same_pref_all = [
            m for m in self.pref.get(prefecture, [])
            if str(m.get("id", "")) != manhole_id
        ]
        same_pref = sorted(
            same_pref_all,
            key=lambda m: (m.get("city", ""), str(m.get("id", "")))
        )[:20]

        # Same pokemon manholes (deduplicated: one entry per manhole)
        seen_ids: set[str] = set()
        same_pokemon: list[dict] = []
        for pk in filter_pokemons(manhole.get("pokemons", [])):
            for other in self.pokemon.get(pk, []):
                oid = str(other.get("id", "")).strip()
                if oid != manhole_id and oid not in seen_ids:
                    seen_ids.add(oid)
                    same_pokemon.append(other)

        return {
            "nearby": nearby[:5],
            "nearby_count": len(nearby),
            "same_pref": same_pref,
            "pref_total": len(self.pref.get(prefecture, [])),
            "city_total": len(self.city.get(f"{prefecture}_{city}", [])),
            "same_pokemon": same_pokemon[:10],
            "same_pokemon_total": len(seen_ids),
        }


def local_image_urls(manholes: list[dict], image_dir: Path) -> dict[str, str]:
    """Build GitHub Pages-safe image URL map (local files only; no Cloudflare URLs)"""
    id_to_image_url: dict[str, str] = {}
    for m in manholes:
        mid = str(m.get("id", "")).strip()
        if mid and (image_dir / f"{mid}_latest.jpeg").exists():
            id_to_image_url[mid] = f"{BASE_URL}manhole/image/{mid}_latest.jpeg"
    return id_to_image_url


def page_photo(
    manhole_id: str, photos: dict[str, dict], image_dir: Path, id_to_image_url: dict[str, str]
) -> Optional[dict]:
    """ヒーロー写真とギャラリー。ローカルに画像がある蓋だけ（無ければ None）。"""
    # Use local image only; merge user-photo metadata for credit overlay
    local_url = id_to_image_url.get(manhole_id)
    norm_id = normalize_id(manhole_id)
    user_photo = photos.get(norm_id) or {}

    # Gallery thumbnails beyond the hero (local files downloaded by
    # import_latest_manhole_photos.py as {id}_{photo_id[:8]}.jpeg)
    gallery_local: list[dict] = []
    rep_photo_id = user_photo.get("photo_id")
    for item in user_photo.get("gallery") or []:
        if not isinstance(item, dict) or item.get("photo_id") == rep_photo_id:
            continue
        slug = re.sub(r"[^0-9a-fA-F]", "", str(item.get("photo_id") or ""))[:8].lower()
        if len(slug) == 8 and (image_dir / f"{manhole_id}_{slug}.jpeg").exists():
            gallery_local.append({
                "url": f"{BASE_URL}manhole/image/{manhole_id}_{slug}.jpeg",
                "display_name": item.get("display_name"),
                "shot_at": item.get("shot_at"),
                "created_at": item.get("created_at"),
                "public_user_id": item.get("public_user_id"),
            })

    return (
        {**user_photo, "url": local_url, "original_url": local_url, "gallery_local": gallery_local}
        if local_url else None
    )


def manhole_ogp_dir(output_dir: Path) -> Optional[Path]:
    """Detect pre-generated per-manhole OGP directory"""
    candidate = output_dir / "assets" / "ogp" / "manholes"
    return candidate if candidate.is_dir() else None


def generate_all_pages(
    manholes: list[dict],
    photos: dict[str, dict],
    pokemon_meta: dict[str, dict],
    output_dir: Path,
    image_dir: Path,
    ja_to_slug: dict[str, str] | None = None,
    design_spots: list[dict] | None = None,
    trips: dict[str, dict] | None = None,
) -> tuple[int, int, int]:
    """Generate HTML pages for all manholes.

    trips: マンホールID → /trip/ エリア（generate_trip_pages.trips_by_manhole）。

    Returns:
        (total_generated, photos_applied, photos_missing)
    """
    total = 0
    photos_applied = 0
    photos_missing = 0

    ogp_dir = manhole_ogp_dir(output_dir)
    if ogp_dir:
        logger.info("Per-manhole OGP directory found: %s", ogp_dir)
    else:
        logger.info("No per-manhole OGP directory — using default og:image")

    # Build cross-manhole indexes once
    index = RelatedIndex(manholes)

    # 市区町村ページがある自治体（県の一部を占める3枚以上）。判定は municipalities.py に一本化
    municipality_paths = municipality_page_paths(manholes)

    id_to_image_url = local_image_urls(manholes, image_dir)

    for manhole in manholes:
        manhole_id = str(manhole.get("id", "")).strip()
        if not manhole_id:
            logger.warning("Skipping manhole with missing ID")
            continue

        photo = page_photo(manhole_id, photos, image_dir, id_to_image_url)
        if photo:
            photos_applied += 1
        else:
            photos_missing += 1
            logger.debug(f"No local image for manhole {manhole_id}")

        prefecture = manhole.get("prefecture", "")
        lat = manhole.get("lat")
        lng = manhole.get("lng")
        rel = index.related(manhole)

        # Nearby design manholes (gundam / character / 写真館投稿)
        nearby_design: list[tuple[dict, float]] = []
        if lat is not None and lng is not None and design_spots:
            for spot in design_spots:
                d = haversine(float(lat), float(lng), spot["lat"], spot["lng"])
                if d <= DESIGN_NEARBY_RADIUS_KM:
                    nearby_design.append((spot, d))
            nearby_design.sort(key=lambda x: x[1])
            nearby_design = nearby_design[:DESIGN_NEARBY_MAX]

        html = generate_html(
            manhole, photo, pokemon_meta, rel["nearby"], rel["same_pref"], rel["pref_total"], rel["same_pokemon"],
            id_to_image_url,
            city_total=rel["city_total"], same_pokemon_total=rel["same_pokemon_total"],
            nearby_count=rel["nearby_count"],
            ogp_dir=ogp_dir, ja_to_slug=ja_to_slug,
            nearby_design=nearby_design,
            municipality_path=municipality_paths.get((prefecture, municipality_label(manhole))),
            trip=(trips or {}).get(manhole_id),
        )

        page_dir = output_dir / "manholes" / manhole_id
        page_dir.mkdir(parents=True, exist_ok=True)

        index_file = page_dir / "index.html"
        index_file.write_text(html, encoding="utf-8")

        total += 1

    return total, photos_applied, photos_missing


def _load_trips(manholes: list[dict]) -> dict[str, dict]:
    """/trip/ のエリア（dataset/trip_areas.json）と所要時間の集計から、蓋ごとのエリアを引く。"""
    try:
        from apps.scraper.generate_trip_pages import trips_by_manhole
        from apps.scraper.visit_durations import load_durations, load_trip_areas
    except ModuleNotFoundError as exc:
        if exc.name != "apps":
            raise
        from generate_trip_pages import trips_by_manhole
        from visit_durations import load_durations, load_trip_areas
    return trips_by_manhole(manholes, load_trip_areas(), load_durations())


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--manholes",
        default="docs/pokefuta.ndjson",
        help="Path to manholes NDJSON file"
    )
    parser.add_argument(
        "--photos",
        default="docs/latest-manhole-photos.json",
        help="Path to photos JSON file"
    )
    parser.add_argument(
        "--pokemon",
        default="docs/pokemon_metadata.json",
        help="Path to Pokemon metadata JSON file"
    )
    parser.add_argument(
        "--image-dir",
        default="dataset/manhole/image",
        help="Directory containing {id}_latest.jpeg local images"
    )
    parser.add_argument(
        "--gundam",
        default="docs/gmanhole.ndjson",
        help="Path to gundam manholes NDJSON file"
    )
    parser.add_argument(
        "--character-manholes",
        default="dataset/aichi_character_manholes.ndjson",
        help="Path to character manholes NDJSON file"
    )
    parser.add_argument(
        "--design-submissions",
        default="docs/design_manholes.ndjson",
        help="Path to pokefuta.com design-manhole submissions NDJSON file"
    )
    parser.add_argument(
        "--output",
        default="dist",
        help="Output directory (will create manholes/ subdirectory)"
    )
    parser.add_argument(
        "--log-level",
        default="INFO",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        help="Logging level"
    )

    args = parser.parse_args()

    logging.basicConfig(
        level=getattr(logging, args.log_level),
        format="%(levelname)s: %(message)s"
    )

    manholes = load_manholes(Path(args.manholes))
    if not manholes:
        logger.error("No manholes loaded, exiting")
        return 1

    photos = load_photos(Path(args.photos))
    pokemon_meta = load_pokemon_metadata(Path(args.pokemon))
    try:
        _raw_pokemon = json.loads(Path(args.pokemon).read_text(encoding="utf-8")) if Path(args.pokemon).exists() else []
    except (json.JSONDecodeError, OSError) as e:
        logger.warning(f"Could not load pokemon metadata for slug map: {e}")
        _raw_pokemon = []
    ja_to_slug = build_ja_to_slug(_raw_pokemon)

    design_spots = load_design_spots(
        Path(args.gundam),
        Path(args.character_manholes),
        Path(args.design_submissions),
    )

    output_dir = Path(args.output)
    output_dir.mkdir(parents=True, exist_ok=True)

    total, photos_applied, photos_missing = generate_all_pages(
        manholes, photos, pokemon_meta, output_dir, Path(args.image_dir),
        ja_to_slug=ja_to_slug, design_spots=design_spots,
        trips=_load_trips(manholes),
    )

    print(f"[generate_manhole_pages] total manholes: {len(manholes)}")
    print(f"[generate_manhole_pages] generated manhole pages: {total}")
    print(f"[generate_manhole_pages] photo applied: {photos_applied}")
    print(f"[generate_manhole_pages] photo missing: {photos_missing}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
