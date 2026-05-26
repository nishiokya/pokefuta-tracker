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
import sys
from pathlib import Path
from typing import Any, Optional
from urllib.parse import quote, urlparse
from xml.sax.saxutils import escape

sys.path.insert(0, str(Path(__file__).parent))
from generate_pokemon_pages import _FORM_PREFIX, _normalize_katakana  # noqa: E402

# Constants
BASE_URL = "https://data.pokefuta.com/"
GA_MEASUREMENT_ID = "G-K18NR4GZG2"


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
    """Load Pokemon metadata indexed by Japanese name."""
    if not path.exists():
        logger.warning(f"Pokemon metadata file not found: {path}")
        return {}

    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        # Index by Japanese name for quick lookup
        metadata = {}
        for pokemon in data:
            if isinstance(pokemon, dict):
                names = pokemon.get("names", {})
                ja_name = names.get("ja", "")
                if ja_name:
                    metadata[ja_name] = pokemon

        logger.info(f"Loaded metadata for {len(metadata)} Pokemon")
        return metadata
    except json.JSONDecodeError as e:
        logger.error(f"Failed to parse Pokemon metadata: {e}")
        return {}


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
    pref = manhole.get("prefecture", "")
    city = manhole.get("city", "")
    pokes = "・".join(filter_pokemons(manhole.get("pokemons", []))) or "ポケモン"
    location = f"{pref}{city}" if (pref or city) else manhole.get("title", "")
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
) -> str:
    """Generate complete HTML for a manhole detail page."""
    manhole_id = str(manhole.get("id", "")).strip()
    prefecture = manhole.get("prefecture", "")
    city = manhole.get("city", "")
    address = manhole.get("address", "")
    building = manhole.get("building", "")
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

    title = f"{prefecture}{city}のポケふた｜{pokemon_text} | data.pokefuta.com"

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
        _og_title = f"{_top_label}｜{city_label}のポケふた（{pokemon_label}）｜ポケふたマップ"
        _og_desc = f"{_top_label}！{prefecture}{city}に設置されている{pokemon_label}のポケふた。場所・写真・地図で確認できます。"
        _tw_title = f"{_top_label}｜{city_label}のポケふた（{pokemon_label}）"
        _tw_desc = f"{_top_label}！{prefecture}{city}のポケふたを地図で確認できます。"
    else:
        _og_title = f"{city_label}のポケふた｜{pokemon_label}｜ポケふたマップ"
        _og_desc = f"{prefecture}{city}に設置されている{pokemon_label}のポケふた。場所・写真・地図で確認できます。"
        _tw_title = f"{city_label}のポケふた｜{pokemon_label}"
        _tw_desc = f"{prefecture}{city}のポケふたを地図で確認できます。"

    h1 = f"{prefecture}{city}のポケふた"
    if pokemons:
        h1 += f"（{pokemon_text}）"

    canonical_url = f"{BASE_URL}manholes/{quote(manhole_id)}/"
    map_url = f"{BASE_URL}?manhole={quote(manhole_id)}"
    pref_url = f"{BASE_URL}?pref={quote(prefecture)}"

    # _js_json() serializes values for safe embedding inside <script> blocks:
    # json.dumps handles quotes/backslashes; the </  → <\/ replacement prevents
    # premature </script> tag closure from scraped data values.
    manhole_id_js = _js_json(manhole_id)
    prefecture_js = _js_json(prefecture)
    city_js = _js_json(city)

    # _attr_json() serializes dicts as JSON with " escaped to &quot; so they
    # are safe inside HTML double-quoted onclick attributes.
    onclick_params = _attr_json(
        {"manhole_id": manhole_id, "prefecture": prefecture, "city": city}
    )

    # Source-differentiated params for Google Maps — same event name but
    # distinguishable in GA4 by where the tap came from.
    _base = {"manhole_id": manhole_id, "prefecture": prefecture, "city": city}
    gmaps_onclick_hero  = _attr_json({**_base, "source": "hero"})
    gmaps_onclick_links = _attr_json({**_base, "source": "links"})

    # Build Pokemon info with metadata
    pokemon_info_html = ""
    if pokemons:
        pokemon_info_html = "<section class='pokemon-section section-card'><h2>登場ポケモン</h2><div class='pokemon-list'>"
        for poke_name in pokemons:
            meta = pokemon_meta.get(poke_name, {})
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

    hero_photo_html = (
        f"<a class='hero-photo-placeholder' href='https://pokefuta.com/visits'"
        f" target='_blank' rel='noopener noreferrer'"
        f" onclick=\"trackEvent('click_photo_upload_placeholder', {_attr_json({'manhole_id': manhole_id, 'prefecture': prefecture, 'city': city, 'has_photo': False})})\">"
        f"<span class='placeholder-camera' aria-hidden='true'>📷</span>"
        f"<span class='placeholder-title'>まだ写真がありません</span>"
        f"<span class='placeholder-sub'>最初の旅写真を投稿する</span>"
        f"</a>"
    )

    if photo_url:
        og_image = photo_url

        raw_name = photo.get("display_name") or ""
        display_name = str(raw_name)[:20] if raw_name else ""

        raw_comment = photo.get("comment") or ""
        comment = " ".join(str(raw_comment).split())  # normalize whitespace
        if len(comment) > 100:
            comment = comment[:97] + "…"

        shot_date = ""
        shot_at_raw = photo.get("shot_at", "")
        if isinstance(shot_at_raw, str) and shot_at_raw:
            try:
                dt = datetime.datetime.fromisoformat(shot_at_raw.replace("Z", "+00:00"))
                shot_date = f"{dt.year}年{dt.month}月{dt.day}日"
            except (ValueError, TypeError):
                pass

        credit_parts = []
        if display_name:
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
            f"<img src=\"{escape(photo_url)}\" alt=\"{escape(h1)}の写真\" loading=\"lazy\">"
            f"{credit_html}"
            f"{comment_html}"
            f"</div>"
        )

    # Per-manhole generated OGP takes priority over photo URL
    _ogp_path = (ogp_dir / f"{manhole_id}.png") if ogp_dir else None
    if _ogp_path is not None and _ogp_path.exists():
        og_image = f"{BASE_URL}assets/ogp/manholes/{manhole_id}.png"

    # HERO card: region label
    region_parts = [p for p in [prefecture, city] if p]
    region_html = "".join(f"<span>{escape(r)}</span>" for r in region_parts)
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
        badges.append(f"<span class='hero-badge hero-badge-title'>{label}</span>")
    # Stats badges with suppression rules (§2.3)
    suppress_pref = title_keys & {"only_in_pref", "unique_pokemon"}
    suppress_nearby = "lone" in title_keys
    if pref_total > 0 and prefecture and not suppress_pref:
        badges.append(f"<span class='hero-badge'>{escape(prefecture)} {pref_total}枚</span>")
    if city_total >= 2 and city:
        badges.append(f"<span class='hero-badge'>{escape(city)} {city_total}枚</span>")
    if same_pokemon_total > 0:
        badges.append(f"<span class='hero-badge'>同じポケモン {same_pokemon_total}枚</span>")
    if nearby_count > 0 and not suppress_nearby:
        badges.append(f"<span class='hero-badge'>30km以内に{nearby_count}件</span>")
    stats_html = f"<div class='hero-stats'>{''.join(badges)}</div>" if badges else ""

    # HERO card: share JS data (Python-serialized to avoid injection)
    _title_hashtags = " ".join(t["hashtag"] for t in titles if t.get("hashtag"))
    _base_hashtags = f"{_title_hashtags} #ポケふた #ポケモンマンホール".strip()
    if has_photo_bool and pokemons:
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

    jsonld_str = json.dumps(jsonld, ensure_ascii=False, indent=2)

    # Links grid: external + internal + photo upload (移設統合)
    _pref_site_raw = manhole.get("prefecture_site_url", "") or ""
    _pref_parsed = urlparse(_pref_site_raw)
    prefecture_site_url = _pref_site_raw if _pref_parsed.scheme in ("http", "https") else ""
    link_cards: list[str] = []
    # Share first: X / LINE / Web Share
    _share_onclick = _attr_json({"manhole_id": manhole_id, "prefecture": prefecture, "city": city})
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
    # Navigation: Official / Prefecture / Same Pref / National Map
    if has_official_url:
        link_cards.append(
            f"<a class='link-card link-card--official' href=\"{escape(detail_url)}\""
            f" target=\"_blank\" rel=\"noopener noreferrer\""
            f" onclick=\"trackEvent('click_official_site', {onclick_params})\">"
            f"{_icon('icon-link-official', 'link-card-icon')}<span>公式サイト</span></a>"
        )
    if prefecture_site_url:
        link_cards.append(
            f"<a class='link-card link-card--pref-site' href=\"{escape(prefecture_site_url)}\""
            f" target=\"_blank\" rel=\"noopener noreferrer\">"
            f"{_icon('icon-link-prefecture', 'link-card-icon')}<span>{escape(prefecture)}の公式</span></a>"
        )
    if prefecture:
        link_cards.append(
            f"<a class='link-card link-card--internal' href=\"{escape(pref_url)}\">"
            f"{_icon('icon-detail-same-pref', 'link-card-icon')}<span>同じ都道府県</span></a>"
        )
    _map_onclick = _attr_json({"manhole_id": manhole_id, "source": "links_map"})
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

    # Nearby manholes section
    nearby_html = ""
    if nearby:
        nearby_html = (
            f"<section class='nearby-section section-card'>"
            f"<h2>{_icon('icon-detail-nearby', 'icon-lg')} 次に寄れるポケふた</h2>"
            f"<ul class='related-list related-list--cards'>"
        )
        for other, dist in nearby:
            dist_str = f"{dist:.1f} km"
            _nearby_params = _attr_json({
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
    _follow_onclick = _attr_json({"manhole_id": manhole_id, "prefecture": prefecture})
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
    _back_onclick = _attr_json({"manhole_id": manhole_id, "source": "back_btn"})
    back_btn_html = (
        f"<a href=\"{escape(map_url)}\" class=\"back-btn\""
        f" onclick=\"trackEvent('click_map_internal', {_back_onclick})\">"
        f"← 全国マップへ戻る</a>"
    )

    # Hero photo upload CTA
    _photo_event = "click_photo_upload" if has_photo_bool else "click_photo_upload_placeholder"
    _photo_label = "写真を投稿" if has_photo_bool else "最初の旅写真を投稿する"
    _photo_cta_onclick = _attr_json({"manhole_id": manhole_id, "prefecture": prefecture, "city": city, "has_photo": has_photo_bool})

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
    <div class="hero-region">{region_html}</div>
    {region_en_html}
    <h1 class="hero-title">{escape(h1)}</h1>
    {pokemon_tags_html}
    {stats_html}
    <div class="hero-actions">
      <a class="btn-photo-upload" href="https://pokefuta.com/visits" target="_blank" rel="noopener noreferrer" onclick="trackEvent('{_photo_event}', {_photo_cta_onclick})">{_icon('icon-link-photo', 'action-icon')}<span>{escape(_photo_label)}</span></a>
    </div>
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
  <meta name="robots" content="index,follow">
  <link rel="canonical" href="{escape(canonical_url)}">

  <meta property="og:type" content="article">
  <meta property="og:locale" content="ja_JP">
  <meta property="og:site_name" content="ポケふたマップ">
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
  <script async src="https://www.googletagmanager.com/gtag/js?id={GA_MEASUREMENT_ID}"></script>
  <script>
    window.dataLayer = window.dataLayer || [];
    function gtag(){{dataLayer.push(arguments);}}
    gtag('js', new Date());
    gtag('config', '{GA_MEASUREMENT_ID}', {{
      'page_path': '/manholes/' + {manhole_id_js} + '/'
    }});
    gtag('event', 'view_manhole_detail', {{
      manhole_id: {manhole_id_js},
      prefecture: {prefecture_js},
      city: {city_js},
      pokemon_count: {len(pokemons)},
      has_photo: {has_photo_js}
    }});

    function trackEvent(action, params) {{
      gtag('event', action, params);
    }}

    function shareManhole() {{
      var _sp = {{
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
    * {{
      box-sizing: border-box;
      margin: 0;
      padding: 0;
    }}

    body {{
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif;
      line-height: 1.6;
      color: #333;
      background: #fff8ec;
      padding: 16px;
    }}

    .container {{
      max-width: 800px;
      margin: 0 auto;
      background: white;
      border-radius: 12px;
      padding: 20px;
      box-shadow: 0 4px 16px rgba(0,0,0,0.08);
    }}

    h1 {{
      font-size: 24px;
      margin-bottom: 16px;
      color: #1a1a1a;
    }}

    h2 {{
      font-size: 20px;
      margin: 24px 0 12px;
      padding-bottom: 8px;
      border-bottom: 2px solid #e0e0e0;
    }}

    h3 {{
      font-size: 18px;
      margin-bottom: 8px;
    }}

    .cta-primary {{
      display: block;
      background: #dc3545;
      color: white;
      text-align: center;
      padding: 16px 24px;
      border-radius: 8px;
      text-decoration: none;
      font-size: 18px;
      font-weight: bold;
      margin: 24px 0;
      transition: background 0.2s;
    }}

    .cta-primary:hover {{
      background: #c82333;
    }}

    .cta-secondary {{
      display: inline-block;
      background: #007bff;
      color: white;
      padding: 12px 20px;
      border-radius: 6px;
      text-decoration: none;
      margin: 8px 8px 8px 0;
      transition: background 0.2s;
    }}

    .cta-secondary:hover {{
      background: #0056b3;
    }}

    .photo-section img {{
      max-width: 100%;
      height: auto;
      border-radius: 8px;
      margin-top: 12px;
    }}

    .pokemon-list {{
      display: grid;
      grid-template-columns: repeat(auto-fill, minmax(200px, 1fr));
      gap: 16px;
      margin-top: 12px;
    }}

    .pokemon-card {{
      background: #f8f9fa;
      padding: 16px;
      border-radius: 8px;
      border: 1px solid #e0e0e0;
    }}
    .pokemon-card h3 a {{
      color: inherit;
      text-decoration: none;
    }}
    .pokemon-card h3 a:hover, .pokemon-card h3 a:focus {{
      text-decoration: underline;
    }}

    .pokemon-card .en-name {{
      color: #666;
      font-size: 14px;
    }}

    .pokemon-card .types,
    .pokemon-card .generation {{
      font-size: 14px;
      margin-top: 4px;
    }}

    dl {{
      display: grid;
      grid-template-columns: 5em 1fr;
      gap: 3px 8px;
      margin-top: 8px;
    }}

    dt {{
      font-weight: bold;
      margin-top: 0;
    }}

    dd {{
      margin-left: 0;
      color: #555;
    }}

    .official-link {{
      margin-top: 16px;
    }}

    .official-link a {{
      color: #007bff;
      text-decoration: none;
    }}

    .official-link a:hover {{
      text-decoration: underline;
    }}

    footer {{
      margin-top: 32px;
      padding-top: 16px;
      border-top: 1px solid #e0e0e0;
      text-align: center;
      color: #666;
      font-size: 14px;
    }}

    .related-list {{
      list-style: none;
      margin-top: 0;
      display: flex;
      flex-direction: column;
      gap: 10px;
    }}

    .related-list a {{
      color: #1a6fd4;
      text-decoration: none;
      font-weight: 500;
      flex: 1;
    }}

    .related-list a:hover {{
      text-decoration: underline;
    }}

    .related-list li {{
      display: flex;
      justify-content: space-between;
      align-items: center;
      padding: 10px 14px;
      background: #fafaf8;
      border-radius: 8px;
      border: 1px solid #e8e3db;
      flex-wrap: wrap;
      gap: 4px;
      transition: background 0.15s;
    }}

    .related-list li:hover {{
      background: #f3ede4;
    }}

    .distance {{
      font-size: 13px;
      color: #666;
      white-space: nowrap;
    }}

    /* HERO card */
    .hero-card {{
      border-radius: 16px;
      overflow: hidden;
      border: 1px solid #e8d8c0;
      margin-bottom: 24px;
      box-shadow: 0 4px 20px rgba(0,0,0,0.10);
    }}

    .hero-photo img {{
      width: 100%;
      aspect-ratio: 4 / 3;
      object-fit: cover;
      display: block;
    }}

    .hero-photo-placeholder {{
      width: 100%;
      aspect-ratio: 4 / 3;
      background: linear-gradient(135deg, #f5ede0 0%, #ede0cf 100%);
      border: 2px dashed #d4b896;
      display: flex;
      flex-direction: column;
      align-items: center;
      justify-content: center;
      gap: 10px;
      text-decoration: none;
      cursor: pointer;
      transition: background 0.15s, transform 0.15s, box-shadow 0.15s;
    }}

    .hero-photo-placeholder:hover {{
      background: linear-gradient(135deg, #eeddd0 0%, #e4d3be 100%);
      transform: translateY(-1px);
      box-shadow: 0 4px 16px rgba(180, 120, 60, 0.12);
    }}

    .placeholder-camera {{
      font-size: 40px;
      opacity: 0.6;
      display: block;
    }}

    .placeholder-title {{
      font-size: 14px;
      font-weight: 600;
      color: #8a6440;
    }}

    .placeholder-sub {{
      font-size: 13px;
      color: #b08050;
      text-decoration: underline;
      text-underline-offset: 3px;
    }}

    .hero-body {{
      padding: 20px 20px 24px;
    }}

    .hero-region {{
      font-size: 13px;
      color: #888;
      margin-bottom: 6px;
      letter-spacing: 0.02em;
    }}

    .hero-region span + span::before {{
      content: " › ";
    }}

    h1.hero-title {{
      font-size: 21px;
      font-weight: 700;
      margin-bottom: 14px;
      line-height: 1.45;
      color: #1a1a1a;
      letter-spacing: -0.01em;
    }}

    .hero-pokemon-tags {{
      display: flex;
      flex-wrap: wrap;
      gap: 6px;
      margin-bottom: 14px;
    }}

    .hero-tag {{
      background: #fff8e1;
      border: 1px solid #f9c940;
      border-radius: 20px;
      padding: 3px 11px;
      font-size: 13px;
      font-weight: 500;
      color: #7a5c00;
    }}

    a.hero-tag {{
      text-decoration: none;
      color: #7a5c00;
    }}

    a.hero-tag:hover {{
      background: #fde98a;
      border-color: #e6b800;
    }}

    .hero-stats {{
      display: flex;
      flex-wrap: wrap;
      gap: 7px;
      margin-bottom: 18px;
    }}

    .hero-badge {{
      background: #eef0ff;
      border: 1px solid #b8c0f0;
      border-radius: 20px;
      padding: 4px 13px;
      font-size: 12px;
      font-weight: 600;
      color: #3a4fc7;
      letter-spacing: 0.01em;
    }}

    .hero-actions {{
      display: grid;
      grid-template-columns: 1fr;
      gap: 10px;
    }}

    .btn-photo-upload {{
      display: flex;
      align-items: center;
      justify-content: center;
      gap: 10px;
      width: 100%;
      min-height: 52px;
      border-radius: 14px;
      padding: 14px 16px;
      font-size: 15px;
      font-weight: 700;
      letter-spacing: 0.01em;
      background: #fff0f3;
      color: #c0394b;
      border: 1.5px solid #f5c0ca;
      text-decoration: none;
      cursor: pointer;
      box-shadow: 0 1px 4px rgba(0,0,0,0.07);
      transition: background 0.15s, box-shadow 0.15s, transform 0.15s;
    }}

    .btn-photo-upload:hover {{
      background: #ffe4ea;
      box-shadow: 0 3px 10px rgba(192,57,75,0.14);
      transform: translateY(-1px);
    }}

    .action-icon {{
      width: 36px;
      height: 36px;
      display: block;
      flex-shrink: 0;
    }}

    .section-card {{
      background: #fff;
      border: 1px solid #ede8df;
      border-radius: 10px;
      padding: 16px 18px;
      margin-bottom: 12px;
      box-shadow: 0 1px 4px rgba(0,0,0,0.05);
    }}

    .section-card h2 {{
      font-size: 15px;
      font-weight: 600;
      margin: 0 0 10px;
      padding-bottom: 8px;
      border-bottom: 1px solid #ede8df;
      color: #444;
    }}

    .link-grid {{
      display: grid;
      grid-template-columns: repeat(3, 1fr);
      gap: 8px;
    }}

    .link-card {{
      display: flex;
      flex-direction: column;
      justify-content: center;
      align-items: center;
      min-height: 64px;
      border-radius: 12px;
      padding: 10px 6px;
      text-align: center;
      text-decoration: none;
      font-size: 12px;
      font-weight: 600;
      line-height: 1.4;
      gap: 4px;
      border: 1px solid #e6e0d6;
      box-shadow: 0 1px 4px rgba(0,0,0,0.05);
      transition: transform 0.15s, box-shadow 0.15s;
    }}

    .link-card:hover {{
      transform: translateY(-1px);
      box-shadow: 0 3px 8px rgba(0,0,0,0.10);
    }}

    .link-card span {{ display: block; }}

    .link-card--official   {{ background: #fff4f0; color: #c0392b; border-color: #f5c0b0; }}
    .link-card--pref-site  {{ background: #f0fff4; color: #1a6b3c; border-color: #b0e8c8; }}
    .link-card--internal   {{ background: #f8f4ff; color: #5a3fa0; border-color: #d8c8f5; }}
    .link-card--share-x    {{ background: #f5f5f5; color: #444; border-color: #d8d8d8; }}
    .link-card--share-line {{ background: #f0faf5; color: #217a48; border-color: #b0e0c8; }}
    .link-card--share      {{ background: #f8f4ff; color: #5a3fa0; border-color: #d8c8f5; cursor: pointer; }}

    .related-list--cards li {{
      display: flex;
      gap: 12px;
      align-items: center;
      border-radius: 12px;
      padding: 10px 12px;
      background: #fff;
      border: 1px solid #e8e3db;
      box-shadow: 0 1px 3px rgba(0,0,0,0.04);
      transition: background 0.15s;
    }}

    .related-list--cards li:hover {{
      background: #f8f4ee;
    }}

    .icon {{
      display: inline-block;
      width: 18px;
      height: 18px;
      vertical-align: middle;
      flex-shrink: 0;
    }}

    .icon-sm {{ width: 14px; height: 14px; }}
    .icon-lg {{ width: 22px; height: 22px; }}
    .link-card-icon {{ width: 38px; height: 38px; display: block; }}

    .related-card-thumb {{
      width: 60px;
      height: 60px;
      flex-shrink: 0;
      border-radius: 8px;
      overflow: hidden;
      background: #f0ebe3;
    }}

    .related-card-thumb img {{
      width: 100%;
      height: 100%;
      object-fit: cover;
      display: block;
    }}

    .related-card-body {{
      flex: 1;
      display: flex;
      align-items: center;
      gap: 5px;
      min-width: 0;
    }}

    .related-card-body a {{
      min-width: 0;
      overflow: hidden;
      text-overflow: ellipsis;
      white-space: nowrap;
    }}

    @media (max-width: 600px) {{
      body {{
        padding: 6px;
        background: #fff8ec;
      }}

      .container {{
        padding: 12px;
        border-radius: 10px;
      }}

      .hero-card {{
        border-radius: 12px;
      }}

      .hero-body {{
        padding: 14px 14px 18px;
      }}

      h1.hero-title {{
        font-size: 18px;
      }}

      .btn-photo-upload {{
        font-size: 16px;
        min-height: 56px;
      }}

      .section-card {{
        padding: 14px;
        border-radius: 8px;
      }}

      .pokemon-list {{
        grid-template-columns: 1fr;
      }}
    }}

    .pokemon-card .multilingual-names {{
      font-size: 13px;
      color: #666;
      margin-top: 2px;
    }}

    .hero-region-en {{
      font-size: 12px;
      color: #aaa;
      margin-bottom: 8px;
      letter-spacing: 0.03em;
    }}

    .hero-photo {{
      position: relative;
    }}

    .photo-credit {{
      position: absolute;
      bottom: 8px;
      right: 8px;
      background: rgba(0,0,0,0.55);
      color: #fff;
      font-size: 11px;
      padding: 3px 8px;
      border-radius: 20px;
      display: flex;
      gap: 6px;
      align-items: center;
    }}

    .photo-comment {{
      position: absolute;
      bottom: 0;
      left: 0;
      right: 0;
      background: rgba(0,0,0,0.50);
      color: #fff;
      font-size: 13px;
      padding: 8px 12px;
      display: -webkit-box;
      -webkit-line-clamp: 2;
      -webkit-box-orient: vertical;
      overflow: hidden;
    }}

    .hero-badge-new {{
      background: #fff0f0;
      border-color: #ff6b6b;
      color: #c0392b;
    }}

    .back-btn {{
      display: inline-flex;
      align-items: center;
      background: #fff;
      border: 1px solid #e0d8cc;
      border-radius: 20px;
      padding: 10px 18px;
      font-size: 14px;
      font-weight: 500;
      color: #5b4a36;
      text-decoration: none;
      margin-bottom: 12px;
      transition: background 0.15s;
    }}

    .back-btn:hover {{
      background: #f8f3eb;
    }}

    .visit-cta {{
      display: flex;
      align-items: center;
      gap: 14px;
      background: #fff;
      border: 1px solid #d8edd8;
      border-radius: 20px;
      padding: 16px 18px;
      text-decoration: none;
      box-shadow: 0 1px 4px rgba(0,0,0,0.06);
      margin-bottom: 12px;
      transition: box-shadow 0.15s, transform 0.15s;
    }}

    .visit-cta:hover {{
      transform: translateY(-1px);
      box-shadow: 0 3px 10px rgba(0,0,0,0.10);
    }}

    .visit-cta-icon {{
      width: 44px;
      height: 44px;
      border-radius: 50%;
      background: #ddf4e7;
      flex-shrink: 0;
      display: flex;
      align-items: center;
      justify-content: center;
    }}

    .visit-cta-map-icon {{
      width: 26px;
      height: 26px;
      display: block;
    }}

    .visit-cta-body {{
      display: flex;
      flex-direction: column;
      gap: 2px;
    }}

    .visit-cta-main {{
      font-size: 15px;
      font-weight: 700;
      color: #1a1a1a;
    }}

    .visit-cta-sub {{
      font-size: 12px;
      color: #777;
    }}

    .pokemon-same-link {{
      display: block;
      font-size: 12px;
      color: #1a6fd4;
      text-decoration: none;
      margin-top: 6px;
    }}

    .pokemon-same-link:hover {{
      text-decoration: underline;
    }}

    .follow-section {{
      margin: 16px 0;
    }}

    .follow-x-card {{
      display: block;
      background: #000;
      color: #fff;
      text-decoration: none;
      border-radius: 12px;
      padding: 16px 20px;
      transition: background 0.15s, transform 0.15s;
    }}

    .follow-x-card:hover {{
      background: #1a1a1a;
      transform: translateY(-1px);
    }}

    .follow-x-title {{
      font-size: 14px;
      font-weight: 700;
      margin-bottom: 4px;
    }}

    .follow-x-body {{
      font-size: 12px;
      color: #aaa;
      margin-bottom: 8px;
      line-height: 1.4;
    }}

    .follow-x-cta {{
      font-size: 13px;
      font-weight: 600;
      color: #1d9bf0;
    }}
  </style>
</head>
<body>
  {_SVG_DEFS}
  <div class="container">
    {back_btn_html}

    {hero_card_html}

    {visit_cta_html}

    {location_html}

    {pokemon_info_html}

    {nearby_html}

    {same_pokemon_html}

    {pref_section_html}

    {links_grid_html}

    {follow_x_html}

    <footer>
      <p>&copy; 2024-{current_year} data.pokefuta.com | ポケふた情報はポケモン公式サイトを参照しています</p>
    </footer>
  </div>
</body>
</html>
"""

    return html


def generate_all_pages(
    manholes: list[dict],
    photos: dict[str, dict],
    pokemon_meta: dict[str, dict],
    output_dir: Path,
    image_dir: Path,
    ja_to_slug: dict[str, str] | None = None,
) -> tuple[int, int, int]:
    """Generate HTML pages for all manholes.

    Returns:
        (total_generated, photos_applied, photos_missing)
    """
    total = 0
    photos_applied = 0
    photos_missing = 0

    # Detect pre-generated per-manhole OGP directory
    _ogp_candidate = output_dir / "assets" / "ogp" / "manholes"
    ogp_dir: Optional[Path] = _ogp_candidate if _ogp_candidate.is_dir() else None
    if ogp_dir:
        logger.info("Per-manhole OGP directory found: %s", ogp_dir)
    else:
        logger.info("No per-manhole OGP directory — using default og:image")

    # Build cross-manhole indexes once
    pref_index: dict[str, list[dict]] = {}
    for m in manholes:
        pref = m.get("prefecture", "")
        if pref:
            pref_index.setdefault(pref, []).append(m)

    city_index: dict[str, list[dict]] = {}
    for m in manholes:
        pref = m.get("prefecture", "")
        city = m.get("city", "")
        if pref or city:
            city_index.setdefault(f"{pref}_{city}", []).append(m)

    pokemon_index: dict[str, list[dict]] = {}
    for m in manholes:
        for pk in filter_pokemons(m.get("pokemons", [])):
            pokemon_index.setdefault(pk, []).append(m)

    # Build GitHub Pages-safe image URL map (local files only; no Cloudflare URLs)
    id_to_image_url: dict[str, str] = {}
    for m in manholes:
        mid = str(m.get("id", "")).strip()
        if mid and (image_dir / f"{mid}_latest.jpeg").exists():
            id_to_image_url[mid] = f"{BASE_URL}manhole/image/{mid}_latest.jpeg"

    for manhole in manholes:
        manhole_id = str(manhole.get("id", "")).strip()
        if not manhole_id:
            logger.warning("Skipping manhole with missing ID")
            continue

        # Use local image only; merge user-photo metadata for credit overlay
        local_url = id_to_image_url.get(manhole_id)
        norm_id = normalize_id(manhole_id)
        user_photo = photos.get(norm_id) or {}
        photo: Optional[dict] = (
            {**user_photo, "url": local_url, "original_url": local_url}
            if local_url else None
        )

        if photo:
            photos_applied += 1
        else:
            photos_missing += 1
            logger.debug(f"No local image for manhole {manhole_id}")

        prefecture = manhole.get("prefecture", "")
        city = manhole.get("city", "")
        lat = manhole.get("lat")
        lng = manhole.get("lng")

        # Nearby manholes (requires lat/lng)
        nearby: list[tuple[dict, float]] = []
        if lat is not None and lng is not None:
            for other in manholes:
                if str(other.get("id", "")) == manhole_id:
                    continue
                olat, olng = other.get("lat"), other.get("lng")
                if olat is None or olng is None:
                    continue
                dist = haversine(float(lat), float(lng), float(olat), float(olng))
                nearby.append((other, dist))
            nearby.sort(key=lambda x: x[1])
        nearby = [(m, d) for m, d in nearby if d <= 30.0]
        nearby_count = len(nearby)
        nearby = nearby[:5]

        # Same prefecture manholes (stable sort: city then id)
        same_pref_all = [
            m for m in pref_index.get(prefecture, [])
            if str(m.get("id", "")) != manhole_id
        ]
        same_pref = sorted(
            same_pref_all,
            key=lambda m: (m.get("city", ""), str(m.get("id", "")))
        )[:20]
        pref_total = len(pref_index.get(prefecture, []))

        # City total
        city_total = len(city_index.get(f"{prefecture}_{city}", []))

        # Same pokemon manholes (deduplicated: one entry per manhole)
        seen_ids: set[str] = set()
        same_pokemon: list[dict] = []
        for pk in filter_pokemons(manhole.get("pokemons", [])):
            for other in pokemon_index.get(pk, []):
                oid = str(other.get("id", "")).strip()
                if oid != manhole_id and oid not in seen_ids:
                    seen_ids.add(oid)
                    same_pokemon.append(other)
        same_pokemon_total = len(seen_ids)
        same_pokemon = same_pokemon[:10]

        html = generate_html(
            manhole, photo, pokemon_meta, nearby, same_pref, pref_total, same_pokemon,
            id_to_image_url,
            city_total=city_total, same_pokemon_total=same_pokemon_total, nearby_count=nearby_count,
            ogp_dir=ogp_dir, ja_to_slug=ja_to_slug,
        )

        page_dir = output_dir / "manholes" / manhole_id
        page_dir.mkdir(parents=True, exist_ok=True)

        index_file = page_dir / "index.html"
        index_file.write_text(html, encoding="utf-8")

        total += 1

    return total, photos_applied, photos_missing


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

    output_dir = Path(args.output)
    output_dir.mkdir(parents=True, exist_ok=True)

    total, photos_applied, photos_missing = generate_all_pages(
        manholes, photos, pokemon_meta, output_dir, Path(args.image_dir),
        ja_to_slug=ja_to_slug,
    )

    print(f"[generate_manhole_pages] total manholes: {len(manholes)}")
    print(f"[generate_manhole_pages] generated manhole pages: {total}")
    print(f"[generate_manhole_pages] photo applied: {photos_applied}")
    print(f"[generate_manhole_pages] photo missing: {photos_missing}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
