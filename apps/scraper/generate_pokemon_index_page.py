#!/usr/bin/env python3
"""Generate /pokemon/index.html — SEO hub listing all Pokemon with pokefuta."""

from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path
from urllib.parse import quote
from xml.sax.saxutils import escape

sys.path.insert(0, str(Path(__file__).parent))
from generate_pokemon_pages import (
    BASE_URL,
    DEFAULT_OGP_IMAGE,
    GA_MEASUREMENT_ID,
    _FORM_PREFIX,
    build_pokemon_index,
    load_pokemon_metadata,
    read_manholes,
)

logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger(__name__)

CANONICAL_URL = f"{BASE_URL}pokemon/"
TITLE = "ポケふたに登場するポケモン一覧 | 全国のポケモンマンホールマップ"
DESCRIPTION = (
    "全国各地に設置された「ポケふた（ポケモンマンホール）」に登場するポケモン一覧です。"
    "北海道のロコンや香川県のヤドン、宮城県のラプラスなど、地域を応援するポケモンとして"
    "描かれたポケふたも人気があります。気になるポケモンから、全国のポケふたや設置自治体を探せます。"
)

# 地域連携ポケモン（slug → 紹介文）
REGIONAL_POKEMON: list[tuple[str, str]] = [
    ("vulpix",       "北海道を応援するポケモン"),
    ("vulpix-alola", "北海道を応援するポケモン"),
    ("slowpoke",     "香川県を応援するポケモン"),
    ("lapras",       "宮城県を応援するポケモン"),
    ("geodude",      "岩手県を応援するポケモン"),
    ("chansey",      "福島県を応援するポケモン"),
]


def _get_display_name(slug: str, meta: dict) -> tuple[str, str]:
    names = meta.get("names", {})
    form = meta.get("form") or ""
    prefix = _FORM_PREFIX.get(form, "")
    name_ja = prefix + names.get("ja", slug)
    name_en = names.get("en", "")
    return name_ja, name_en


def _region_summary(manholes: list[dict], count: int) -> str:
    prefs = sorted({m.get("prefecture", "") for m in manholes if m.get("prefecture")})
    region_text = prefs[0] if len(prefs) == 1 else f"{len(prefs)}都道府県"
    return f"{count}枚 / {region_text}"


def _card_html(slug: str, meta: dict, manholes: list[dict], css_class: str = "poke-item") -> str:
    name_ja, name_en = _get_display_name(slug, meta)
    count = len(manholes)
    summary = _region_summary(manholes, count)
    en_html = f"<span class='poke-en'>{escape(name_en)}</span>" if name_en else ""
    return (
        f"<li class='{css_class}'>"
        f"<a href='/pokemon/{quote(slug)}/'>"
        f"<span class='poke-name'>{escape(name_ja)}</span>"
        f"{en_html}"
        f"<span class='poke-summary'>{escape(summary)}</span>"
        f"</a></li>"
    )


def generate_html(pokemon_index: dict[str, tuple[dict, list[dict]]]) -> str:
    total_count = len(pokemon_index)

    # 地域連携セクション
    regional_items: list[str] = []
    for slug, tagline in REGIONAL_POKEMON:
        if slug not in pokemon_index:
            continue
        meta, manholes = pokemon_index[slug]
        name_ja, name_en = _get_display_name(slug, meta)
        count = len(manholes)
        summary = _region_summary(manholes, count)
        en_html = f"<span class='poke-en'>{escape(name_en)}</span>" if name_en else ""
        regional_items.append(
            f"<li class='regional-item'>"
            f"<a href='/pokemon/{quote(slug)}/'>"
            f"<span class='poke-name'>{escape(name_ja)}</span>"
            f"{en_html}"
            f"<span class='poke-tagline'>{escape(tagline)}</span>"
            f"<span class='poke-summary'>{escape(summary)}</span>"
            f"</a></li>"
        )
    regional_items_html = "\n".join(regional_items) + "\n" if regional_items else ""

    # 全ポケモン一覧（登場マンホール数の多い順）
    sorted_slugs = sorted(
        pokemon_index.keys(),
        key=lambda s: -len(pokemon_index[s][1]),
    )
    items: list[str] = []
    for slug in sorted_slugs:
        meta, manholes = pokemon_index[slug]
        items.append(_card_html(slug, meta, manholes))
    items_html = "".join(items)

    jsonld_collection = json.dumps({
        "@context": "https://schema.org",
        "@type": "CollectionPage",
        "name": "ポケふたに登場するポケモン一覧",
        "description": DESCRIPTION,
        "url": CANONICAL_URL,
        "inLanguage": "ja",
    }, ensure_ascii=False, indent=2)

    jsonld_breadcrumb = json.dumps({
        "@context": "https://schema.org",
        "@type": "BreadcrumbList",
        "itemListElement": [
            {"@type": "ListItem", "position": 1, "name": "全国マップ", "item": BASE_URL},
            {"@type": "ListItem", "position": 2, "name": "ポケモン一覧", "item": CANONICAL_URL},
        ],
    }, ensure_ascii=False, indent=2)

    return f"""<!doctype html>
<html lang="ja">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{escape(TITLE)}</title>
  <meta name="description" content="{escape(DESCRIPTION)}">
  <meta name="robots" content="index,follow">
  <link rel="canonical" href="{escape(CANONICAL_URL)}">

  <meta property="og:type" content="website">
  <meta property="og:locale" content="ja_JP">
  <meta property="og:title" content="ポケふたに登場するポケモン一覧">
  <meta property="og:description" content="{escape(DESCRIPTION)}">
  <meta property="og:url" content="{escape(CANONICAL_URL)}">
  <meta property="og:image" content="{escape(DEFAULT_OGP_IMAGE)}">

  <meta name="twitter:card" content="summary_large_image">
  <meta name="twitter:title" content="ポケふたに登場するポケモン一覧">
  <meta name="twitter:description" content="{escape(DESCRIPTION)}">
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
    gtag('config', '{GA_MEASUREMENT_ID}', {{'page_path': '/pokemon/'}});
    gtag('event', 'view_pokemon_index', {{'pokemon_count': {total_count}}});
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
    /* 共通カードリスト */
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
  <nav aria-label="パンくずリスト" class="breadcrumb">
    <ol>
      <li><a href="/">全国マップ</a></li>
      <li aria-current="page">ポケモン一覧</li>
    </ol>
  </nav>

  <h1>ポケふたに登場するポケモン一覧</h1>
  <p class="lead">
    全国各地に設置された「ポケふた（ポケモンマンホール）」に登場するポケモン一覧です。
    北海道のロコンや香川県のヤドン、宮城県のラプラスなど、地域を応援するポケモンとして描かれたポケふたも人気があります。
    気になるポケモンから、全国のポケふたや設置自治体を探せます。
  </p>

  <h2>地域を応援するポケモン</h2>
  <ul class="regional-list">
{regional_items_html}  </ul>

  <h2>全ポケモン一覧（{total_count}体）</h2>
  <ul class="poke-list">
{items_html}  </ul>

  <a href="{escape(BASE_URL)}" class="cta-map">地図で全国のポケふたを探す →</a>

  <footer>
    <p><a href="{escape(BASE_URL)}">data.pokefuta.com</a> &mdash; ポケモンマンホール全国マップ</p>
  </footer>
</div>
</body>
</html>"""


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manholes", default="docs/pokefuta.ndjson")
    parser.add_argument("--pokemon", default="docs/pokemon_metadata.json")
    parser.add_argument("--output", default="dist/pokemon")
    args = parser.parse_args()

    metadata = load_pokemon_metadata(Path(args.pokemon))
    if not metadata:
        logger.error("No pokemon metadata loaded")
        return 1

    manholes = read_manholes(Path(args.manholes))
    if not manholes:
        logger.error("No manholes loaded")
        return 1

    pokemon_index = build_pokemon_index(manholes, metadata)
    logger.info(f"Pokemon with active pokefuta: {len(pokemon_index)}")

    output_dir = Path(args.output)
    output_dir.mkdir(parents=True, exist_ok=True)

    html = generate_html(pokemon_index)
    (output_dir / "index.html").write_text(html, encoding="utf-8")
    logger.info(f"Written: {output_dir}/index.html")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
