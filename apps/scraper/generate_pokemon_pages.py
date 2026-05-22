#!/usr/bin/env python3
"""Generate static SEO-optimized LP pages for individual Pokemon.

Creates /pokemon/{slug}/index.html for each Pokemon that appears on at least
one active pokefuta manhole.  Each page includes title, meta description,
canonical URL, OGP tags, JSON-LD (CollectionPage), a manhole list, and CTAs.
Supports 5 languages (ja/en/zh-CN/zh-TW/ko); generates language-specific pages
under dist/{lang}/pokemon/{slug}/ (Japanese goes to dist/pokemon/{slug}/).
"""

from __future__ import annotations

import argparse
import json
import logging
from collections import defaultdict
from collections.abc import Callable
from itertools import groupby
from pathlib import Path
from urllib.parse import quote
from xml.sax.saxutils import escape

logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger(__name__)

BASE_URL = "https://data.pokefuta.com/"
GA_MEASUREMENT_ID = "G-K18NR4GZG2"
DEFAULT_OGP_IMAGE = f"{BASE_URL}assets/ogp/pokefuta_map_ogp.png"

# Short contextual descriptions explaining regional connections.
# Keeps wording soft ("イメージ", "語感", "連想") — no unsourced assertions.
# Only shown on Japanese pages (not yet translated).
POKEMON_SEO_DESCRIPTIONS: dict[str, str] = {
    "vulpix": (
        "ロコンは北海道各地を応援するポケモンとして親しまれ、"
        "キツネを連想させる姿や雪景色との相性から"
        "北海道のイメージに合うポケモンとして話題になっています。"
        "北海道内には多数のロコンのポケふたが設置されています。"
    ),
    "vulpix-alola": (
        "アローラロコンは北海道を応援するポケモンとして知られ、"
        "北海道各地に多数のポケふたが設置されています。"
        "雪や冬景色を連想させるデザインや、キツネを思わせる姿から、"
        "北海道のイメージに合うポケモンとして選ばれています。"
    ),
    "ninetales": (
        "キュウコンはロコンの進化系として知られるポケモンです。"
        "北海道をはじめ各地のポケふたでも人気があり、"
        "その優雅な姿が地域の自然景観とも相性が良いとされています。"
    ),
    "ninetales-alola": (
        "アローラキュウコンはアローラロコンの進化系として知られるポケモンです。"
        "雪や氷をイメージした姿が北海道の風景と相性が良く、"
        "冬をテーマにしたポケふたでも人気があります。"
    ),
    "slowpoke": (
        "ヤドンは香川県を応援するポケモンとして知られています。"
        "『うどん』と『ヤドン』の語感の近さでも話題になり、"
        "香川県内ではヤドンのポケふた巡りや観光企画が人気です。"
    ),
    "lapras": (
        "ラプラスは宮城県を応援するポケモンとして知られています。"
        "海を泳ぐイメージや穏やかな雰囲気が宮城県の観光や海辺の景色とも相性が良く、"
        "県内各地にラプラスのポケふたが設置されています。"
    ),
    "geodude": (
        "イシツブテは岩手県を応援するポケモンとして知られています。"
        "『いわて』と『イシツブテ』の語感の近さでも話題となり、"
        "岩手県内ではポケふたや観光企画にも登場しています。"
    ),
    "chansey": (
        "ラッキーは福島県を応援するポケモンとして知られています。"
        "『福』を連想させるイメージから、"
        "福島県内ではラッキーのポケふたや観光企画が展開されています。"
    ),
}

# Regional form prefix mapping (pokefuta data uses these prefixes)
_FORM_PREFIX: dict[str, str] = {
    "alola": "アローラ",
    "galar": "ガラル",
    "hisui": "ヒスイ",
    "paldea": "パルデア",
}

# Per-language config: name_key maps to pokemon_metadata names keys.
LANG_CONFIGS: dict[str, dict] = {
    "ja": {
        "name_key": "ja",
        "pref_key": None,  # None = use Japanese prefecture name directly
        "html_lang": "ja",
        "og_locale": "ja_JP",
        "hreflang": "ja",
        "url_prefix": "",   # → dist/pokemon/
        "form_prefixes": _FORM_PREFIX,
        "pref_joiner": "・",
    },
    "en": {
        "name_key": "en",
        "pref_key": "en",
        "html_lang": "en",
        "og_locale": "en_US",
        "hreflang": "en",
        "url_prefix": "en/",
        "form_prefixes": {"alola": "Alolan ", "galar": "Galarian ", "hisui": "Hisuian ", "paldea": "Paldean "},
        "pref_joiner": ", ",
    },
    "zh-CN": {
        "name_key": "zh-Hans",
        "pref_key": "zh-Hans",
        "html_lang": "zh-Hans",
        "og_locale": "zh_CN",
        "hreflang": "zh-Hans",
        "url_prefix": "zh-CN/",
        "form_prefixes": {"alola": "阿罗拉", "galar": "伽勒尔", "hisui": "洗翠", "paldea": "帕底亚"},
        "pref_joiner": "、",
    },
    "zh-TW": {
        "name_key": "zh-Hant",
        "pref_key": "zh-Hant",
        "html_lang": "zh-Hant",
        "og_locale": "zh_TW",
        "hreflang": "zh-TW",
        "url_prefix": "zh-TW/",
        "form_prefixes": {"alola": "阿羅拉", "galar": "伽勒爾", "hisui": "洗翠", "paldea": "帕底亞"},
        "pref_joiner": "、",
    },
    "ko": {
        "name_key": "ko",
        "pref_key": "ko",
        "html_lang": "ko",
        "og_locale": "ko_KR",
        "hreflang": "ko",
        "url_prefix": "ko/",
        "form_prefixes": {"alola": "알로라 ", "galar": "가라르 ", "hisui": "히스이 ", "paldea": "팔데아 "},
        "pref_joiner": "・",
    },
}

# UI strings per language for LP pages.
LP_STRINGS: dict[str, dict[str, str]] = {
    "ja": {
        "title_suffix": "のポケふた一覧 | 全国のポケモンマンホールマップ",
        "desc_template": "{name}が描かれた全国のポケふた（ポケモンマンホール）を地図で探せます。旅行先や現在地から近くのポケふたを見つけよう。",
        "og_title_suffix": "のポケふた一覧",
        "generation": "第{gen}世代",
        "unknown_location": "所在地不明",
        "pref_section_heading": "{pref}の{name}のポケふた",
        "pref_map_link": "{pref}の地図で見る →",
        "related_heading": "関連するポケモン",
        "count_text": "全国に <strong>{count}</strong> 枚の{name}のポケふたがあります。",
        "cta": "地図で全国のポケふたを探す →",
        "breadcrumb_aria": "パンくずリスト",
        "breadcrumb_home": "全国マップ",
        "breadcrumb_pokemon": "ポケモン一覧",
        "footer": "ポケモンマンホール全国マップ",
        "summary_0pref": "{name}のポケふたは現在{count}枚確認されています。",
        "summary_1pref": "{name}のポケふたは{pref}に{count}枚設置されています。",
        "summary_few_pref": "{name}のポケふたは{prefs}の{n}都道府県、合計{count}枚設置されています。",
        "summary_many_pref": "{name}のポケふたは全国{n}都道府県・{count}枚設置されています。{top_prefs}をはじめ、各地で出会えます。",
        "summary_travel_many": "複数の都道府県を旅行しながら巡るのもおすすめです。",
        "summary_travel_few": "設置地域を訪れながら探してみてください。",
    },
    "en": {
        "title_suffix": " Pokéfuta | Pokémon Manhole Map of Japan",
        "desc_template": "Find all Pokéfuta (Pokémon manholes) featuring {name} across Japan. Explore locations on the map from your destination or current position.",
        "og_title_suffix": " Pokéfuta",
        "generation": "Generation {gen}",
        "unknown_location": "Location unknown",
        "pref_section_heading": "{name} Pokéfuta in {pref}",
        "pref_map_link": "View {pref} on map →",
        "related_heading": "Related Pokémon",
        "count_text": "There are <strong>{count}</strong> {name} Pokéfuta nationwide.",
        "cta": "Explore all Pokéfuta on the map →",
        "breadcrumb_aria": "Breadcrumb",
        "breadcrumb_home": "Japan Map",
        "breadcrumb_pokemon": "Pokémon List",
        "footer": "Pokémon Manhole Map of Japan",
        "summary_0pref": "There are currently {count} {name} Pokéfuta confirmed.",
        "summary_1pref": "{count} {name} Pokéfuta installed in {pref}.",
        "summary_few_pref": "{name} Pokéfuta found in {n} prefectures — {prefs} — totaling {count} locations.",
        "summary_many_pref": "{name} Pokéfuta spread across {n} prefectures nationwide, {count} total. Including {top_prefs} and more.",
        "summary_travel_many": "Consider visiting multiple prefectures to find them all.",
        "summary_travel_few": "Visit the installation area to find it.",
    },
    "zh-CN": {
        "title_suffix": " 宝可梦井盖 | 日本宝可梦井盖地图",
        "desc_template": "在地图上查找日本各地绘有{name}的宝可梦井盖（Pokéfuta）。从旅游目的地或当前位置寻找附近的宝可梦井盖。",
        "og_title_suffix": " 宝可梦井盖",
        "generation": "第{gen}世代",
        "unknown_location": "位置不明",
        "pref_section_heading": "{pref}的{name}宝可梦井盖",
        "pref_map_link": "在地图上查看{pref} →",
        "related_heading": "相关宝可梦",
        "count_text": "全国共有 <strong>{count}</strong> 个{name}宝可梦井盖。",
        "cta": "在地图上查找全国宝可梦井盖 →",
        "breadcrumb_aria": "面包屑导航",
        "breadcrumb_home": "全国地图",
        "breadcrumb_pokemon": "宝可梦列表",
        "footer": "日本宝可梦井盖全国地图",
        "summary_0pref": "目前已确认{count}个{name}宝可梦井盖。",
        "summary_1pref": "{name}宝可梦井盖共{count}个，设置于{pref}。",
        "summary_few_pref": "{name}宝可梦井盖遍布{prefs}等{n}个都道府县，合计{count}个。",
        "summary_many_pref": "{name}宝可梦井盖遍布全国{n}个都道府县，共{count}个。包括{top_prefs}等地。",
        "summary_travel_many": "推荐前往多个都道府县打卡。",
        "summary_travel_few": "前往设置地点寻找吧。",
    },
    "zh-TW": {
        "title_suffix": " 寶可夢人孔蓋 | 日本寶可夢人孔蓋地圖",
        "desc_template": "在地圖上查找日本各地繪有{name}的寶可夢人孔蓋（Pokéfuta）。從旅遊目的地或所在位置尋找附近的寶可夢人孔蓋。",
        "og_title_suffix": " 寶可夢人孔蓋",
        "generation": "第{gen}世代",
        "unknown_location": "位置不明",
        "pref_section_heading": "{pref}的{name}寶可夢人孔蓋",
        "pref_map_link": "在地圖上查看{pref} →",
        "related_heading": "相關寶可夢",
        "count_text": "全國共有 <strong>{count}</strong> 個{name}寶可夢人孔蓋。",
        "cta": "在地圖上查找全國寶可夢人孔蓋 →",
        "breadcrumb_aria": "麵包屑導覽",
        "breadcrumb_home": "全國地圖",
        "breadcrumb_pokemon": "寶可夢列表",
        "footer": "日本寶可夢人孔蓋全國地圖",
        "summary_0pref": "目前已確認{count}個{name}寶可夢人孔蓋。",
        "summary_1pref": "{name}寶可夢人孔蓋共{count}個，設置於{pref}。",
        "summary_few_pref": "{name}寶可夢人孔蓋遍布{prefs}等{n}個都道府縣，合計{count}個。",
        "summary_many_pref": "{name}寶可夢人孔蓋遍布全國{n}個都道府縣，共{count}個。包括{top_prefs}等地。",
        "summary_travel_many": "推薦前往多個都道府縣打卡。",
        "summary_travel_few": "前往設置地點尋找吧。",
    },
    "ko": {
        "title_suffix": " 포케후타 | 일본 포켓몬 맨홀 지도",
        "desc_template": "일본 전국에 설치된 {name} 포케후타（포켓몬 맨홀）를 지도에서 찾아보세요. 여행지나 현재 위치에서 가까운 포케후타를 발견하세요.",
        "og_title_suffix": " 포케후타",
        "generation": "{gen}세대",
        "unknown_location": "위치 불명",
        "pref_section_heading": "{pref}의 {name} 포케후타",
        "pref_map_link": "{pref} 지도로 보기 →",
        "related_heading": "관련 포켓몬",
        "count_text": "전국에 <strong>{count}</strong>개의 {name} 포케후타가 있습니다.",
        "cta": "지도에서 전국의 포케후타 찾기 →",
        "breadcrumb_aria": "이동 경로",
        "breadcrumb_home": "전국 지도",
        "breadcrumb_pokemon": "포켓몬 목록",
        "footer": "일본 포켓몬 맨홀 전국 지도",
        "summary_0pref": "현재 {name} 포케후타가 {count}개 확인되었습니다.",
        "summary_1pref": "{name} 포케후타가 {pref}에 {count}개 설치되어 있습니다.",
        "summary_few_pref": "{name} 포케후타는 {prefs} 등 {n}개 현에 합계 {count}개 설치되어 있습니다.",
        "summary_many_pref": "{name} 포케후타는 전국 {n}개 현에 {count}개 설치되어 있습니다. {top_prefs} 등 각지에서 만날 수 있습니다.",
        "summary_travel_many": "여러 현을 여행하며 방문해 보세요.",
        "summary_travel_few": "설치 지역을 방문해 찾아보세요.",
    },
}


def load_prefectures(path: Path) -> dict[str, dict[str, str]]:
    """Load prefecture name translations from prefectures.json."""
    if not path.exists():
        logger.warning(f"Prefectures file not found: {path}")
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def _get_display_name(pokemon: dict, lang_config: dict) -> str:
    """Return the localized display name for a Pokémon, including form prefix."""
    names = pokemon.get("names", {})
    form = pokemon.get("form") or ""
    name_key = lang_config["name_key"]
    form_prefixes = lang_config.get("form_prefixes", {})
    prefix = form_prefixes.get(form, "")
    name = names.get(name_key) or names.get("ja", "")
    return prefix + name


def generate_ai_summary(
    name: str,
    manholes: list[dict],
    strings: dict,
    translate_pref: Callable[[str], str],
    pref_joiner: str = "・",
) -> str:
    """Return a natural-language summary describing where this Pokemon appears."""
    count = len(manholes)
    prefs_ja = sorted({m.get("prefecture") for m in manholes if m.get("prefecture")})
    prefs = [translate_pref(p) for p in prefs_ja]
    n = len(prefs)

    if n == 0:
        dist = strings["summary_0pref"].format(count=count, name=name)
    elif n == 1:
        dist = strings["summary_1pref"].format(count=count, name=name, pref=prefs[0])
    elif n <= 3:
        dist = strings["summary_few_pref"].format(
            n=n, count=count, name=name, prefs=pref_joiner.join(prefs)
        )
    else:
        dist = strings["summary_many_pref"].format(
            n=n, count=count, name=name,
            top_prefs=pref_joiner.join(prefs[:2])
        )

    travel = strings["summary_travel_many"] if n >= 3 else strings["summary_travel_few"]
    return dist + travel


def _normalize_katakana(text: str) -> str:
    """Convert hiragana to katakana for loose matching."""
    return "".join(
        chr(ord(c) + 0x60) if "ぁ" <= c <= "ゖ" else c
        for c in text
    )


def load_pokemon_metadata(path: Path) -> dict[str, dict]:
    """Load Pokemon metadata; index by Japanese name (including regional forms)."""
    if not path.exists():
        logger.warning(f"Pokemon metadata not found: {path}")
        return {}

    data = json.loads(path.read_text(encoding="utf-8"))
    metadata: dict[str, dict] = {}

    for pokemon in data:
        if not isinstance(pokemon, dict):
            continue
        names = pokemon.get("names", {})
        ja_name = names.get("ja", "")
        form = pokemon.get("form") or ""
        if not ja_name:
            continue

        # Direct name: prefer base form (form == None) over regional variants.
        # Alolan/Galarian/Hisuian entries share the same names.ja as the base
        # Pokemon, so we must not let them overwrite the base slug.
        if ja_name not in metadata or not form:
            metadata[ja_name] = pokemon

        # Regional prefix variants: metadata stores "ロコン" for alolan vulpix,
        # but pokefuta data uses "アローラロコン"
        prefix = _FORM_PREFIX.get(form, "")
        if prefix:
            combined = prefix + ja_name
            if combined not in metadata:
                metadata[combined] = pokemon

    # Normalize katakana: handle ゴンべ (hiragana べ) → ゴンベ mismatch
    for key in list(metadata.keys()):
        normalized = _normalize_katakana(key)
        if normalized != key and normalized not in metadata:
            metadata[normalized] = metadata[key]

    logger.info(f"Loaded {len(metadata)} Pokemon name variants from metadata")
    return metadata


# Slugs whose regional-form match must be exact to avoid cross-form contamination.
# e.g. a manhole with only "アローラロコン" must not appear on /pokemon/vulpix/.
FORM_EXACT_MATCH: dict[str, str] = {
    "vulpix":          "ロコン",
    "vulpix-alola":    "アローラロコン",
    "ninetales":       "キュウコン",
    "ninetales-alola": "アローラキュウコン",
}


def pokemon_matches_manhole(slug: str, ja_name: str, manhole_pokemons: list[str]) -> bool:
    exact_name = FORM_EXACT_MATCH.get(slug)
    if exact_name:
        return exact_name in manhole_pokemons
    return ja_name in manhole_pokemons


def filter_pokemons(pokemons: list) -> list[str]:
    """Remove prefecture site link entries from the pokemons field."""
    if not isinstance(pokemons, list):
        return []
    return [
        p for p in pokemons
        if isinstance(p, str) and p.strip() and "ローカルActs" not in p
    ]


def read_manholes(path: Path) -> list[dict]:
    """Read active manhole records from NDJSON."""
    if not path.exists():
        logger.warning(f"Manhole data not found: {path}")
        return []
    records = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            r = json.loads(line)
        except json.JSONDecodeError:
            continue
        if r.get("status") == "active":
            records.append(r)
    return records


def build_pokemon_index(
    manholes: list[dict],
    metadata: dict[str, dict],
) -> dict[str, tuple[dict, list[dict]]]:
    """Return {slug: (pokemon_meta, [manhole, ...])} for Pokemon with >=1 pokefuta."""
    index: dict[str, tuple[dict, list[dict]]] = {}
    slug_to_meta: dict[str, dict] = {}
    ja_to_slug: dict[str, str] = {}
    seen: dict[str, set[str]] = defaultdict(set)  # slug → set of manhole IDs already added

    for ja_name, meta in metadata.items():
        slug = meta.get("slug", "")
        if slug:
            ja_to_slug[ja_name] = slug
            slug_to_meta[slug] = meta

    for manhole in manholes:
        manhole_pokemons = filter_pokemons(manhole.get("pokemons", []))
        mid = str(manhole.get("id", "")).strip()
        for ja_name in manhole_pokemons:
            # Try direct match, then katakana-normalized match
            slug = ja_to_slug.get(ja_name) or ja_to_slug.get(
                _normalize_katakana(ja_name)
            )
            if not slug:
                continue
            if not pokemon_matches_manhole(slug, ja_name, manhole_pokemons):
                continue
            if mid in seen[slug]:
                continue
            seen[slug].add(mid)
            meta = slug_to_meta[slug]
            if slug not in index:
                index[slug] = (meta, [])
            index[slug][1].append(manhole)

    return index


# Explicit override for evolution families where family_id alone doesn't capture
# cross-form relationships (e.g. Vulpix ↔ Alolan Vulpix have different family_ids).
RELATED_POKEMON_OVERRIDES: dict[str, list[str]] = {
    "vulpix":          ["vulpix-alola", "ninetales", "ninetales-alola"],
    "vulpix-alola":    ["vulpix", "ninetales", "ninetales-alola"],
    "ninetales":       ["vulpix", "vulpix-alola", "ninetales-alola"],
    "ninetales-alola": ["vulpix", "vulpix-alola", "ninetales"],
}


def build_related_map(
    index: dict[str, tuple[dict, list[dict]]],
    metadata: dict[str, dict],
) -> dict[str, list[tuple[str, dict]]]:
    """Return {slug: [(related_slug, pokemon_meta), ...]} sharing a base evolution family."""
    slug_to_family: dict[str, str] = {}
    slug_to_poke_meta: dict[str, dict] = {}

    for _ja_name, meta in metadata.items():
        slug = meta.get("slug", "")
        fam = (meta.get("evolution") or {}).get("family_id", "")
        if slug:
            slug_to_poke_meta[slug] = meta
            if fam:
                slug_to_family[slug] = fam

    base_to_slugs: dict[str, list[str]] = defaultdict(list)
    for slug in index:
        fam = slug_to_family.get(slug, "")
        base = fam.split("-")[0] if fam else ""
        if base:
            base_to_slugs[base].append(slug)

    result: dict[str, list[tuple[str, dict]]] = {}
    for slug in index:
        fam = slug_to_family.get(slug, "")
        base = fam.split("-")[0] if fam else ""
        related = [
            (s, slug_to_poke_meta[s])
            for s in sorted(base_to_slugs.get(base, []))
            if s != slug and s in slug_to_poke_meta
        ]
        result[slug] = related

    for slug, override_slugs in RELATED_POKEMON_OVERRIDES.items():
        if slug not in index:
            continue
        existing = {s for s, _ in result.get(slug, [])}
        merged = list(result.get(slug, []))
        for related_slug in override_slugs:
            if related_slug not in index or related_slug in existing:
                continue
            if related_slug not in slug_to_poke_meta:
                continue
            merged.append((related_slug, slug_to_poke_meta[related_slug]))
            existing.add(related_slug)
        result[slug] = merged

    return result


def _hreflang_links(slug: str) -> str:
    """Generate hreflang <link> tags for all language variants of a Pokemon page."""
    lines = []
    for lang, lc in LANG_CONFIGS.items():
        url = f"{BASE_URL}{lc['url_prefix']}pokemon/{quote(slug)}/"
        lines.append(f'  <link rel="alternate" hreflang="{lc["hreflang"]}" href="{escape(url)}">')
    # x-default points to Japanese (root)
    default_url = f"{BASE_URL}pokemon/{quote(slug)}/"
    lines.append(f'  <link rel="alternate" hreflang="x-default" href="{escape(default_url)}">')
    return "\n".join(lines)


def generate_html(
    slug: str,
    pokemon: dict,
    manholes: list[dict],
    related: list[tuple[str, dict]],
    image_dir: Path,
    lang: str,
    lang_config: dict,
    strings: dict,
    translate_pref: Callable[[str], str],
    seo_desc: str = "",
) -> str:
    """Return complete HTML for a Pokemon LP page."""
    display_name = _get_display_name(pokemon, lang_config)
    names = pokemon.get("names", {})
    types_data = pokemon.get("types", [])
    generation = pokemon.get("generation")

    # Show type badges in the page language where available; fall back to Japanese.
    lang_type_key = lang_config["name_key"] if lang_config["name_key"] != "ja" else None
    types_display = []
    for t in types_data:
        if not isinstance(t, dict):
            continue
        label = (lang_type_key and t.get(lang_type_key)) or t.get("en") or t.get("ja", "")
        if label:
            types_display.append(label)

    url_prefix = lang_config["url_prefix"]
    canonical_url = f"{BASE_URL}{url_prefix}pokemon/{quote(slug)}/"
    map_url = f"{BASE_URL}{url_prefix}"
    pokemon_list_url = f"/{url_prefix}pokemon/" if url_prefix else "/pokemon/"
    map_href = f"/{url_prefix}" if url_prefix else "/"

    count = len(manholes)

    title = display_name + strings["title_suffix"]
    description = strings["desc_template"].format(name=display_name)
    og_title = display_name + strings["og_title_suffix"]

    # Multilingual names line (other languages than the current one)
    other_lang_keys = ["en", "ja", "ko", "zh-Hans", "zh-Hant"]
    current_key = lang_config["name_key"]
    multilang_parts = [
        names[k] for k in other_lang_keys
        if k != current_key and names.get(k)
    ]
    # For non-ja pages, show Japanese name prominently
    if lang != "ja" and names.get("ja"):
        ja_display = _get_display_name(pokemon, LANG_CONFIGS["ja"])
        if ja_display not in multilang_parts:
            multilang_parts.insert(0, ja_display)
    multilang_html = ""
    if multilang_parts:
        multilang_html = (
            f"<p class='poke-multilang'>{escape(' / '.join(multilang_parts[:3]))}</p>"
        )

    # Type badges
    type_badges = "".join(
        f"<span class='type-badge'>{escape(t)}</span>" for t in types_display
    )
    type_html = (
        f"<div class='type-badges'>{type_badges}</div>" if type_badges else ""
    )

    gen_html = ""
    if generation:
        gen_html = f"<p class='poke-gen'>{escape(strings['generation'].format(gen=generation))}</p>"

    seo_desc_html = f"<p class='poke-seo-desc'>{escape(seo_desc)}</p>" if seo_desc else ""

    pref_joiner = lang_config.get("pref_joiner", "・")
    ai_summary_text = generate_ai_summary(
        display_name, manholes, strings, translate_pref, pref_joiner
    )
    ai_summary_html = f"<div class='ai-summary-box'><p>{escape(ai_summary_text)}</p></div>"

    # JSON-LD
    jsonld = {
        "@context": "https://schema.org",
        "@type": "CollectionPage",
        "name": og_title,
        "description": description,
        "url": canonical_url,
        "inLanguage": lang_config["html_lang"],
    }
    jsonld_str = json.dumps(jsonld, ensure_ascii=False, indent=2)

    breadcrumb_home = strings["breadcrumb_home"]
    breadcrumb_pokemon = strings["breadcrumb_pokemon"]
    jsonld_breadcrumb_str = json.dumps({
        "@context": "https://schema.org",
        "@type": "BreadcrumbList",
        "itemListElement": [
            {"@type": "ListItem", "position": 1, "name": breadcrumb_home, "item": map_url},
            {"@type": "ListItem", "position": 2, "name": breadcrumb_pokemon, "item": f"{BASE_URL}{url_prefix}pokemon/"},
            {"@type": "ListItem", "position": 3, "name": display_name, "item": canonical_url},
        ],
    }, ensure_ascii=False, indent=2)

    hreflang_html = _hreflang_links(slug)

    # Manhole sections grouped by prefecture
    unknown_location = strings["unknown_location"]
    sorted_manholes = sorted(
        manholes,
        key=lambda m: (0 if m.get("prefecture") else 1, m.get("prefecture", ""), m.get("city", "")),
    )
    sections_html = ""
    for prefecture_ja, group in groupby(sorted_manholes, key=lambda m: m.get("prefecture", "")):
        prefecture_display = translate_pref(prefecture_ja) if prefecture_ja else unknown_location
        pref_h2 = strings["pref_section_heading"].format(pref=prefecture_display, name=display_name)
        cards_html = ""
        for m in group:
            mid = str(m.get("id", "")).strip()
            pref_ja = m.get("prefecture", "")
            city = m.get("city", "")
            pref_display = translate_pref(pref_ja) if pref_ja else ""
            if pref_display and city:
                location = pref_display + city if lang == "ja" else f"{pref_display} {city}"
            else:
                location = pref_display or city or m.get("title", unknown_location)
            pokes = filter_pokemons(m.get("pokemons", []))
            sub = "・".join(pokes) if pokes else ""

            img_html = ""
            img_path = image_dir / f"{mid}_latest.jpeg"
            if img_path.exists():
                img_url = escape(f"https://data.pokefuta.com/manhole/image/{mid}_latest.jpeg")
                img_html = (
                    f"<img src='{img_url}' alt='{escape(display_name)}'"
                    f" loading='lazy' decoding='async' width='320' height='180'>"
                )

            cards_html += (
                f"<li class='manhole-item'>"
                f"<a href='/manholes/{quote(mid)}/'>"
                + img_html
                + f"<span class='manhole-location'>{escape(location)}</span>"
                + (f"<span class='manhole-poke'>{escape(sub)}</span>" if sub else "")
                + f"</a></li>"
            )

        pref_map_link = ""
        if prefecture_ja:
            pref_encoded = quote(prefecture_ja)
            link_text = strings["pref_map_link"].format(pref=prefecture_display)
            pref_map_link = (
                f"<a class='pref-map-link' href='{escape(map_href)}?pref={pref_encoded}'>"
                f"{escape(link_text)}</a>"
            )
        sections_html += (
            f"<section class='pref-section'>"
            f"<h2>{escape(pref_h2)}</h2>"
            f"{pref_map_link}"
            f"<ul class='manhole-list'>{cards_html}</ul>"
            f"</section>"
        )

    # Related Pokemon section
    related_html = ""
    if related:
        links = "".join(
            f"<li><a href='/{url_prefix}pokemon/{quote(s)}/'>"
            f"{escape(_get_display_name(meta, lang_config))}</a></li>"
            for s, meta in related
        )
        related_html = (
            f"<div class='section-card related-section'>"
            f"<h2>{escape(strings['related_heading'])}</h2>"
            f"<ul class='related-list'>{links}</ul>"
            f"</div>"
        )

    count_text_html = strings["count_text"].format(count=count, name=escape(display_name))
    cta_text = strings["cta"]
    footer_text = strings["footer"]
    breadcrumb_aria = strings["breadcrumb_aria"]

    slug_js = json.dumps(slug)

    return f"""<!doctype html>
<html lang="{lang_config['html_lang']}">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{escape(title)}</title>
  <meta name="description" content="{escape(description)}">
  <meta name="robots" content="index,follow">
  <link rel="canonical" href="{escape(canonical_url)}">
{hreflang_html}

  <meta property="og:type" content="website">
  <meta property="og:locale" content="{lang_config['og_locale']}">
  <meta property="og:title" content="{escape(og_title)}">
  <meta property="og:description" content="{escape(description)}">
  <meta property="og:url" content="{escape(canonical_url)}">
  <meta property="og:image" content="{escape(DEFAULT_OGP_IMAGE)}">

  <meta name="twitter:card" content="summary_large_image">
  <meta name="twitter:title" content="{escape(og_title)}">
  <meta name="twitter:description" content="{escape(description)}">
  <meta name="twitter:image" content="{escape(DEFAULT_OGP_IMAGE)}">

  <script type="application/ld+json">
{jsonld_str}
  </script>
  <script type="application/ld+json">
{jsonld_breadcrumb_str}
  </script>

  <!-- Google Analytics -->
  <script async src="https://www.googletagmanager.com/gtag/js?id={GA_MEASUREMENT_ID}"></script>
  <script>
    window.dataLayer = window.dataLayer || [];
    function gtag(){{dataLayer.push(arguments);}}
    gtag('js', new Date());
    gtag('config', '{GA_MEASUREMENT_ID}', {{
      'page_path': '/{url_prefix}pokemon/' + {slug_js} + '/'
    }});
    gtag('event', 'view_pokemon_lp', {{
      pokemon_slug: {slug_js},
      manhole_count: {count},
      lang: '{lang}'
    }});
    function trackEvent(action, params) {{
      gtag('event', action, params);
    }}
  </script>

  <style>
    * {{ box-sizing: border-box; margin: 0; padding: 0; }}
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
    .poke-hero {{
      margin-bottom: 24px;
    }}
    .poke-seo-desc {{
      font-size: 14px;
      color: #555;
      line-height: 1.7;
      margin-top: 12px;
      padding: 12px 14px;
      background: #f5f0ff;
      border-left: 3px solid #6F55A3;
      border-radius: 0 6px 6px 0;
    }}
    .ai-summary-box {{
      margin-top: 12px;
      padding: 12px 14px;
      background: #f0faf9;
      border-left: 3px solid #176f68;
      border-radius: 0 6px 6px 0;
      font-size: 14px;
      color: #2d5c58;
      line-height: 1.75;
    }}
    .pref-map-link {{
      display: inline-block;
      font-size: 12px;
      color: #6F55A3;
      text-decoration: none;
      margin-bottom: 8px;
      font-weight: bold;
    }}
    .pref-map-link:hover {{ text-decoration: underline; }}
    h1 {{
      font-size: 26px;
      font-weight: bold;
      color: #1a1a1a;
      margin-bottom: 8px;
    }}
    .poke-multilang {{
      color: #666;
      font-size: 14px;
      margin-bottom: 8px;
    }}
    .type-badges {{
      display: flex;
      flex-wrap: wrap;
      gap: 6px;
      margin-bottom: 6px;
    }}
    .type-badge {{
      background: #6F55A3;
      color: white;
      font-size: 12px;
      padding: 2px 10px;
      border-radius: 12px;
      font-weight: bold;
    }}
    .poke-gen {{
      font-size: 13px;
      color: #888;
    }}
    .section-card {{
      margin-top: 24px;
      padding: 16px;
      background: #fafafa;
      border-radius: 8px;
      border: 1px solid #e8e8e8;
    }}
    .count-text {{
      font-size: 15px;
      color: #555;
      margin-bottom: 16px;
    }}
    .pref-section {{
      margin-bottom: 20px;
    }}
    .pref-section h2 {{
      font-size: 16px;
      font-weight: bold;
      color: #1a1a1a;
      margin-bottom: 10px;
      padding-bottom: 6px;
      border-bottom: 2px solid #e0e0e0;
    }}
    .manhole-list {{
      list-style: none;
      display: grid;
      grid-template-columns: repeat(auto-fill, minmax(220px, 1fr));
      gap: 8px;
    }}
    .manhole-item a {{
      display: block;
      background: white;
      border: 1px solid #ddd;
      border-radius: 8px;
      padding: 10px 14px;
      text-decoration: none;
      color: #333;
      transition: border-color 0.15s, box-shadow 0.15s;
      overflow: hidden;
    }}
    .manhole-item a:hover {{
      border-color: #6F55A3;
      box-shadow: 0 2px 8px rgba(111,85,163,0.15);
    }}
    .manhole-item a img {{
      display: block;
      width: calc(100% + 28px);
      margin: -10px -14px 8px;
      height: 160px;
      object-fit: cover;
    }}
    .manhole-location {{
      display: block;
      font-size: 14px;
      font-weight: bold;
      color: #1a1a1a;
    }}
    .manhole-poke {{
      display: block;
      font-size: 12px;
      color: #888;
      margin-top: 2px;
    }}
    .related-section h2 {{
      font-size: 16px;
      font-weight: bold;
      color: #1a1a1a;
      margin-bottom: 10px;
      padding-bottom: 6px;
      border-bottom: 2px solid #e0e0e0;
    }}
    .related-list {{
      list-style: none;
      display: flex;
      flex-wrap: wrap;
      gap: 8px;
    }}
    .related-list a {{
      display: inline-block;
      padding: 4px 14px;
      background: #f0ebfa;
      color: #6F55A3;
      border-radius: 16px;
      text-decoration: none;
      font-size: 14px;
      font-weight: bold;
    }}
    .related-list a:hover {{ background: #e0d8f5; }}
    .cta-map {{
      display: block;
      background: #6F55A3;
      color: white;
      text-align: center;
      padding: 16px 24px;
      border-radius: 8px;
      text-decoration: none;
      font-size: 17px;
      font-weight: bold;
      margin-top: 24px;
      transition: background 0.2s;
    }}
    .cta-map:hover {{ background: #5a4480; }}
    footer {{
      margin-top: 32px;
      text-align: center;
      font-size: 13px;
      color: #aaa;
    }}
    footer a {{ color: #6F55A3; text-decoration: none; }}
    .breadcrumb {{ font-size: 13px; color: #888; margin-bottom: 14px; }}
    .breadcrumb ol {{ list-style: none; display: flex; flex-wrap: wrap; gap: 4px; align-items: center; }}
    .breadcrumb li + li::before {{ content: "›"; margin-right: 4px; color: #ccc; }}
    .breadcrumb a {{ color: #6F55A3; text-decoration: none; }}
    .breadcrumb a:hover {{ text-decoration: underline; }}
  </style>
</head>
<body>
<div class="container">
  <nav aria-label="{escape(breadcrumb_aria)}" class="breadcrumb">
    <ol>
      <li><a href="{escape(map_href)}">{escape(breadcrumb_home)}</a></li>
      <li><a href="{escape(pokemon_list_url)}">{escape(breadcrumb_pokemon)}</a></li>
      <li aria-current="page">{escape(display_name)}</li>
    </ol>
  </nav>

  <div class="poke-hero">
    <h1>{escape(display_name)}{escape(strings['og_title_suffix'])}</h1>
    {multilang_html}
    {type_html}
    {gen_html}
    {seo_desc_html}
    {ai_summary_html}
  </div>

  <div class="section-card">
    <p class="count-text">{count_text_html}</p>
    {sections_html}
  </div>

  {related_html}

  <a href="{escape(map_url)}" class="cta-map"
     onclick="trackEvent('click_map_cta', {{pokemon_slug: {slug_js}}})">
    {escape(cta_text)}
  </a>

  <footer>
    <p><a href="{escape(BASE_URL)}">data.pokefuta.com</a> &mdash; {escape(footer_text)}</p>
  </footer>
</div>
</body>
</html>"""


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--manholes", default="docs/pokefuta.ndjson",
        help="Path to pokefuta NDJSON",
    )
    parser.add_argument(
        "--pokemon", default="docs/pokemon_metadata.json",
        help="Path to pokemon_metadata.json",
    )
    parser.add_argument(
        "--images", default="dataset/manhole/image",
        help="Directory containing {id}_latest.jpeg files",
    )
    parser.add_argument(
        "--output-root", default="dist",
        help="Root output directory (default: dist). Pokemon pages go to {output-root}/pokemon/ for ja and {output-root}/{lang}/pokemon/ for other languages.",
    )
    parser.add_argument(
        "--langs", nargs="*", default=list(LANG_CONFIGS.keys()),
        help="Languages to generate (default: all). Example: --langs ja en ko",
    )
    parser.add_argument(
        "--prefectures", default="apps/web/i18n/prefectures.json",
        help="Path to prefectures.json for prefecture name translations",
    )
    args = parser.parse_args()

    metadata = load_pokemon_metadata(Path(args.pokemon))
    if not metadata:
        logger.error("No Pokemon metadata loaded — aborting")
        return 1

    manholes = read_manholes(Path(args.manholes))
    if not manholes:
        logger.error("No manhole records loaded — aborting")
        return 1

    pref_data = load_prefectures(Path(args.prefectures))

    index = build_pokemon_index(manholes, metadata)
    logger.info(f"Pokemon with pokefuta: {len(index)}")

    related_map = build_related_map(index, metadata)
    image_dir = Path(args.images)
    output_root = Path(args.output_root)

    langs_to_build = [la for la in args.langs if la in LANG_CONFIGS]
    if not langs_to_build:
        logger.error(f"No valid languages specified. Choose from: {list(LANG_CONFIGS.keys())}")
        return 1

    for lang in langs_to_build:
        lc = LANG_CONFIGS[lang]
        strings = LP_STRINGS[lang]
        pref_key = lc["pref_key"]

        if pref_key is None:
            def translate_pref(ja: str, _key: str = "") -> str:
                return ja
        else:
            def translate_pref(ja: str, _key: str = pref_key) -> str:
                return pref_data.get(ja, {}).get(_key, ja)

        url_prefix = lc["url_prefix"]
        if url_prefix:
            pokemon_dir = output_root / url_prefix.rstrip("/") / "pokemon"
        else:
            pokemon_dir = output_root / "pokemon"

        generated = 0
        for slug, (pokemon, poke_manholes) in sorted(index.items()):
            out_dir = pokemon_dir / slug
            out_dir.mkdir(parents=True, exist_ok=True)
            html = generate_html(
                slug=slug,
                pokemon=pokemon,
                manholes=poke_manholes,
                related=related_map.get(slug, []),
                image_dir=image_dir,
                lang=lang,
                lang_config=lc,
                strings=strings,
                translate_pref=translate_pref,
                seo_desc=POKEMON_SEO_DESCRIPTIONS.get(slug, "") if lang == "ja" else "",
            )
            (out_dir / "index.html").write_text(html, encoding="utf-8")
            generated += 1

        logger.info(f"[{lang}] wrote {generated} pages to {pokemon_dir}/")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
