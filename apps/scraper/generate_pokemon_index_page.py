#!/usr/bin/env python3
"""Generate /pokemon/index.html — SEO hub listing all Pokemon with pokefuta.

Generates language-specific versions under dist/{lang}/pokemon/index.html
(Japanese goes to dist/pokemon/index.html).
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from collections import defaultdict
from collections.abc import Callable
from pathlib import Path
from urllib.parse import quote
from xml.sax.saxutils import escape

sys.path.insert(0, str(Path(__file__).parent))
from generate_pokemon_pages import (
    BASE_URL,
    DEFAULT_OGP_IMAGE,
    GA_MEASUREMENT_ID,
    LANG_CONFIGS,
    _get_display_name,
    build_pokemon_index,
    load_pokemon_metadata,
    load_prefectures,
    read_manholes,
)

logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger(__name__)

# UI strings per language for the Pokemon index page.
LP_INDEX_STRINGS: dict[str, dict] = {
    "ja": {
        "title": "ポケモン別ポケふた一覧｜登場ポケモンから探すポケモンマンホール",
        "description": (
            "全国のポケモンマンホール「ポケふた」を登場ポケモン別に探せる一覧ページです。"
            "ピカチュウ、イーブイ、カビゴンなど、ポケふたに登場するポケモンから設置場所を探せます。"
        ),
        "og_title": "ポケモン別ポケふた一覧",
        "h1": "ポケモン別ポケふた一覧",
        "lead": (
            "全国に広がるポケモンマンホール「ポケふた」を、登場ポケモン別に探せます。"
            "好きなポケモンがどの地域のポケふたに登場しているかを見たり、"
            "旅先で出会えるポケふたを探したりできます。"
        ),
        "hub_heading": "ポケふたをポケモン別に探す",
        "hub_name": "ポケモン名で探す",
        "hub_ranking": "登場数ランキングを見る",
        "hub_taxonomy": "タイプ・世代から探す",
        "hub_map": "地図で設置場所を見る",
        "summary_link": "ポケふた統計・一覧ハブへ戻る",
        "ranking_heading": "登場数ランキング",
        "featured_heading": "人気・代表ポケモン",
        "type_heading": "タイプ別に探す",
        "generation_heading": "世代別に探す",
        "regional_heading": "地域を応援するポケモン",
        "all_heading": "全ポケモン一覧（{total}体）",
        "map_nav_hint": "都道府県ごとのポケふたは<a href='{map_href}'>全国マップ</a>から地域を選んで確認できます。",
        "cta": "地図で全国のポケふたを探す →",
        "breadcrumb_aria": "パンくずリスト",
        "breadcrumb_home": "全国マップ",
        "footer": "ポケモンマンホール全国マップ",
        "region_summary_unknown": "所在地不明",
        "region_summary_fmt": "{count}枚 / {region}",
        "region_summary_pref_count": "{n}都道府県",
        "count_label": "{count}枚",
        "pref_count_label": "{count}都道府県",
        "pokemon_count_label": "{count}体",
        "rank_label": "{rank}位",
        "type_label": "タイプ",
        "generation_label": "第{gen}世代",
        "generation_later_label": "第5世代以降",
        "unknown_generation": "世代不明",
        "latest_image_alt": "{name}のポケふた（{location}）",
        "popular_intro": (
            "登場回数が多いポケモンほど、全国各地で出会いやすいポケモンです。"
            "{top3}などは{min_count}枚以上のポケふたに登場しており、"
            "初めてポケふた巡りをする方にも見つけやすいポケモンです。"
            "気になるポケモンをタップして、設置場所や旅のルートを確認しましょう。"
        ),
        "jsonld_name": "ポケふたに登場するポケモン一覧",
    },
    "en": {
        "title": "Pokefuta by Pokémon | Find Pokémon Manhole Covers by Featured Pokémon",
        "description": (
            "Browse Japan's Pokefuta Pokémon manhole covers by featured Pokémon. "
            "Find locations for Pikachu, Eevee, Snorlax, and other Pokémon appearing on Pokefuta."
        ),
        "og_title": "Pokefuta by Pokémon",
        "h1": "Pokefuta by Pokémon",
        "lead": (
            "Explore Japan's Pokefuta Pokémon manhole covers by the Pokémon featured on them. "
            "See where your favorite Pokémon appear and find Pokefuta to visit on your trip."
        ),
        "hub_heading": "Find Pokefuta by Pokémon",
        "hub_name": "Search by Pokémon",
        "hub_ranking": "View appearance rankings",
        "hub_taxonomy": "Browse by type and generation",
        "hub_map": "View locations on the map",
        "summary_link": "Back to the Pokefuta summary hub",
        "ranking_heading": "Appearance Ranking",
        "featured_heading": "Popular Pokémon",
        "type_heading": "Browse by Type",
        "generation_heading": "Browse by Generation",
        "regional_heading": "Regional Pokémon",
        "all_heading": "All Pokémon ({total})",
        "map_nav_hint": "Browse Pokéfuta by prefecture on the <a href='{map_href}'>Japan Map</a>.",
        "cta": "Explore all Pokéfuta on the map →",
        "breadcrumb_aria": "Breadcrumb",
        "breadcrumb_home": "Japan Map",
        "footer": "Pokémon Manhole Map of Japan",
        "region_summary_unknown": "Location unknown",
        "region_summary_fmt": "{count} / {region}",
        "region_summary_pref_count": "{n} prefectures",
        "count_label": "{count} Pokefuta",
        "pref_count_label": "{count} prefectures",
        "pokemon_count_label": "{count} Pokémon",
        "rank_label": "#{rank}",
        "type_label": "Type",
        "generation_label": "Gen {gen}",
        "generation_later_label": "Gen 5+",
        "unknown_generation": "Generation unknown",
        "latest_image_alt": "{name} Pokefuta in {location}",
        "popular_intro": (
            "Pokémon that appear on more Pokéfuta are easier to find across Japan. "
            "{top3} and others appear on {min_count}+ Pokéfuta, "
            "making them great starting points for first-time Pokéfuta hunters. "
            "Tap any Pokémon to check locations and plan your route."
        ),
        "jsonld_name": "Pokémon on Pokéfuta — Full List",
    },
    "zh-CN": {
        "title": "按宝可梦查找宝可梦井盖一览 | 日本宝可梦井盖地图",
        "description": (
            "按登场宝可梦查找日本全国的宝可梦井盖（Pokéfuta）。"
            "可从皮卡丘、伊布、卡比兽等宝可梦查看设置地点。"
        ),
        "og_title": "按宝可梦查找宝可梦井盖",
        "h1": "按宝可梦查找宝可梦井盖",
        "lead": (
            "日本全国的宝可梦井盖（Pokéfuta）可按登场宝可梦查找。"
            "看看喜欢的宝可梦出现在哪些地区，也可以为旅行寻找想去看的井盖。"
        ),
        "hub_heading": "按宝可梦查找井盖",
        "hub_name": "按宝可梦名称查找",
        "hub_ranking": "查看登场数排行",
        "hub_taxonomy": "按属性・世代查找",
        "hub_map": "在地图上查看地点",
        "summary_link": "返回宝可梦井盖统计中心",
        "ranking_heading": "登场数排行",
        "featured_heading": "热门・代表宝可梦",
        "type_heading": "按属性查找",
        "generation_heading": "按世代查找",
        "regional_heading": "代表各地区的宝可梦",
        "all_heading": "全部宝可梦（{total}只）",
        "map_nav_hint": "可从<a href='{map_href}'>全国地图</a>按都道府县查看宝可梦井盖分布。",
        "cta": "在地图上查找全国宝可梦井盖 →",
        "breadcrumb_aria": "面包屑导航",
        "breadcrumb_home": "全国地图",
        "footer": "日本宝可梦井盖全国地图",
        "region_summary_unknown": "位置不明",
        "region_summary_fmt": "{count}个 / {region}",
        "region_summary_pref_count": "{n}个都道府县",
        "count_label": "{count}个",
        "pref_count_label": "{count}个都道府县",
        "pokemon_count_label": "{count}只",
        "rank_label": "第{rank}名",
        "type_label": "属性",
        "generation_label": "第{gen}世代",
        "generation_later_label": "第5世代以后",
        "unknown_generation": "世代不明",
        "latest_image_alt": "{location}的{name}宝可梦井盖",
        "popular_intro": (
            "登场次数越多的宝可梦，越容易在全国各地相遇。"
            "{top3}等宝可梦登场的宝可梦井盖达{min_count}个以上，"
            "非常适合初次挑战宝可梦井盖打卡的玩家。"
            "点击感兴趣的宝可梦，确认设置地点和旅行路线。"
        ),
        "jsonld_name": "宝可梦井盖上的宝可梦一览",
    },
    "zh-TW": {
        "title": "按寶可夢查找寶可夢人孔蓋一覽 | 日本寶可夢人孔蓋地圖",
        "description": (
            "按登場寶可夢查找日本全國的寶可夢人孔蓋（Pokéfuta）。"
            "可從皮卡丘、伊布、卡比獸等寶可夢查看設置地點。"
        ),
        "og_title": "按寶可夢查找寶可夢人孔蓋",
        "h1": "按寶可夢查找寶可夢人孔蓋",
        "lead": (
            "日本全國的寶可夢人孔蓋（Pokéfuta）可按登場寶可夢查找。"
            "看看喜歡的寶可夢出現在哪些地區，也可以為旅行尋找想去看的井蓋。"
        ),
        "hub_heading": "按寶可夢查找人孔蓋",
        "hub_name": "按寶可夢名稱查找",
        "hub_ranking": "查看登場數排行",
        "hub_taxonomy": "按屬性・世代查找",
        "hub_map": "在地圖上查看地點",
        "summary_link": "返回寶可夢人孔蓋統計中心",
        "ranking_heading": "登場數排行",
        "featured_heading": "熱門・代表寶可夢",
        "type_heading": "按屬性查找",
        "generation_heading": "按世代查找",
        "regional_heading": "代表各地區的寶可夢",
        "all_heading": "全部寶可夢（{total}隻）",
        "map_nav_hint": "可從<a href='{map_href}'>全國地圖</a>按都道府縣查看寶可夢人孔蓋分布。",
        "cta": "在地圖上查找全國寶可夢人孔蓋 →",
        "breadcrumb_aria": "麵包屑導覽",
        "breadcrumb_home": "全國地圖",
        "footer": "日本寶可夢人孔蓋全國地圖",
        "region_summary_unknown": "位置不明",
        "region_summary_fmt": "{count}個 / {region}",
        "region_summary_pref_count": "{n}個都道府縣",
        "count_label": "{count}個",
        "pref_count_label": "{count}個都道府縣",
        "pokemon_count_label": "{count}隻",
        "rank_label": "第{rank}名",
        "type_label": "屬性",
        "generation_label": "第{gen}世代",
        "generation_later_label": "第5世代以後",
        "unknown_generation": "世代不明",
        "latest_image_alt": "{location}的{name}寶可夢人孔蓋",
        "popular_intro": (
            "登場次數越多的寶可夢，越容易在全國各地相遇。"
            "{top3}等寶可夢登場的寶可夢人孔蓋達{min_count}個以上，"
            "非常適合初次挑戰寶可夢人孔蓋打卡的玩家。"
            "點擊感興趣的寶可夢，確認設置地點和旅行路線。"
        ),
        "jsonld_name": "寶可夢人孔蓋上的寶可夢一覽",
    },
    "ko": {
        "title": "포켓몬별 포케후타 목록 | 등장 포켓몬으로 찾는 포켓몬 맨홀",
        "description": (
            "일본 전국의 포켓몬 맨홀 「포케후타」를 등장 포켓몬별로 찾는 목록 페이지입니다. "
            "피카츄, 이브이, 잠만보 등 포케후타에 등장하는 포켓몬으로 설치 장소를 찾을 수 있습니다."
        ),
        "og_title": "포켓몬별 포케후타 목록",
        "h1": "포켓몬별 포케후타 목록",
        "lead": (
            "일본 전국에 퍼져 있는 포켓몬 맨홀 「포케후타」를 등장 포켓몬별로 찾을 수 있습니다. "
            "좋아하는 포켓몬이 어느 지역의 포케후타에 등장하는지 보고, 여행지에서 만날 포케후타를 찾아보세요."
        ),
        "hub_heading": "포켓몬별로 포케후타 찾기",
        "hub_name": "포켓몬 이름으로 찾기",
        "hub_ranking": "등장 수 랭킹 보기",
        "hub_taxonomy": "타입・세대로 찾기",
        "hub_map": "지도에서 설치 장소 보기",
        "summary_link": "포케후타 통계 허브로 돌아가기",
        "ranking_heading": "등장 수 랭킹",
        "featured_heading": "인기・대표 포켓몬",
        "type_heading": "타입별로 찾기",
        "generation_heading": "세대별로 찾기",
        "regional_heading": "지역을 응원하는 포켓몬",
        "all_heading": "모든 포켓몬（{total}마리）",
        "map_nav_hint": "<a href='{map_href}'>전국 지도</a>에서 현별로 포케후타를 확인할 수 있습니다.",
        "cta": "지도에서 전국의 포케후타 찾기 →",
        "breadcrumb_aria": "이동 경로",
        "breadcrumb_home": "전국 지도",
        "footer": "일본 포켓몬 맨홀 전국 지도",
        "region_summary_unknown": "위치 불명",
        "region_summary_fmt": "{count}개 / {region}",
        "region_summary_pref_count": "{n}개 현",
        "count_label": "{count}개",
        "pref_count_label": "{count}개 현",
        "pokemon_count_label": "{count}마리",
        "rank_label": "{rank}위",
        "type_label": "타입",
        "generation_label": "{gen}세대",
        "generation_later_label": "5세대 이후",
        "unknown_generation": "세대 불명",
        "latest_image_alt": "{location}의 {name} 포케후타",
        "popular_intro": (
            "등장 횟수가 많은 포켓몬일수록 전국 각지에서 만나기 쉽습니다. "
            "{top3} 등은 {min_count}개 이상의 포케후타에 등장하여 "
            "처음 포케후타를 찾는 분들에게도 발견하기 쉬운 포켓몬입니다. "
            "좋아하는 포켓몬을 탭해서 설치 장소와 여행 루트를 확인해 보세요."
        ),
        "jsonld_name": "포케후타에 등장하는 포켓몬 목록",
    },
}

# Regional Pokémon taglines per language: slug → {lang: tagline}
REGIONAL_TAGLINES: dict[str, dict[str, str]] = {
    "vulpix": {
        "ja": "北海道を応援するポケモン",
        "en": "Pokémon representing Hokkaido",
        "zh-CN": "代表北海道的宝可梦",
        "zh-TW": "代表北海道的寶可夢",
        "ko": "홋카이도를 응원하는 포켓몬",
    },
    "vulpix-alola": {
        "ja": "北海道を応援するポケモン",
        "en": "Pokémon representing Hokkaido",
        "zh-CN": "代表北海道的宝可梦",
        "zh-TW": "代表北海道的寶可夢",
        "ko": "홋카이도를 응원하는 포켓몬",
    },
    "slowpoke": {
        "ja": "香川県を応援するポケモン",
        "en": "Pokémon representing Kagawa",
        "zh-CN": "代表香川县的宝可梦",
        "zh-TW": "代表香川縣的寶可夢",
        "ko": "카가와현을 응원하는 포켓몬",
    },
    "lapras": {
        "ja": "宮城県を応援するポケモン",
        "en": "Pokémon representing Miyagi",
        "zh-CN": "代表宫城县的宝可梦",
        "zh-TW": "代表宮城縣的寶可夢",
        "ko": "미야기현을 응원하는 포켓몬",
    },
    "geodude": {
        "ja": "岩手県を応援するポケモン",
        "en": "Pokémon representing Iwate",
        "zh-CN": "代表岩手县的宝可梦",
        "zh-TW": "代表岩手縣的寶可夢",
        "ko": "이와테현을 응원하는 포켓몬",
    },
    "chansey": {
        "ja": "福島県を応援するポケモン",
        "en": "Pokémon representing Fukushima",
        "zh-CN": "代表福岛县的宝可梦",
        "zh-TW": "代表福島縣的寶可夢",
        "ko": "후쿠시마현을 응원하는 포켓몬",
    },
}

REGIONAL_POKEMON_SLUGS: list[str] = [
    "vulpix", "vulpix-alola", "slowpoke", "lapras", "geodude", "chansey",
]

FEATURED_POKEMON_SLUGS: list[str] = [
    "pikachu", "eevee", "snorlax", "lapras",
    "vulpix", "magikarp", "slowpoke", "meowth",
]

TYPE_ORDER_JA: list[str] = [
    "ノーマル", "ほのお", "みず", "でんき", "くさ", "こおり",
    "かくとう", "どく", "じめん", "ひこう", "エスパー", "むし",
    "いわ", "ゴースト", "ドラゴン", "あく", "はがね", "フェアリー",
]


def _region_summary(
    manholes: list[dict],
    count: int,
    strings: dict,
    translate_pref: Callable[[str], str],
) -> str:
    prefs_ja = sorted({m.get("prefecture", "") for m in manholes if m.get("prefecture")})
    if not prefs_ja:
        region_text = strings["region_summary_unknown"]
    elif len(prefs_ja) == 1:
        region_text = translate_pref(prefs_ja[0])
    else:
        n = len(prefs_ja)
        region_text = strings["region_summary_pref_count"].format(n=n)
    return strings["region_summary_fmt"].format(count=count, region=region_text)


def load_photos(path: Path) -> dict:
    """Load latest-manhole-photos.json."""
    if not path.exists():
        logger.warning(f"Latest photos file not found: {path}")
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        logger.warning(f"Failed to read latest photos ({exc})")
        return {}
    return data if isinstance(data, dict) else {}


def _pokemon_href(url_prefix: str, slug: str) -> str:
    return f"/{url_prefix}pokemon/{quote(slug)}/"


def _map_href(url_prefix: str) -> str:
    return f"/{url_prefix}" if url_prefix else "/"


def _summary_href(url_prefix: str) -> str:
    return f"/{url_prefix}summary/" if url_prefix else "/summary/"


def _location_text(manhole: dict, translate_pref: Callable[[str], str], lang: str) -> str:
    pref = manhole.get("prefecture", "")
    city = manhole.get("city", "")
    pref_display = translate_pref(pref) if pref else ""
    if pref_display and city:
        return pref_display + city if lang == "ja" else f"{pref_display} {city}"
    return pref_display or city or manhole.get("title", "")


def _type_labels(meta: dict, lang_config: dict) -> list[str]:
    labels = []
    for type_data in meta.get("types", []):
        if not isinstance(type_data, dict):
            continue
        if lang_config["name_key"] == "ja":
            label = type_data.get("ja") or type_data.get("en", "")
        else:
            label = type_data.get("en") or type_data.get("ja", "")
        if label:
            labels.append(label)
    return labels


def _type_keys(meta: dict) -> list[str]:
    keys = []
    for type_data in meta.get("types", []):
        if isinstance(type_data, dict) and type_data.get("ja"):
            keys.append(type_data["ja"])
    return keys


def _generation_label(generation: object, strings: dict) -> str:
    if isinstance(generation, int):
        if generation >= 5:
            return strings["generation_later_label"]
        if 1 <= generation <= 4:
            return strings["generation_label"].format(gen=generation)
    return strings["unknown_generation"]


def _photo_url(mid: str, photo: dict | None, available_images: frozenset[str]) -> str:
    if mid and mid in available_images:
        return f"{BASE_URL}manhole/image/{quote(mid, safe='')}_latest.jpeg"
    if photo and isinstance(photo.get("url"), str):
        return photo["url"]
    return ""


def _select_latest_image(
    manholes: list[dict],
    photos_data: dict,
    available_images: frozenset[str],
    display_name: str,
    translate_pref: Callable[[str], str],
    lang: str,
    strings: dict,
) -> dict | None:
    ids = {str(m.get("id", "")).strip() for m in manholes if m.get("id")}
    photos = photos_data.get("photos", {}) if isinstance(photos_data, dict) else {}
    records_by_id = {str(m.get("id", "")).strip(): m for m in manholes}

    photo_candidates = [
        p for p in photos.values()
        if str(p.get("manhole_id", "")).strip() in ids
    ]
    for photo in sorted(photo_candidates, key=lambda p: p.get("created_at", ""), reverse=True):
        mid = str(photo.get("manhole_id", "")).strip()
        url = _photo_url(mid, photo, available_images)
        if not url:
            continue
        location = _location_text(records_by_id.get(mid, {}), translate_pref, lang)
        return {
            "url": url,
            "manhole_id": mid,
            "location": location,
            "alt": strings["latest_image_alt"].format(
                name=display_name, location=location or strings["region_summary_unknown"]
            ),
        }

    for manhole in sorted(manholes, key=lambda m: str(m.get("id", ""))):
        mid = str(manhole.get("id", "")).strip()
        url = _photo_url(mid, None, available_images)
        if not url:
            continue
        location = _location_text(manhole, translate_pref, lang)
        return {
            "url": url,
            "manhole_id": mid,
            "location": location,
            "alt": strings["latest_image_alt"].format(
                name=display_name, location=location or strings["region_summary_unknown"]
            ),
        }
    return None


def _build_pokemon_cards(
    pokemon_index: dict[str, tuple[dict, list[dict]]],
    lang: str,
    lang_config: dict,
    strings: dict,
    translate_pref: Callable[[str], str],
    photos_data: dict,
    image_dir: Path,
) -> list[dict]:
    url_prefix = lang_config["url_prefix"]
    available_images = frozenset(
        p.stem.removesuffix("_latest")
        for p in image_dir.glob("*_latest.jpeg")
    ) if image_dir.exists() else frozenset()
    cards = []
    for slug, (meta, manholes) in pokemon_index.items():
        display_name = _get_display_name(meta, lang_config)
        count = len(manholes)
        prefs = {m.get("prefecture") for m in manholes if m.get("prefecture")}
        generation = meta.get("generation")
        card = {
            "slug": slug,
            "href": _pokemon_href(url_prefix, slug),
            "name": display_name,
            "name_en": meta.get("names", {}).get("en", ""),
            "count": count,
            "pref_count": len(prefs),
            "types": _type_labels(meta, lang_config),
            "type_keys": _type_keys(meta),
            "generation": generation,
            "generation_label": _generation_label(generation, strings),
            "summary": _region_summary(manholes, count, strings, translate_pref),
        }
        card["latest_image"] = _select_latest_image(
            manholes, photos_data, available_images, display_name,
            translate_pref, lang, strings,
        )
        cards.append(card)
    return sorted(cards, key=lambda c: (-c["count"], c["name"]))


def _hreflang_links_index() -> str:
    """Generate hreflang <link> tags for all language variants of the Pokemon index."""
    lines = []
    for lang, lc in LANG_CONFIGS.items():
        url = f"{BASE_URL}{lc['url_prefix']}pokemon/"
        lines.append(f'  <link rel="alternate" hreflang="{lc["hreflang"]}" href="{escape(url)}">')
    lines.append(f'  <link rel="alternate" hreflang="x-default" href="{escape(BASE_URL)}pokemon/">')
    return "\n".join(lines)


def generate_html(
    pokemon_index: dict[str, tuple[dict, list[dict]]],
    lang: str,
    lang_config: dict,
    strings: dict,
    translate_pref: Callable[[str], str],
    photos_data: dict,
    image_dir: Path,
) -> str:
    total_count = len(pokemon_index)
    url_prefix = lang_config["url_prefix"]
    map_href = _map_href(url_prefix)
    summary_href = _summary_href(url_prefix)
    canonical_url = f"{BASE_URL}{url_prefix}pokemon/"
    map_url = f"{BASE_URL}{url_prefix}"

    hreflang_html = _hreflang_links_index()
    cards = _build_pokemon_cards(
        pokemon_index, lang, lang_config, strings, translate_pref,
        photos_data, image_dir,
    )
    cards_by_slug = {c["slug"]: c for c in cards}

    def image_html(card: dict, class_name: str = "card-photo") -> str:
        image = card.get("latest_image")
        if not image:
            return ""
        return (
            f'<span class="{class_name}">'
            f'<img src="{escape(image["url"])}" alt="{escape(image["alt"])}" '
            f'loading="lazy" decoding="async" width="320" height="180">'
            f"</span>"
        )

    def meta_html(card: dict) -> str:
        type_text = " / ".join(card["types"])
        parts = []
        if type_text:
            parts.append(f'{strings["type_label"]}: {type_text}')
        if card["generation_label"]:
            parts.append(card["generation_label"])
        return "".join(f'<span class="poke-chip">{escape(part)}</span>' for part in parts)

    def count_html(card: dict) -> str:
        return (
            f'<span>{escape(strings["count_label"].format(count=card["count"]))}</span>'
            f'<span>{escape(strings["pref_count_label"].format(count=card["pref_count"]))}</span>'
        )

    def card_html(card: dict, class_name: str = "poke-card") -> str:
        en_html = (
            f'<span class="poke-en">{escape(card["name_en"])}</span>'
            if card["name_en"] and lang != "en" else ""
        )
        return (
            f'<article class="{class_name}">'
            f'<a href="{escape(card["href"])}">'
            f'{image_html(card)}'
            f'<span class="poke-card-body">'
            f'<span class="poke-name">{escape(card["name"])}</span>'
            f'{en_html}'
            f'<span class="poke-counts">{count_html(card)}</span>'
            f'<span class="poke-meta">{meta_html(card)}</span>'
            f'<span class="poke-summary">{escape(card["summary"])}</span>'
            f'</span>'
            f'</a></article>'
        )

    def compact_links(section_cards: list[dict], limit: int = 8) -> str:
        links = []
        for card in section_cards[:limit]:
            links.append(
                f'<a href="{escape(card["href"])}">'
                f'{escape(card["name"])}'
                f'<span>{escape(strings["count_label"].format(count=card["count"]))}</span>'
                f'</a>'
            )
        return "".join(links)

    # Regional Pokémon section
    regional_items: list[str] = []
    for slug in REGIONAL_POKEMON_SLUGS:
        if slug not in pokemon_index:
            continue
        card = cards_by_slug.get(slug)
        if not card:
            continue
        tagline = REGIONAL_TAGLINES.get(slug, {}).get(lang, REGIONAL_TAGLINES.get(slug, {}).get("en", ""))
        en_span = (
            f"<span class='poke-en'>{escape(card['name_en'])}</span>"
            if card["name_en"] and lang != "en" else ""
        )
        regional_items.append(
            f"<li class='regional-item'>"
            f"<a href='{escape(card['href'])}'>"
            f"{image_html(card, 'regional-photo')}"
            f"<span class='poke-name'>{escape(card['name'])}</span>"
            f"{en_span}"
            f"<span class='poke-tagline'>{escape(tagline)}</span>"
            f"<span class='poke-summary'>{escape(card['summary'])}</span>"
            f"</a></li>"
        )
    regional_items_html = "\n".join(regional_items) + "\n" if regional_items else ""

    ranking_items = []
    for rank, card in enumerate(cards[:10], start=1):
        en_html = (
            f'<span class="poke-en">{escape(card["name_en"])}</span>'
            if card["name_en"] and lang != "en" else ""
        )
        ranking_image = (
            image_html(card, "ranking-photo")
            or '<span class="ranking-photo image-placeholder"></span>'
        )
        ranking_items.append(
            f'<li class="ranking-item">'
            f'<a href="{escape(card["href"])}">'
            f'<span class="ranking-rank">{escape(strings["rank_label"].format(rank=rank))}</span>'
            f'{ranking_image}'
            f'<span class="ranking-main">'
            f'<span class="poke-name">{escape(card["name"])}</span>{en_html}'
            f'<span class="poke-counts">{count_html(card)}</span>'
            f'</span>'
            f'</a></li>'
        )
    ranking_html = "\n".join(ranking_items)

    featured_cards = [cards_by_slug[slug] for slug in FEATURED_POKEMON_SLUGS if slug in cards_by_slug]
    featured_html = "".join(card_html(card, "featured-card") for card in featured_cards)

    type_groups: dict[str, list[dict]] = defaultdict(list)
    type_label_by_key: dict[str, str] = {}
    for card in cards:
        for idx, key in enumerate(card["type_keys"]):
            type_groups[key].append(card)
            if idx < len(card["types"]) and key not in type_label_by_key:
                type_label_by_key[key] = card["types"][idx]
    ordered_type_keys = [key for key in TYPE_ORDER_JA if key in type_groups]
    ordered_type_keys.extend(sorted(key for key in type_groups if key not in ordered_type_keys))
    type_sections = []
    for key in ordered_type_keys:
        group = sorted(type_groups[key], key=lambda c: (-c["count"], c["name"]))
        type_sections.append(
            f'<section class="taxonomy-card" id="type-{quote(key, safe="")}">'
            f'<h3>{escape(type_label_by_key.get(key, key))}</h3>'
            f'<p>{escape(strings["pokemon_count_label"].format(count=len(group)))}</p>'
            f'<div class="taxonomy-links">{compact_links(group)}</div>'
            f'</section>'
        )
    type_html = "\n".join(type_sections)

    generation_groups: dict[str, list[dict]] = defaultdict(list)
    generation_order = ["1", "2", "3", "4", "5plus", "unknown"]
    generation_labels = {
        "1": strings["generation_label"].format(gen=1),
        "2": strings["generation_label"].format(gen=2),
        "3": strings["generation_label"].format(gen=3),
        "4": strings["generation_label"].format(gen=4),
        "5plus": strings["generation_later_label"],
        "unknown": strings["unknown_generation"],
    }
    for card in cards:
        gen = card["generation"]
        if isinstance(gen, int) and 1 <= gen <= 4:
            key = str(gen)
        elif isinstance(gen, int) and gen >= 5:
            key = "5plus"
        else:
            key = "unknown"
        generation_groups[key].append(card)
    generation_sections = []
    for key in generation_order:
        if key not in generation_groups:
            continue
        group = sorted(generation_groups[key], key=lambda c: (-c["count"], c["name"]))
        generation_sections.append(
            f'<section class="taxonomy-card" id="generation-{key}">'
            f'<h3>{escape(generation_labels[key])}</h3>'
            f'<p>{escape(strings["pokemon_count_label"].format(count=len(group)))}</p>'
            f'<div class="taxonomy-links">{compact_links(group)}</div>'
            f'</section>'
        )
    generation_html = "\n".join(generation_sections)

    items_html = "".join(f"<li>{card_html(card)}</li>" for card in cards)

    # Popular intro text
    name_joiner = lang_config.get("pref_joiner", "・")
    top3_names = name_joiner.join(
        card["name"] for card in cards[:3]
    )
    top3_min_count = (
        min(card["count"] for card in cards[:3])
        if cards else 0
    )
    popular_intro = escape(
        strings["popular_intro"].format(top3=top3_names, min_count=top3_min_count)
    )

    all_heading = escape(strings["all_heading"].format(total=total_count))
    regional_heading = escape(strings["regional_heading"])
    h1 = escape(strings["h1"])
    lead = escape(strings["lead"])
    map_nav_hint = strings["map_nav_hint"].format(map_href=escape(map_href))
    cta = escape(strings["cta"])
    footer_text = escape(strings["footer"])
    breadcrumb_aria = escape(strings["breadcrumb_aria"])
    breadcrumb_home = escape(strings["breadcrumb_home"])

    jsonld_collection = json.dumps({
        "@context": "https://schema.org",
        "@type": "CollectionPage",
        "name": strings["jsonld_name"],
        "description": strings["description"],
        "url": canonical_url,
        "inLanguage": lang_config["html_lang"],
    }, ensure_ascii=False, indent=2)

    jsonld_breadcrumb = json.dumps({
        "@context": "https://schema.org",
        "@type": "BreadcrumbList",
        "itemListElement": [
            {"@type": "ListItem", "position": 1, "name": strings["breadcrumb_home"], "item": map_url},
            {"@type": "ListItem", "position": 2, "name": strings["jsonld_name"], "item": canonical_url},
        ],
    }, ensure_ascii=False, indent=2)

    jsonld_item_list = json.dumps({
        "@context": "https://schema.org",
        "@type": "ItemList",
        "name": strings["ranking_heading"],
        "itemListElement": [
            {
                "@type": "ListItem",
                "position": rank,
                "name": card["name"],
                "url": f"{BASE_URL}{url_prefix}pokemon/{quote(card['slug'])}/",
            }
            for rank, card in enumerate(cards[:10], start=1)
        ],
    }, ensure_ascii=False, indent=2)

    return f"""<!doctype html>
<html lang="{lang_config['html_lang']}">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{escape(strings['title'])}</title>
  <meta name="description" content="{escape(strings['description'])}">
  <meta name="robots" content="index,follow">
  <link rel="canonical" href="{escape(canonical_url)}">
{hreflang_html}

  <meta property="og:type" content="website">
  <meta property="og:locale" content="{lang_config['og_locale']}">
  <meta property="og:title" content="{escape(strings['og_title'])}">
  <meta property="og:description" content="{escape(strings['description'])}">
  <meta property="og:url" content="{escape(canonical_url)}">
  <meta property="og:image" content="{escape(DEFAULT_OGP_IMAGE)}">

  <meta name="twitter:card" content="summary_large_image">
  <meta name="twitter:title" content="{escape(strings['og_title'])}">
  <meta name="twitter:description" content="{escape(strings['description'])}">
  <meta name="twitter:image" content="{escape(DEFAULT_OGP_IMAGE)}">

  <script type="application/ld+json">
{jsonld_collection}
  </script>
  <script type="application/ld+json">
{jsonld_breadcrumb}
  </script>
  <script type="application/ld+json">
{jsonld_item_list}
  </script>

  <!-- Google Analytics -->
  <script async src="https://www.googletagmanager.com/gtag/js?id={GA_MEASUREMENT_ID}"></script>
  <script>
    window.dataLayer = window.dataLayer || [];
    function gtag(){{dataLayer.push(arguments);}}
    gtag('js', new Date());
    gtag('config', '{GA_MEASUREMENT_ID}', {{'page_path': '/{url_prefix}pokemon/', site_type: 'map', page_type: 'pokemon_index'}});
    gtag('event', 'view_pokemon_index', {{'pokemon_count': {total_count}, 'lang': '{lang}'}});
  </script>

  <style>
    * {{ box-sizing: border-box; margin: 0; padding: 0; }}
    html, body {{
      width: 100%;
      overflow-x: hidden;
    }}
    body {{
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif;
      line-height: 1.6;
      color: #333;
      background: #f7f8f3;
      padding: 16px;
      overflow-wrap: anywhere;
    }}
    .container {{
      width: 100%;
      max-width: 1080px;
      margin: 0 auto;
      background: white;
      border-radius: 8px;
      padding: 22px;
      box-shadow: 0 4px 16px rgba(0,0,0,0.08);
    }}
    .breadcrumb {{ font-size: 13px; color: #888; margin-bottom: 16px; }}
    .breadcrumb ol {{ list-style: none; display: flex; flex-wrap: wrap; gap: 4px; align-items: center; }}
    .breadcrumb li + li::before {{ content: "›"; margin-right: 4px; color: #ccc; }}
    .breadcrumb a {{ color: #6F55A3; text-decoration: none; }}
    .breadcrumb a:hover {{ text-decoration: underline; }}
    h1 {{
      font-size: 28px;
      font-weight: bold;
      color: #1a1a1a;
      margin-bottom: 8px;
    }}
    h2 {{
      font-size: 17px;
      font-weight: bold;
      color: #1a1a1a;
      margin: 24px 0 10px;
      padding-bottom: 6px;
      border-bottom: 2px solid #e0e0e0;
    }}
    .lead {{
      font-size: 15px;
      color: #555;
      line-height: 1.75;
      margin-bottom: 14px;
    }}
    .hub-grid, .poke-list, .regional-list, .featured-grid, .taxonomy-grid {{
      list-style: none;
      display: grid;
      gap: 10px;
    }}
    .hub-grid {{
      grid-template-columns: repeat(auto-fit, minmax(190px, 1fr));
      margin: 16px 0 8px;
    }}
    .hub-card {{
      display: block;
      padding: 14px;
      background: #f0faf9;
      border: 1px solid #c9e9e4;
      border-radius: 8px;
      color: #176f68;
      text-decoration: none;
      font-weight: bold;
      min-width: 0;
    }}
    .regional-list {{
      grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
    }}
    .poke-list {{
      grid-template-columns: repeat(auto-fill, minmax(230px, 1fr));
    }}
    .featured-grid {{
      grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
    }}
    .taxonomy-grid {{
      grid-template-columns: repeat(auto-fit, minmax(210px, 1fr));
    }}
    .poke-card a, .featured-card a, .regional-item a, .ranking-item a {{
      display: flex;
      flex-direction: column;
      overflow: hidden;
      background: #fafafa;
      border: 1px solid #e8e8e8;
      border-radius: 8px;
      text-decoration: none;
      color: #333;
      transition: border-color 0.15s, box-shadow 0.15s;
      height: 100%;
    }}
    .poke-card a:hover, .featured-card a:hover, .regional-item a:hover, .ranking-item a:hover, .hub-card:hover {{
      border-color: #6F55A3;
      box-shadow: 0 2px 8px rgba(111,85,163,0.12);
    }}
    .regional-item a {{
      background: #f5f0ff;
      border-color: #d8ccf0;
      padding: 0 0 12px;
    }}
    .card-photo, .regional-photo, .ranking-photo {{
      display: block;
      width: 100%;
      aspect-ratio: 16 / 9;
      background: #eee;
      overflow: hidden;
    }}
    .card-photo img, .regional-photo img, .ranking-photo img {{
      display: block;
      width: 100%;
      height: 100%;
      object-fit: cover;
    }}
    .poke-card-body {{
      display: flex;
      flex-direction: column;
      gap: 4px;
      padding: 10px 12px 12px;
    }}
    .poke-name {{
      font-size: 15px;
      font-weight: bold;
      color: #1a1a1a;
    }}
    .poke-en {{
      font-size: 12px;
      color: #888;
      margin-top: 1px;
    }}
    .poke-counts {{
      display: flex;
      flex-wrap: wrap;
      gap: 6px;
      font-size: 12px;
      font-weight: bold;
      color: #176f68;
    }}
    .poke-meta {{
      display: flex;
      flex-wrap: wrap;
      gap: 5px;
    }}
    .poke-chip {{
      display: inline-block;
      padding: 2px 7px;
      border-radius: 999px;
      background: #eef2e6;
      color: #46563a;
      font-size: 11px;
      line-height: 1.4;
    }}
    .poke-tagline {{
      font-size: 12px;
      color: #6F55A3;
      margin-top: 4px;
      font-weight: bold;
      padding: 0 12px;
    }}
    .poke-summary {{
      font-size: 12px;
      color: #666;
      margin-top: auto;
      padding-top: 4px;
    }}
    .regional-item .poke-name, .regional-item .poke-en, .regional-item .poke-summary {{
      padding-left: 12px;
      padding-right: 12px;
    }}
    .ranking-list {{
      list-style: none;
      display: grid;
      gap: 8px;
    }}
    .ranking-item a {{
      display: grid;
      grid-template-columns: 64px 116px minmax(0, 1fr);
      align-items: center;
      min-height: 82px;
      padding: 8px;
    }}
    .ranking-rank {{
      font-weight: bold;
      color: #6F55A3;
      text-align: center;
    }}
    .ranking-photo {{
      border-radius: 6px;
    }}
    .image-placeholder {{
      background: linear-gradient(135deg, #eef2e6, #f7f8f3);
      border: 1px solid #dde4d3;
    }}
    .ranking-main {{
      display: flex;
      flex-direction: column;
      gap: 3px;
      min-width: 0;
      padding-left: 10px;
    }}
    .popular-intro {{
      font-size: 13px;
      color: #555;
      line-height: 1.7;
      margin: 0 0 10px;
      padding: 10px 14px;
      background: #f5f0ff;
      border-left: 3px solid #6F55A3;
      border-radius: 0 6px 6px 0;
    }}
    .taxonomy-card {{
      border: 1px solid #e8e8e8;
      border-radius: 8px;
      padding: 12px;
      background: #fcfcfb;
    }}
    .taxonomy-card h3 {{
      font-size: 15px;
      margin-bottom: 2px;
    }}
    .taxonomy-card p {{
      font-size: 12px;
      color: #777;
      margin-bottom: 8px;
    }}
    .taxonomy-links {{
      display: flex;
      flex-wrap: wrap;
      gap: 6px;
    }}
    .taxonomy-links a {{
      display: inline-flex;
      gap: 5px;
      align-items: center;
      padding: 4px 8px;
      background: #f0ebfa;
      border-radius: 999px;
      color: #6F55A3;
      text-decoration: none;
      font-size: 12px;
      font-weight: bold;
    }}
    .taxonomy-links span {{
      color: #777;
      font-weight: normal;
    }}
    .map-nav-hint {{
      font-size: 13px;
      color: #666;
      margin: 16px 0 4px;
      text-align: center;
    }}
    .map-nav-hint a {{ color: #6F55A3; text-decoration: none; font-weight: bold; }}
    .map-nav-hint a:hover {{ text-decoration: underline; }}
    .cta-map {{
      display: block;
      background: #6F55A3;
      color: white;
      text-align: center;
      padding: 14px 24px;
      border-radius: 8px;
      text-decoration: none;
      font-size: 16px;
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
    @media (max-width: 620px) {{
      body {{ padding: 10px; }}
      .container {{
        width: auto;
        max-width: calc(100vw - 20px);
        padding: 16px;
      }}
      h1 {{ font-size: 24px; }}
      .hub-grid {{ grid-template-columns: 1fr; }}
      .ranking-item a {{
        grid-template-columns: 50px 84px minmax(0, 1fr);
      }}
    }}
  </style>
</head>
<body>
<div class="container">
  <nav aria-label="{breadcrumb_aria}" class="breadcrumb">
    <ol>
      <li><a href="{escape(map_href)}">{breadcrumb_home}</a></li>
      <li aria-current="page">{escape(strings['og_title'])}</li>
    </ol>
  </nav>

  <h1>{h1}</h1>
  <p class="lead">{lead}</p>
  <section aria-labelledby="hub-heading">
    <h2 id="hub-heading">{escape(strings["hub_heading"])}</h2>
    <div class="hub-grid">
      <a class="hub-card" href="#pokemon-list">{escape(strings["hub_name"])}</a>
      <a class="hub-card" href="#pokemon-ranking">{escape(strings["hub_ranking"])}</a>
      <a class="hub-card" href="#pokemon-types">{escape(strings["hub_taxonomy"])}</a>
      <a class="hub-card" href="{escape(map_href)}">{escape(strings["hub_map"])}</a>
    </div>
    <p class="map-nav-hint"><a href="{escape(summary_href)}">{escape(strings["summary_link"])}</a></p>
  </section>

  <section aria-labelledby="pokemon-ranking">
    <h2 id="pokemon-ranking">{escape(strings["ranking_heading"])}</h2>
    <ol class="ranking-list">
{ranking_html}
    </ol>
  </section>

  <section aria-labelledby="featured-pokemon">
    <h2 id="featured-pokemon">{escape(strings["featured_heading"])}</h2>
    <div class="featured-grid">
{featured_html}
    </div>
  </section>

  <h2>{regional_heading}</h2>
  <ul class="regional-list">
{regional_items_html}  </ul>

  <section aria-labelledby="pokemon-types">
    <h2 id="pokemon-types">{escape(strings["type_heading"])}</h2>
    <div class="taxonomy-grid">
{type_html}
    </div>
  </section>

  <section aria-labelledby="pokemon-generations">
    <h2 id="pokemon-generations">{escape(strings["generation_heading"])}</h2>
    <div class="taxonomy-grid">
{generation_html}
    </div>
  </section>

  <h2 id="pokemon-list">{all_heading}</h2>
  <p class="popular-intro">{popular_intro}</p>
  <ul class="poke-list">
{items_html}  </ul>

  <p class="map-nav-hint">{map_nav_hint}</p>

  <a href="{escape(map_url)}" class="cta-map">{cta}</a>

  <footer>
    <p><a href="{escape(BASE_URL)}">data.pokefuta.com</a> &mdash; {footer_text}</p>
  </footer>
</div>
</body>
</html>"""


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manholes", default="docs/pokefuta.ndjson")
    parser.add_argument("--pokemon", default="docs/pokemon_metadata.json")
    parser.add_argument("--photos", default="docs/latest-manhole-photos.json")
    parser.add_argument("--images", default="dataset/manhole/image")
    parser.add_argument(
        "--output-root", default="dist",
        help="Root output directory (default: dist). Index goes to {output-root}/pokemon/ for ja.",
    )
    parser.add_argument(
        "--langs", nargs="*", default=list(LANG_CONFIGS.keys()),
        help="Languages to generate (default: all).",
    )
    parser.add_argument(
        "--prefectures", default="apps/web/i18n/prefectures.json",
        help="Path to prefectures.json",
    )
    args = parser.parse_args()

    metadata = load_pokemon_metadata(Path(args.pokemon))
    if not metadata:
        logger.error("No pokemon metadata loaded")
        return 1

    manholes = read_manholes(Path(args.manholes))
    if not manholes:
        logger.error("No manholes loaded")
        return 1

    pref_data = load_prefectures(Path(args.prefectures))
    photos_data = load_photos(Path(args.photos))
    image_dir = Path(args.images)
    pokemon_index = build_pokemon_index(manholes, metadata)
    logger.info(f"Pokemon with active pokefuta: {len(pokemon_index)}")

    output_root = Path(args.output_root)
    langs_to_build = [la for la in args.langs if la in LANG_CONFIGS]
    if not langs_to_build:
        logger.error(f"No valid languages specified. Choose from: {list(LANG_CONFIGS.keys())}")
        return 1

    for lang in langs_to_build:
        lc = LANG_CONFIGS[lang]
        strings = LP_INDEX_STRINGS[lang]
        pref_key = lc["pref_key"]

        if pref_key is None:
            def translate_pref(ja: str, _key: str = "") -> str:
                return ja
        else:
            def translate_pref(ja: str, _key: str = pref_key) -> str:
                return pref_data.get(ja, {}).get(_key, ja)

        url_prefix = lc["url_prefix"]
        if url_prefix:
            output_dir = output_root / url_prefix.rstrip("/") / "pokemon"
        else:
            output_dir = output_root / "pokemon"

        output_dir.mkdir(parents=True, exist_ok=True)
        html = generate_html(
            pokemon_index, lang, lc, strings, translate_pref,
            photos_data, image_dir,
        )
        (output_dir / "index.html").write_text(html, encoding="utf-8")
        logger.info(f"[{lang}] Written: {output_dir}/index.html")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
