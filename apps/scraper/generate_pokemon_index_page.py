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
        "title": "ポケふたに登場するポケモン一覧 | 全国のポケモンマンホールマップ",
        "description": (
            "全国各地に設置された「ポケふた（ポケモンマンホール）」に登場するポケモン一覧です。"
            "北海道のロコンや香川県のヤドン、宮城県のラプラスなど、地域を応援するポケモンとして"
            "描かれたポケふたも人気があります。気になるポケモンから、全国のポケふたや設置自治体を探せます。"
        ),
        "og_title": "ポケふたに登場するポケモン一覧",
        "h1": "ポケふたに登場するポケモン一覧",
        "lead": (
            "全国各地に設置された「ポケふた（ポケモンマンホール）」に登場するポケモン一覧です。"
            "北海道のロコンや香川県のヤドン、宮城県のラプラスなど、地域を応援するポケモンとして描かれたポケふたも人気があります。"
            "気になるポケモンから、全国のポケふたや設置自治体を探せます。"
        ),
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
        "popular_intro": (
            "登場回数が多いポケモンほど、全国各地で出会いやすいポケモンです。"
            "{top3}などは{min_count}枚以上のポケふたに登場しており、"
            "初めてポケふた巡りをする方にも見つけやすいポケモンです。"
            "気になるポケモンをタップして、設置場所や旅のルートを確認しましょう。"
        ),
        "jsonld_name": "ポケふたに登場するポケモン一覧",
    },
    "en": {
        "title": "Pokémon on Pokéfuta — Full List | Pokémon Manhole Map of Japan",
        "description": (
            "Complete list of Pokémon featured on Pokéfuta (Pokémon manhole covers) installed across Japan. "
            "Includes regional favorites such as Vulpix in Hokkaido, Slowpoke in Kagawa, and Lapras in Miyagi. "
            "Find Pokéfuta locations and municipalities for any Pokémon you love."
        ),
        "og_title": "Pokémon on Pokéfuta — Full List",
        "h1": "Pokémon on Pokéfuta — Full List",
        "lead": (
            "Complete list of Pokémon featured on Pokéfuta (Pokémon manhole covers) installed across Japan. "
            "Includes regional favorites such as Vulpix in Hokkaido, Slowpoke in Kagawa, and Lapras in Miyagi. "
            "Tap any Pokémon to see installation locations and plan your trip."
        ),
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
        "popular_intro": (
            "Pokémon that appear on more Pokéfuta are easier to find across Japan. "
            "{top3} and others appear on {min_count}+ Pokéfuta, "
            "making them great starting points for first-time Pokéfuta hunters. "
            "Tap any Pokémon to check locations and plan your route."
        ),
        "jsonld_name": "Pokémon on Pokéfuta — Full List",
    },
    "zh-CN": {
        "title": "宝可夢井盖上的宝可梦一览 | 日本宝可梦井盖地图",
        "description": (
            "日本各地设置的「宝可梦井盖（Pokéfuta）」上登场的宝可梦一览。"
            "包括北海道的六尾、香川县的呆呆兽、宫城县的拉普拉斯等代表各地区的宝可梦。"
            "从喜欢的宝可梦查找全国各地的宝可梦井盖和设置市区町村。"
        ),
        "og_title": "宝可梦井盖上的宝可梦一览",
        "h1": "宝可梦井盖上的宝可梦一览",
        "lead": (
            "日本各地设置的「宝可梦井盖（Pokéfuta）」上登场的宝可梦一览。"
            "包括北海道的六尾、香川县的呆呆兽、宫城县的拉普拉斯等代表各地区的宝可梦。"
            "点击感兴趣的宝可梦，查看设置地点并规划行程。"
        ),
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
        "popular_intro": (
            "登场次数越多的宝可梦，越容易在全国各地相遇。"
            "{top3}等宝可梦登场的宝可梦井盖达{min_count}个以上，"
            "非常适合初次挑战宝可梦井盖打卡的玩家。"
            "点击感兴趣的宝可梦，确认设置地点和旅行路线。"
        ),
        "jsonld_name": "宝可梦井盖上的宝可梦一览",
    },
    "zh-TW": {
        "title": "寶可夢人孔蓋上的寶可夢一覽 | 日本寶可夢人孔蓋地圖",
        "description": (
            "日本各地設置的「寶可夢人孔蓋（Pokéfuta）」上登場的寶可夢一覽。"
            "包括北海道的六尾、香川縣的呆呆獸、宮城縣的拉普拉斯等代表各地區的寶可夢。"
            "從喜歡的寶可夢查找全國各地的寶可夢人孔蓋和設置市區町村。"
        ),
        "og_title": "寶可夢人孔蓋上的寶可夢一覽",
        "h1": "寶可夢人孔蓋上的寶可夢一覽",
        "lead": (
            "日本各地設置的「寶可夢人孔蓋（Pokéfuta）」上登場的寶可夢一覽。"
            "包括北海道的六尾、香川縣的呆呆獸、宮城縣的拉普拉斯等代表各地區的寶可夢。"
            "點擊感興趣的寶可夢，查看設置地點並規劃行程。"
        ),
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
        "popular_intro": (
            "登場次數越多的寶可夢，越容易在全國各地相遇。"
            "{top3}等寶可夢登場的寶可夢人孔蓋達{min_count}個以上，"
            "非常適合初次挑戰寶可夢人孔蓋打卡的玩家。"
            "點擊感興趣的寶可夢，確認設置地點和旅行路線。"
        ),
        "jsonld_name": "寶可夢人孔蓋上的寶可夢一覽",
    },
    "ko": {
        "title": "포케후타에 등장하는 포켓몬 목록 | 일본 포켓몬 맨홀 지도",
        "description": (
            "일본 전국에 설치된 「포케후타（포켓몬 맨홀）」에 등장하는 포켓몬 목록입니다. "
            "홋카이도의 식스테일, 카가와현의 야돈, 미야기현의 라프라스 등 지역을 응원하는 포켓몬도 인기입니다. "
            "좋아하는 포켓몬으로 전국의 포케후타와 설치 지자체를 찾아보세요."
        ),
        "og_title": "포케후타에 등장하는 포켓몬 목록",
        "h1": "포케후타에 등장하는 포켓몬 목록",
        "lead": (
            "일본 전국에 설치된 「포케후타（포켓몬 맨홀）」에 등장하는 포켓몬 목록입니다. "
            "홋카이도의 식스테일, 카가와현의 야돈, 미야기현의 라프라스 등 지역을 응원하는 포켓몬도 인기입니다. "
            "좋아하는 포켓몬을 탭해서 설치 장소와 여행 루트를 확인해 보세요."
        ),
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
) -> str:
    total_count = len(pokemon_index)
    url_prefix = lang_config["url_prefix"]
    map_href = f"/{url_prefix}" if url_prefix else "/"
    pokemon_list_url = f"/{url_prefix}pokemon/" if url_prefix else "/pokemon/"
    canonical_url = f"{BASE_URL}{url_prefix}pokemon/"
    map_url = f"{BASE_URL}{url_prefix}"

    hreflang_html = _hreflang_links_index()

    # Regional Pokémon section
    regional_items: list[str] = []
    for slug in REGIONAL_POKEMON_SLUGS:
        if slug not in pokemon_index:
            continue
        meta, manholes = pokemon_index[slug]
        display_name = _get_display_name(meta, lang_config)
        name_en = meta.get("names", {}).get("en", "")
        count = len(manholes)
        summary = _region_summary(manholes, count, strings, translate_pref)
        tagline = REGIONAL_TAGLINES.get(slug, {}).get(lang, REGIONAL_TAGLINES.get(slug, {}).get("en", ""))
        en_html = f"<span class='poke-en'>{escape(name_en)}</span>" if name_en and lang != "en" else ""
        regional_items.append(
            f"<li class='regional-item'>"
            f"<a href='/{url_prefix}pokemon/{quote(slug)}/'>"
            f"<span class='poke-name'>{escape(display_name)}</span>"
            f"{en_html}"
            f"<span class='poke-tagline'>{escape(tagline)}</span>"
            f"<span class='poke-summary'>{escape(summary)}</span>"
            f"</a></li>"
        )
    regional_items_html = "\n".join(regional_items) + "\n" if regional_items else ""

    # All Pokémon list sorted by manhole count (descending)
    sorted_slugs = sorted(
        pokemon_index.keys(),
        key=lambda s: -len(pokemon_index[s][1]),
    )
    items: list[str] = []
    for slug in sorted_slugs:
        meta, manholes = pokemon_index[slug]
        display_name = _get_display_name(meta, lang_config)
        name_en = meta.get("names", {}).get("en", "")
        count = len(manholes)
        summary = _region_summary(manholes, count, strings, translate_pref)
        en_html = f"<span class='poke-en'>{escape(name_en)}</span>" if name_en and lang != "en" else ""
        items.append(
            f"<li class='poke-item'>"
            f"<a href='/{url_prefix}pokemon/{quote(slug)}/'>"
            f"<span class='poke-name'>{escape(display_name)}</span>"
            f"{en_html}"
            f"<span class='poke-summary'>{escape(summary)}</span>"
            f"</a></li>"
        )
    items_html = "".join(items)

    # Popular intro text
    top3_names = "・".join(
        _get_display_name(pokemon_index[s][0], lang_config)
        for s in sorted_slugs[:3]
    )
    top3_min_count = (
        min(len(pokemon_index[s][1]) for s in sorted_slugs[:3])
        if sorted_slugs else 0
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

  <!-- Google Analytics -->
  <script async src="https://www.googletagmanager.com/gtag/js?id={GA_MEASUREMENT_ID}"></script>
  <script>
    window.dataLayer = window.dataLayer || [];
    function gtag(){{dataLayer.push(arguments);}}
    gtag('js', new Date());
    gtag('config', '{GA_MEASUREMENT_ID}', {{'page_path': '/{url_prefix}pokemon/'}});
    gtag('event', 'view_pokemon_index', {{'pokemon_count': {total_count}, 'lang': '{lang}'}});
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
    .breadcrumb {{ font-size: 13px; color: #888; margin-bottom: 16px; }}
    .breadcrumb ol {{ list-style: none; display: flex; flex-wrap: wrap; gap: 4px; align-items: center; }}
    .breadcrumb li + li::before {{ content: "›"; margin-right: 4px; color: #ccc; }}
    .breadcrumb a {{ color: #6F55A3; text-decoration: none; }}
    .breadcrumb a:hover {{ text-decoration: underline; }}
    h1 {{
      font-size: 24px;
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
      font-size: 14px;
      color: #555;
      line-height: 1.75;
      margin-bottom: 4px;
    }}
    .poke-list, .regional-list {{
      list-style: none;
      display: grid;
      gap: 6px;
    }}
    .regional-list {{
      grid-template-columns: repeat(auto-fill, minmax(200px, 1fr));
    }}
    .poke-list {{
      grid-template-columns: repeat(auto-fill, minmax(180px, 1fr));
    }}
    .poke-item a, .regional-item a {{
      display: flex;
      flex-direction: column;
      padding: 8px 12px;
      background: #fafafa;
      border: 1px solid #e8e8e8;
      border-radius: 8px;
      text-decoration: none;
      color: #333;
      transition: border-color 0.15s, box-shadow 0.15s;
      height: 100%;
    }}
    .poke-item a:hover, .regional-item a:hover {{
      border-color: #6F55A3;
      box-shadow: 0 2px 8px rgba(111,85,163,0.12);
    }}
    .regional-item a {{
      background: #f5f0ff;
      border-color: #d8ccf0;
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
    .poke-tagline {{
      font-size: 12px;
      color: #6F55A3;
      margin-top: 4px;
      font-weight: bold;
    }}
    .poke-summary {{
      font-size: 12px;
      color: #666;
      margin-top: auto;
      padding-top: 4px;
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

  <h2>{regional_heading}</h2>
  <ul class="regional-list">
{regional_items_html}  </ul>

  <h2>{all_heading}</h2>
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
        html = generate_html(pokemon_index, lang, lc, strings, translate_pref)
        (output_dir / "index.html").write_text(html, encoding="utf-8")
        logger.info(f"[{lang}] Written: {output_dir}/index.html")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
