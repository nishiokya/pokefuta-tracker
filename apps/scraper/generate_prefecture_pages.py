#!/usr/bin/env python3
"""Generate static Japanese landing pages for all 47 prefectures."""

from __future__ import annotations

import argparse
import json
from collections import Counter
from datetime import datetime
from pathlib import Path
from urllib.parse import quote
from xml.sax.saxutils import escape

try:
    from apps.scraper.prefectures import (
        PREFECTURES,
        PREFECTURE_ORDER,
        PREFECTURE_SLUGS,
    )
except ModuleNotFoundError as exc:
    if exc.name != "apps":
        raise
    from prefectures import PREFECTURES, PREFECTURE_ORDER, PREFECTURE_SLUGS

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_MANHOLES = ROOT / "docs" / "pokefuta.ndjson"
DEFAULT_POKEMON = ROOT / "docs" / "pokemon_metadata.json"
DEFAULT_TRIVIA = ROOT / "dataset" / "prefecture_trivia.json"
DEFAULT_OUTPUT = ROOT / "dist" / "prefectures"
BASE_URL = "https://data.pokefuta.com"
OG_IMAGE = f"{BASE_URL}/assets/ogp/pokefuta_summary_ogp.png"

REGIONS: list[tuple[str, list[str]]] = [
    ("北海道・東北", PREFECTURE_ORDER[0:7]),
    ("関東", PREFECTURE_ORDER[7:14]),
    ("中部", PREFECTURE_ORDER[14:23]),
    ("近畿", PREFECTURE_ORDER[23:30]),
    ("中国", PREFECTURE_ORDER[30:35]),
    ("四国", PREFECTURE_ORDER[35:39]),
    ("九州・沖縄", PREFECTURE_ORDER[39:47]),
]

FORM_PREFIX = {
    "alola": "アローラ",
    "galar": "ガラル",
    "hisui": "ヒスイ",
    "paldea": "パルデア",
}


def load_records(path: Path) -> list[dict]:
    by_id: dict[str, dict] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            record = json.loads(line)
        except json.JSONDecodeError:
            continue
        record_id = str(record.get("id", "")).strip()
        if not record_id:
            continue
        by_id[record_id] = {**by_id.get(record_id, {}), **record}
    return [
        record for record in by_id.values()
        if record.get("status", "active") == "active"
    ]


def _normalize_katakana(text: str) -> str:
    return "".join(
        chr(ord(char) + 0x60) if "ぁ" <= char <= "ゖ" else char
        for char in text
    )


def load_pokemon_slugs(path: Path) -> dict[str, str]:
    result: dict[str, str] = {}
    for pokemon in json.loads(path.read_text(encoding="utf-8")):
        if not isinstance(pokemon, dict):
            continue
        name = pokemon.get("names", {}).get("ja", "")
        slug = pokemon.get("slug", "")
        form = pokemon.get("form") or ""
        if not name or not slug:
            continue
        if name not in result or not form:
            result[name] = slug
        prefix = FORM_PREFIX.get(form)
        if prefix:
            result.setdefault(prefix + name, slug)
    for name, slug in list(result.items()):
        result.setdefault(_normalize_katakana(name), slug)
    return result


def load_trivia(path: Path) -> dict[str, dict]:
    if not path.exists():
        return {}
    try:
        entries = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return {
        entry["prefecture"]: entry
        for entry in entries
        if isinstance(entry, dict) and entry.get("prefecture")
    }


def build_rankings(records: list[dict]) -> dict[str, int | None]:
    counts = Counter(record.get("prefecture", "") for record in records)
    installed_counts = [
        counts[pref] for pref in PREFECTURE_ORDER if counts[pref] > 0
    ]
    return {
        pref: (
            1 + sum(other > counts[pref] for other in installed_counts)
            if counts[pref]
            else None
        )
        for pref in PREFECTURE_ORDER
    }


def _clean_pokemons(record: dict) -> list[str]:
    return [
        pokemon for pokemon in record.get("pokemons", [])
        if isinstance(pokemon, str)
        and pokemon.strip()
        and "ローカルActs" not in pokemon
    ]


def _json_for_script(value: object) -> str:
    return json.dumps(value, ensure_ascii=False).replace("</", "<\\/")


def _trivia_html(prefecture: str, trivia_entry: dict | None, count: int) -> str:
    entries = (trivia_entry or {}).get("trivia", [])
    selected = entries[0] if entries else None
    if selected:
        source_url = str(selected.get("source_url", "")).strip()
        source = ""
        if source_url.startswith("https://"):
            source = (
                f'<a href="{escape(source_url)}" target="_blank" '
                f'rel="noopener noreferrer">'
                f'{escape(selected.get("source_label", "出典"))}</a>'
            )
        return (
            f'<p>{escape(selected["text"])}</p>'
            f'<div class="trivia-source">{source}</div>'
        )
    if count:
        municipalities = (trivia_entry or {}).get("municipality_count", 0)
        return (
            f"<p>{escape(prefecture)}では{count}枚のポケふたを"
            f"{municipalities}自治体で巡れます。</p>"
        )
    return (
        f"<p>{escape(prefecture)}では、現在ポケふたの設置を確認できていません。"
        "今後の新しい設置情報をお待ちください。</p>"
    )


def _record_date(record: dict) -> datetime | None:
    for key in ("first_seen", "added_at", "last_updated"):
        value = str(record.get(key, "")).strip()
        if not value:
            continue
        try:
            return datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            continue
    return None


def _format_year_month(date: datetime) -> str:
    return f"{date.year}年{date.month}月"


def _hero_summary(
    prefecture: str,
    count: int,
    records: list[dict],
    trivia_entry: dict | None,
) -> str:
    if not count:
        return f"{prefecture}は現在未設置。新しい設置情報を追跡中です。"

    cities = {
        str(record.get("city", "")).strip()
        for record in records
        if str(record.get("city", "")).strip()
    }
    municipalities = (trivia_entry or {}).get("municipality_count", 0) or len(cities)
    first_dates = [date for record in records if (date := _record_date(record))]
    first_month = _format_year_month(min(first_dates)) if first_dates else ""
    if first_month:
        return (
            f"{prefecture}は{first_month}にポケふた初登場。"
            f"現在は{municipalities}自治体で{count}枚を巡れます。"
        )
    return f"{prefecture}では{municipalities}自治体で{count}枚のポケふたを巡れます。"


def _pokemon_card(name: str, count: int, pokemon_slugs: dict[str, str]) -> str:
    slug = pokemon_slugs.get(name) or pokemon_slugs.get(_normalize_katakana(name))
    content = (
        f"<strong>{escape(name)}</strong>"
        f"<span>{count}枚のポケふたに登場</span>"
    )
    if slug:
        return (
            f'<a class="pokemon-card" href="/pokemon/{quote(slug)}/" '
            f'data-track="prefecture_pokemon_click" '
            f'data-destination="{escape(slug)}">{content}</a>'
        )
    return f'<article class="pokemon-card">{content}</article>'


def _pokemon_cards(records: list[dict], pokemon_slugs: dict[str, str]) -> str:
    counts = Counter(
        pokemon
        for record in records
        for pokemon in set(_clean_pokemons(record))
    )
    if not counts:
        return '<p class="empty-state">現在、掲載できるポケモンはいません。</p>'
    ranked = sorted(counts.items(), key=lambda item: (-item[1], item[0]))
    featured = "".join(
        _pokemon_card(name, count, pokemon_slugs)
        for name, count in ranked[:12]
    )
    remaining = ranked[12:]
    if not remaining:
        return featured
    more = "".join(
        _pokemon_card(name, count, pokemon_slugs)
        for name, count in remaining
    )
    return (
        f'{featured}<details class="pokemon-more">'
        f'<summary>ほか{len(remaining)}種類のポケモンを見る</summary>'
        f'<div class="pokemon-more-grid">{more}</div>'
        f'</details>'
    )


def _manhole_cards(records: list[dict]) -> str:
    if not records:
        return '<p class="empty-state">現在、この都道府県のポケふたは未設置です。</p>'
    cards = []
    for position, record in enumerate(
        sorted(records, key=lambda item: (item.get("city", ""), str(item.get("id", "")))),
        start=1,
    ):
        mid = str(record.get("id", "")).strip()
        city = record.get("city", "") or "所在地不明"
        pokemons = "・".join(_clean_pokemons(record)) or "ポケモン"
        image_path = ROOT / "dataset" / "manhole" / "image" / f"{mid}_latest.jpeg"
        image_html = (
            f'<img src="/manhole/image/{quote(mid)}_latest.jpeg" '
            f'alt="{escape(city)}のポケふた" loading="lazy" width="128" height="128">'
            if image_path.exists()
            else '<span class="manhole-placeholder" aria-hidden="true">●</span>'
        )
        cards.append(
            f'<a class="manhole-card" href="/manholes/{quote(mid)}/" '
            f'data-track="prefecture_manhole_click" data-position="{position}" '
            f'data-destination="{escape(mid)}">'
            f'{image_html}<span class="manhole-copy"><strong>{escape(city)}</strong>'
            f'<small>{escape(pokemons)}</small></span></a>'
        )
    return "".join(cards)


def _related_prefectures(prefecture: str) -> str:
    region_name = ""
    region_prefs: list[str] = []
    for name, prefectures in REGIONS:
        if prefecture in prefectures:
            region_name = name
            region_prefs = prefectures
            break
    links = "".join(
        f'<a href="/prefectures/{PREFECTURE_SLUGS[name]}/">{escape(name)}</a>'
        for name in region_prefs
        if name != prefecture
    )
    return (
        f'<p class="related-label">{escape(region_name)}のポケふた</p>'
        f'<div class="related-links">{links}</div>'
    )


def _hero_intro(
    prefecture: str,
    count: int,
    trivia_entry: dict | None,
) -> str:
    if not count:
        return (
            f"{prefecture}では、現在ポケふたの設置を確認できていません。"
            "新しい設置情報が入り次第、このページへ追加します。"
        )

    municipality_count = (trivia_entry or {}).get("municipality_count", 0)
    intro = f"{prefecture}には{count}枚のポケふたがあります。"
    if municipality_count:
        intro += f"県内{municipality_count}自治体に広がっています。"
    trivia = (trivia_entry or {}).get("trivia", [])
    if trivia and trivia[0].get("text"):
        fact = str(trivia[0]["text"]).rstrip("。")
        intro += f"{fact}。"
    return intro


def build_page(
    prefecture: str,
    slug: str,
    records: list[dict],
    rank: int | None,
    pokemon_slugs: dict[str, str],
    trivia_entry: dict | None,
) -> str:
    count = len(records)
    canonical = f"{BASE_URL}/prefectures/{slug}/"
    title = (
        f"{prefecture}のポケふた{count}枚｜設置場所マップ・ポケモン一覧"
        if count
        else f"{prefecture}のポケふた｜設置状況・ポケモンマンホール情報"
    )
    description = (
        f"{prefecture}にあるポケふた{count}枚の設置場所、登場ポケモン、"
        f"マンホール一覧、全国順位を紹介します。"
        "旅行やポケふた巡りの計画にご活用ください。"
        if count
        else (
            f"{prefecture}のポケふた設置状況を紹介します。"
            "現在の設置枚数や全国のポケモンマンホール情報を確認できます。"
        )
    )
    rank_label = f"全国{rank}位" if rank else "現在未設置"
    hero_intro = _hero_intro(prefecture, count, trivia_entry)
    hero_summary = _hero_summary(prefecture, count, records, trivia_entry)
    map_points = [
        {
            "id": str(record.get("id", "")),
            "lat": record.get("lat"),
            "lng": record.get("lng"),
            "city": record.get("city", ""),
            "pokemons": _clean_pokemons(record),
        }
        for record in records
        if isinstance(record.get("lat"), (int, float))
        and isinstance(record.get("lng"), (int, float))
    ]
    map_href = f"/?pref={quote(prefecture)}"
    pokemon_html = _pokemon_cards(records, pokemon_slugs)
    manhole_html = _manhole_cards(records)
    trivia_html = _trivia_html(prefecture, trivia_entry, count)
    related_html = _related_prefectures(prefecture)
    map_empty_class = " map-empty" if not map_points else ""
    json_ld = {
        "@context": "https://schema.org",
        "@type": "CollectionPage",
        "name": title,
        "description": description,
        "url": canonical,
        "isPartOf": {"@type": "WebSite", "name": "Pokefuta Map", "url": BASE_URL},
        "breadcrumb": {
            "@type": "BreadcrumbList",
            "itemListElement": [
                {"@type": "ListItem", "position": 1, "name": "全国マップ", "item": f"{BASE_URL}/"},
                {"@type": "ListItem", "position": 2, "name": "全国一覧", "item": f"{BASE_URL}/summary/"},
                {"@type": "ListItem", "position": 3, "name": prefecture, "item": canonical},
            ],
        },
    }

    return f"""<!doctype html>
<html lang="ja">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{escape(title)}</title>
  <meta name="description" content="{escape(description)}">
  <meta name="robots" content="index,follow">
  <meta property="og:type" content="website">
  <meta property="og:locale" content="ja_JP">
  <meta property="og:title" content="{escape(title)}">
  <meta property="og:description" content="{escape(description)}">
  <meta property="og:url" content="{escape(canonical)}">
  <meta property="og:image" content="{OG_IMAGE}">
  <meta name="twitter:card" content="summary_large_image">
  <meta name="twitter:title" content="{escape(title)}">
  <meta name="twitter:description" content="{escape(description)}">
  <meta name="twitter:image" content="{OG_IMAGE}">
  <link rel="canonical" href="{escape(canonical)}">
  <link rel="icon" href="/assets/pokefuta-marker.svg" type="image/svg+xml">
  <link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css"
    integrity="sha256-p4NxAoJBhIIN+hmNHrzRCf9tD/miZyoHS5obTRR9BMY=" crossorigin="">
  <script type="application/ld+json">{_json_for_script(json_ld)}</script>
  <style>
    :root {{ color-scheme: light; }}
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0; background: #f7f0df; color: #201b16;
      font-family: system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
      line-height: 1.65;
    }}
    a {{ color: #176f68; }}
    .page {{ max-width: 1040px; margin: 0 auto; padding: 20px 16px 56px; }}
    .breadcrumb {{ display: flex; gap: 8px; font-size: .82rem; font-weight: 800; }}
    .breadcrumb a {{ text-decoration: none; }}
    .hero {{
      position: relative; overflow: hidden; margin-top: 14px; padding: 28px;
      display: grid; grid-template-columns: minmax(0, 1fr) 280px; gap: 22px;
      align-items: center;
      border: 1px solid rgba(93,67,35,.15); border-radius: 24px;
      background: linear-gradient(135deg, #fffaf0, #f0e9fb);
      box-shadow: 0 14px 32px rgba(77,56,30,.08);
    }}
    .hero::after {{
      content: ""; position: absolute; width: 230px; height: 230px;
      right: -70px; top: -90px; border: 42px solid rgba(126,107,169,.1);
      border-radius: 50%;
    }}
    .hero-kicker {{ margin: 0; color: #6b4aa2; font-size: .8rem; font-weight: 900; }}
    h1 {{ margin: 4px 0 8px; font-size: clamp(2rem, 7vw, 3.5rem); line-height: 1.15; }}
    .hero p:last-of-type {{ max-width: 720px; margin: 0; color: #574b41; font-weight: 650; }}
    .hero-summary {{
      position: relative; z-index: 1; padding: 16px 18px; border-radius: 17px;
      background: rgba(255,255,255,.74); color: #3a3128;
      box-shadow: inset 0 0 0 1px rgba(93,67,35,.11);
    }}
    .hero-summary span {{
      display: block; margin-bottom: 6px; color: #6b4aa2;
      font-size: .76rem; font-weight: 900;
    }}
    .hero-summary p {{ margin: 0; font-size: .96rem; font-weight: 800; }}
    .stats {{ display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 10px; margin-top: 18px; }}
    .stat {{ padding: 14px; border-radius: 15px; background: rgba(255,255,255,.72); }}
    .stat span {{ display: block; color: #75685c; font-size: .76rem; font-weight: 850; }}
    .stat strong {{ display: block; color: #57408f; font-size: 1.55rem; line-height: 1.3; }}
    .hero-actions {{ display: flex; flex-wrap: wrap; gap: 10px; margin-top: 18px; }}
    .button {{
      display: inline-flex; align-items: center; min-height: 44px; padding: 0 16px;
      border-radius: 999px; background: #176f68; color: white; font-weight: 900;
      text-decoration: none;
    }}
    .button.secondary {{ background: #6b4aa2; }}
    .button.pokefuta {{ background: #b5483c; }}
    .button.photo {{ background: #2d846c; }}
    section {{
      margin-top: 22px; padding: 20px; border: 1px solid rgba(93,67,35,.14);
      border-radius: 19px; background: #fffaf0;
      box-shadow: 0 8px 20px rgba(77,56,30,.05);
    }}
    h2 {{ margin: 0 0 12px; font-size: 1.35rem; line-height: 1.35; }}
    #prefecture-map {{ height: 430px; border-radius: 14px; background: #e9e3d6; }}
    #prefecture-map.map-empty {{ display: grid; place-items: center; color: #75685c; font-weight: 850; }}
    .map-note {{ margin: 10px 0 0; color: #75685c; font-size: .8rem; }}
    .pokemon-grid {{ display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 8px; }}
    .pokemon-card {{
      display: grid; gap: 2px; padding: 12px; border: 1px solid rgba(93,67,35,.13);
      border-radius: 13px; background: white; color: inherit; text-decoration: none;
    }}
    .pokemon-card strong {{ color: #3d2b72; }}
    .pokemon-card span {{ color: #75685c; font-size: .75rem; font-weight: 750; }}
    .pokemon-more {{ grid-column: 1 / -1; }}
    .pokemon-more summary {{
      width: fit-content; margin: 12px auto 0; padding: 8px 14px;
      border-radius: 999px; background: #eee7fb; color: #57408f;
      cursor: pointer; font-size: .82rem; font-weight: 900;
    }}
    .pokemon-more-grid {{
      display: grid; grid-template-columns: repeat(3, minmax(0, 1fr));
      gap: 8px; margin-top: 12px;
    }}
    .manhole-grid {{ display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 10px; }}
    .manhole-card {{
      display: grid; grid-template-columns: 72px minmax(0,1fr); align-items: center;
      gap: 12px; min-height: 88px; padding: 8px; border: 1px solid rgba(93,67,35,.13);
      border-radius: 14px; background: white; color: inherit; text-decoration: none;
    }}
    .manhole-card img, .manhole-placeholder {{
      width: 72px; height: 72px; border-radius: 50%; object-fit: cover;
    }}
    .manhole-placeholder {{
      display: grid; place-items: center; background: #eee7fb; color: #7654aa; font-size: 2rem;
    }}
    .manhole-copy {{ min-width: 0; }}
    .manhole-copy strong, .manhole-copy small {{ display: block; }}
    .manhole-copy small {{ overflow: hidden; color: #75685c; text-overflow: ellipsis; white-space: nowrap; }}
    .trivia-card {{
      border-left: 5px solid #7e6ba9;
      background: linear-gradient(135deg, #fffaf0, #f4effd);
    }}
    .trivia-kicker {{
      display: inline-flex; margin: 0 0 6px; padding: 3px 9px;
      border-radius: 999px; background: #6b4aa2; color: white;
      font-size: .72rem; font-weight: 900;
    }}
    .trivia-card p {{ margin: 0; font-size: 1.05rem; font-weight: 750; }}
    .trivia-source {{ margin-top: 8px; font-size: .78rem; }}
    .empty-state {{ margin: 0; color: #75685c; }}
    .related-label {{ margin: 0 0 8px; color: #75685c; font-size: .8rem; font-weight: 850; }}
    .related-links {{ display: flex; flex-wrap: wrap; gap: 8px; }}
    .related-links a {{
      padding: 6px 10px; border-radius: 999px; background: #eee7fb;
      color: #57408f; font-size: .82rem; font-weight: 850; text-decoration: none;
    }}
    footer {{ margin-top: 24px; color: #75685c; font-size: .8rem; text-align: center; }}
    .leaflet-popup-content a {{ font-weight: 850; }}
    @media (max-width: 700px) {{
      .hero {{ display: block; padding: 22px 18px; }}
      .hero-summary {{ display: none; }}
      .pokemon-grid, .pokemon-more-grid, .manhole-grid {{ grid-template-columns: 1fr; }}
      #prefecture-map {{ height: 360px; }}
      section {{ padding: 16px; }}
    }}
  </style>
</head>
<body>
  <main class="page">
    <nav class="breadcrumb" aria-label="パンくず">
      <a href="/">全国マップ</a><span>›</span>
      <a href="/summary/">全国一覧</a><span>›</span>
      <span>{escape(prefecture)}</span>
    </nav>
    <header class="hero">
      <div class="hero-main">
        <p class="hero-kicker">都道府県別 ポケふたガイド</p>
        <h1>{escape(prefecture)}のポケふた</h1>
        <p>{escape(hero_intro)}</p>
        <div class="stats" aria-label="{escape(prefecture)}の集計">
          <div class="stat"><span>設置枚数</span><strong>{count}枚</strong></div>
          <div class="stat"><span>全国順位</span><strong>{escape(rank_label)}</strong></div>
        </div>
        <div class="hero-actions">
          <a class="button" href="#manhole-list">マンホール一覧を見る</a>
          <a class="button pokefuta" href="https://pokefuta.com/visits"
            data-track="prefecture_visit_cta_click" data-destination="pokefuta_visits">訪問記録を残す</a>
          <a class="button photo" href="https://pokefuta.com/"
            data-track="prefecture_photo_cta_click" data-destination="pokefuta_photos">写真を見る</a>
          <a class="button secondary" href="{escape(map_href)}"
            data-track="prefecture_map_click" data-destination="map">全国マップで見る</a>
        </div>
      </div>
      <div class="hero-summary" aria-label="{escape(prefecture)}のサマリー">
        <span>サマリー</span>
        <p>{escape(hero_summary)}</p>
      </div>
    </header>

    <section class="trivia-card" aria-labelledby="trivia-heading">
      <span class="trivia-kicker">まず知りたい</span>
      <h2 id="trivia-heading">{escape(prefecture)}のポケふたトリビア</h2>
      {trivia_html}
    </section>

    <section aria-labelledby="map-heading">
      <h2 id="map-heading">{escape(prefecture)}の設置マップ</h2>
      <div id="prefecture-map" class="{map_empty_class.strip()}"></div>
      <p class="map-note">マーカーを選ぶと、各ポケふたの詳細ページへ移動できます。</p>
    </section>

    <section id="manhole-list" aria-labelledby="manhole-heading">
      <h2 id="manhole-heading">{escape(prefecture)}のマンホール一覧</h2>
      <div class="manhole-grid">{manhole_html}</div>
    </section>

    <section aria-labelledby="pokemon-heading">
      <h2 id="pokemon-heading">{escape(prefecture)}で会えるポケモン</h2>
      <div class="pokemon-grid">{pokemon_html}</div>
    </section>

    <section aria-labelledby="related-heading">
      <h2 id="related-heading">近くの都道府県から探す</h2>
      {related_html}
    </section>
    <footer><a href="/summary/">全国のポケふた一覧へ戻る</a></footer>
  </main>
  <script async src="https://www.googletagmanager.com/gtag/js?id=G-K18NR4GZG2"></script>
  <script>
    window.dataLayer = window.dataLayer || [];
    function gtag() {{ dataLayer.push(arguments); }}
    gtag('js', new Date());
    gtag('config', 'G-K18NR4GZG2', {{
      'page_path': '/prefectures/' + {_json_for_script(slug)} + '/',
      site_type: 'map',
      page_type: 'prefecture',
      prefecture: {_json_for_script(slug)}
    }});
    document.addEventListener('click', function(event) {{
      const link = event.target.closest('[data-track]');
      if (!link) return;
      gtag('event', link.dataset.track, {{
        prefecture: {_json_for_script(slug)},
        prefecture_name: {_json_for_script(prefecture)},
        position: Number(link.dataset.position || 0),
        destination: link.dataset.destination || ''
      }});
    }});
  </script>
  <script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"
    integrity="sha256-20nQCchB9co0qIjJZRGuk2/Z9VM+kNiyxNV1lvTlZBo=" crossorigin=""></script>
  <script>
    const points = {_json_for_script(map_points)};
    const mapElement = document.getElementById('prefecture-map');
    if (!points.length) {{
      mapElement.textContent = '現在、表示できる設置地点はありません。';
    }} else {{
      const map = L.map(mapElement, {{ scrollWheelZoom: false }});
      L.tileLayer('https://{{s}}.tile.openstreetmap.org/{{z}}/{{x}}/{{y}}.png', {{
        maxZoom: 19,
        attribution: '&copy; OpenStreetMap contributors'
      }}).addTo(map);
      const bounds = [];
      points.forEach(function(point) {{
        const latlng = [point.lat, point.lng];
        bounds.push(latlng);
        const pokemon = point.pokemons.join('・') || 'ポケモン';
        const detailUrl = '/manholes/' + encodeURIComponent(point.id) + '/';
        L.marker(latlng).addTo(map).bindPopup(
          '<strong>' + escapeHtml(point.city || '所在地不明') + '</strong><br>' +
          escapeHtml(pokemon) + '<br><a href="' + detailUrl +
          '" data-track="prefecture_manhole_click" data-destination="' +
          escapeHtml(point.id) + '">詳細を見る</a>'
        );
      }});
      if (bounds.length === 1) map.setView(bounds[0], 13);
      else map.fitBounds(bounds, {{ padding: [28, 28], maxZoom: 13 }});
    }}
    function escapeHtml(value) {{
      return String(value).replace(/[&<>"']/g, function(char) {{
        return {{'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}}[char];
      }});
    }}
  </script>
</body>
</html>
"""


def generate_all(
    records: list[dict],
    pokemon_slugs: dict[str, str],
    trivia: dict[str, dict],
    output_dir: Path,
) -> int:
    records_by_pref = {pref: [] for pref in PREFECTURE_ORDER}
    for record in records:
        prefecture = record.get("prefecture", "")
        if prefecture in records_by_pref:
            records_by_pref[prefecture].append(record)
    rankings = build_rankings(records)
    for prefecture, slug in PREFECTURES:
        out_dir = output_dir / slug
        out_dir.mkdir(parents=True, exist_ok=True)
        html = build_page(
            prefecture,
            slug,
            records_by_pref[prefecture],
            rankings[prefecture],
            pokemon_slugs,
            trivia.get(prefecture),
        )
        (out_dir / "index.html").write_text(html, encoding="utf-8")
    return len(PREFECTURES)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--manholes", type=Path, default=DEFAULT_MANHOLES)
    parser.add_argument("--pokemon", type=Path, default=DEFAULT_POKEMON)
    parser.add_argument("--trivia", type=Path, default=DEFAULT_TRIVIA)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    records = load_records(args.manholes)
    pokemon_slugs = load_pokemon_slugs(args.pokemon)
    trivia = load_trivia(args.trivia)
    count = generate_all(records, pokemon_slugs, trivia, args.output)
    print(
        f"[generate_prefecture_pages] wrote {count} pages to "
        f"{args.output.relative_to(ROOT) if args.output.is_relative_to(ROOT) else args.output}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
