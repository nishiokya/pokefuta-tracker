#!/usr/bin/env python3
"""市区町村ページ（/municipalities/<県slug>/<市区町村slug>/）とランキング（/municipalities/）を生成する。

対象の決め方は municipalities.py（県の全数を1自治体が占める場合は県ページと同じ内容に
なるので作らない）。見た目・カード・写真・地図は都道府県ページの部品をそのまま使い、
市区町村ページにしかない中身は次の2つ:

- 直線距離で近い順に結んだ「巡る順番」と、その順で開く Google マップのルート
- 県内・全国の中での位置（「都内13枚のうち6枚」「市区町村別で全国2位」）
"""

from __future__ import annotations

import argparse
import itertools
import math
from datetime import datetime
from pathlib import Path
from urllib.parse import quote
from xml.sax.saxutils import escape

try:
    from apps.scraper import generate_prefecture_pages as pref
    from apps.scraper.municipalities import (
        MIN_MANHOLES,
        RANKING_MIN_MANHOLES,
        Municipality,
        build_municipalities,
        load_slugs,
        missing_slugs,
    )
except ModuleNotFoundError as exc:
    if exc.name != "apps":
        raise
    import generate_prefecture_pages as pref
    from municipalities import (
        MIN_MANHOLES,
        RANKING_MIN_MANHOLES,
        Municipality,
        build_municipalities,
        load_slugs,
        missing_slugs,
    )

ROOT = pref.ROOT
BASE_URL = pref.BASE_URL
DEFAULT_OUTPUT = ROOT / "dist" / "municipalities"
OG_IMAGE = pref.OG_IMAGE
JST = pref.JST
# 隣の地点までの直線距離がこれを超える区間があるときは、Google マップのルートを出さない。
# 小笠原村（父島と母島は約50km、船で渡る）のように、道路のルートが意味を持たないため。
ROUTE_LINK_MAX_LEG_KM = 15.0
# Google マップの経路 URL は経由地が9か所まで（出発地・目的地を含めて11地点）。
ROUTE_LINK_MAX_STOPS = 11

_escape_attr = pref._escape_attr
_json_for_script = pref._json_for_script


def _short_prefecture_name(prefecture: str) -> str:
    """「都内」「府内」「県内」「道内」の頭。"""
    if prefecture == "北海道":
        return "道内"
    return prefecture[-1] + "内"


def _to_municipality_events(html: str) -> str:
    """都道府県ページの部品が埋める data-track を市区町村ページのイベント名に変える。

    部品（カード・写真・ポケモン）は `prefecture_*` のイベント名を直書きしている。
    同じ名前のまま送ると、県ページの成果（写真投稿の開始など）に市区町村ページの分が混ざる。
    """
    return html.replace('data-track="prefecture_', 'data-track="municipality_').replace(
        'data-legacy-track="prefecture_', 'data-legacy-track="municipality_'
    )


def _visitable(records: list[dict]) -> list[dict]:
    return [
        record for record in records
        if record.get("installed") is not False
        and isinstance(record.get("lat"), (int, float))
        and isinstance(record.get("lng"), (int, float))
    ]


def shortest_route(records: list[dict]) -> list[dict]:
    """全地点を1回ずつ通る、直線距離の合計が最短の順番（出発地と終着地は自由）。

    対象は1自治体の数地点（多くて十数）なので、地点数が少なければ全順列、
    多ければ各地点から近い順にたどった中で最短のものを使う。
    """
    points = _visitable(records)
    if len(points) <= 2:
        return points

    def leg(a: dict, b: dict) -> float:
        return pref._distance_km(a["lat"], a["lng"], b["lat"], b["lng"])

    def total(order: list[dict]) -> float:
        return sum(leg(a, b) for a, b in zip(order, order[1:]))

    def tie_break(order: list[dict]) -> tuple[float, list[str]]:
        # 同じ長さの順路が複数あるとき（往路と復路）に、生成のたびに変わらないようにする
        return (round(total(order), 6), [str(r.get("id", "")) for r in order])

    if len(points) <= 8:
        return list(min(itertools.permutations(points), key=lambda o: tie_break(list(o))))

    candidates = []
    for start in points:
        order = [start]
        rest = [p for p in points if p is not start]
        while rest:
            nearest = min(rest, key=lambda p: (leg(order[-1], p), str(p.get("id", ""))))
            order.append(nearest)
            rest.remove(nearest)
        candidates.append(order)
    return min(candidates, key=tie_break)


def _google_route_url(route: list[dict]) -> str:
    if len(route) < 2 or len(route) > ROUTE_LINK_MAX_STOPS:
        return ""
    coords = [f'{r["lat"]},{r["lng"]}' for r in route]
    url = (
        "https://www.google.com/maps/dir/?api=1"
        f"&origin={quote(coords[0])}&destination={quote(coords[-1])}"
    )
    if len(coords) > 2:
        url += "&waypoints=" + quote("|".join(coords[1:-1]))
    return url


def _stop_name(record: dict, municipality_name: str) -> str:
    # 「京都市 円山公園」→「円山公園」。市区町村ページの中では自治体名が重複する。
    # 施設名の無い蓋（「町田市（ゼニガメ）」）は自治体名しか手がかりが無いので残す。
    name = pref._guide_stop_name(record)
    short = name.removeprefix(f"{municipality_name} ")
    return short if short != name else name


def _leg_label(km: float) -> str:
    # 同じ施設の中や隣どうしの蓋（町田の原町田6丁目など）は 0.0km と出てしまうので言い換える
    if km < 0.1:
        return "次はすぐ近く（直線100m未満）"
    if km < 1:
        return f"次まで直線約{round(km * 1000, -1):.0f}m"
    return f"次まで直線約{km:.1f}km"


def _route_section(municipality: Municipality) -> str:
    route = shortest_route(municipality.records)
    if len(route) < 2:
        return ""
    legs = [
        pref._distance_km(a["lat"], a["lng"], b["lat"], b["lng"])
        for a, b in zip(route, route[1:])
    ]
    total_km = sum(legs)
    longest = max(legs)
    items = []
    for index, record in enumerate(route):
        mid = str(record.get("id", ""))
        leg_html = (
            f'<span class="route-leg">{_leg_label(legs[index])}</span>'
            if index < len(legs) else ""
        )
        items.append(
            f'<li><a href="#manhole-{_escape_attr(mid)}" data-track="municipality_route_stop_click" '
            f'data-surface="route" data-destination="manhole_list" data-position="{index + 1}" '
            f'data-content-id="{_escape_attr(mid)}">{escape(_stop_name(record, municipality.name))}</a>'
            f'<span>{escape(str(record.get("address") or ""))}</span>{leg_html}</li>'
        )
    name = municipality.name
    lead = (
        f"{name}の{len(route)}地点を、直線距離の合計がいちばん短くなる順に並べました。"
        + (
            f"この順にたどっても直線で合計約{round(total_km * 1000, -1):.0f}mと、近くにまとまっています。"
            if total_km < 1 else f"この順にたどると、直線で合計約{total_km:.1f}kmです。"
        )
    )
    if longest > ROUTE_LINK_MAX_LEG_KM:
        far_index = legs.index(longest)
        lead += (
            f"{_stop_name(route[far_index], name)}と{_stop_name(route[far_index + 1], name)}の間は"
            f"直線で約{longest:.0f}km離れているので、1日で回れるとは限りません。"
        )
    route_url = _google_route_url(route) if longest <= ROUTE_LINK_MAX_LEG_KM else ""
    route_link = (
        f'<a class="inline-link" href="{_escape_attr(route_url)}" target="_blank" '
        'rel="noopener noreferrer" data-track="municipality_route_open" data-surface="route" '
        'data-destination="google_maps_route">この順番でGoogleマップを開く</a>'
        if route_url else ""
    )
    return (
        '<section id="route" class="visit-guide" aria-labelledby="route-heading">'
        f'<h2 id="route-heading">{escape(name)}のポケふたを巡る順番</h2>'
        f'<p>{escape(lead)}</p>'
        f'<ol class="route-stops">{"".join(items)}</ol>'
        '<div class="municipality-actions">'
        f'{route_link}'
        '<a class="inline-link" href="#prefecture-map" data-track="municipality_map_click" '
        'data-surface="route" data-destination="municipality_map">地図で見る</a></div>'
        '<p class="route-note">直線距離で結んだ目安です。実際の道のり・所要時間・交通手段は'
        '地図アプリや公式情報で確認してください。</p>'
        '</section>'
    )


def _rank_label(municipality: Municipality) -> str:
    label = f"全国{municipality.national_rank}位"
    if municipality.national_tied > 1:
        label += f"（{municipality.national_tied}自治体が同数）"
    return label


def _hero_intro(municipality: Municipality) -> str:
    m = municipality
    return (
        f"{m.prefecture}{m.name}には{m.count}枚のポケふたがあります。"
        f"{_short_prefecture_name(m.prefecture)}{m.prefecture_total}枚のうち{m.count}枚がここに集まり、"
        f"市区町村別では{_rank_label(m)}の設置数です。"
    )


def _pokemon_summary(records: list[dict]) -> list[str]:
    return list(dict.fromkeys(
        name for record in records for name in pref._clean_pokemons(record)
    ))


def _seo(municipality: Municipality) -> tuple[str, str, str]:
    m = municipality
    pokemons = _pokemon_summary(m.records)
    pokemon_text = (
        "・".join(pokemons[:3]) + ("など" if len(pokemons) > 3 else "") + "の"
        if pokemons else ""
    )
    title = f"{m.name}のポケふた{m.count}枚はどこ？場所一覧・地図・巡る順番"
    description = (
        f"{m.prefecture}{m.name}にあるポケふた{m.count}枚を一覧と地図で紹介。"
        f"{pokemon_text}設置場所と住所、現地写真、近い順に巡る順番を確認できます。"
    )
    h1 = f"{m.name}（{m.prefecture}）のポケふた{m.count}枚"
    return title, description, h1


def _related_html(municipality: Municipality, others: list[Municipality]) -> str:
    m = municipality
    pref_slug = m.prefecture_slug
    same_pref = [o for o in others if o.prefecture == m.prefecture and o.path and o is not m]
    links = "".join(
        f'<a href="{_escape_attr(o.path)}" data-track="municipality_related_click" '
        f'data-surface="related" data-destination="{_escape_attr(o.slug)}">'
        f'{escape(o.name)} {o.count}枚</a>'
        for o in same_pref
    )
    same_pref_html = (
        f'<p class="related-label">{escape(m.prefecture)}のほかの市区町村</p>'
        f'<div class="related-links">{links}</div>'
        if links else ""
    )
    return (
        '<section aria-labelledby="related-heading">'
        f'<h2 id="related-heading">{escape(m.prefecture)}・全国から探す</h2>'
        f'{same_pref_html}'
        '<div class="municipality-actions">'
        f'<a class="inline-link" href="/prefectures/{quote(pref_slug)}/" '
        'data-track="municipality_prefecture_click" data-surface="related" '
        f'data-destination="{_escape_attr(pref_slug)}">{escape(m.prefecture)}のポケふた'
        f'{m.prefecture_total}枚を見る</a>'
        '<a class="inline-link" href="/municipalities/" data-track="municipality_ranking_click" '
        'data-surface="related" data-destination="ranking">ポケふたが多い市区町村ランキング</a>'
        '</div></section>'
    )


EXTRA_CSS = """
    .route-stops { margin: 12px 0 0; padding-left: 1.6em; display: grid; gap: 8px; }
    .route-stops li { padding: 8px 10px; border-radius: 12px; background: #fffaf0; }
    .route-stops li a { font-weight: 850; }
    .route-stops li span { display: block; color: #62564a; font-size: .82rem; }
    .route-stops li .route-leg { color: #6b4aa2; font-weight: 800; }
    .route-note { margin: 10px 0 0; color: #75685c; font-size: .78rem; }
    .stats { grid-template-columns: repeat(3, minmax(0, 1fr)); }
    .stat small { display: block; color: #75685c; font-size: .72rem; font-weight: 800; }
    .ranking-table { width: 100%; border-collapse: collapse; font-size: .92rem; }
    .ranking-table th, .ranking-table td { padding: 8px 6px; border-bottom: 1px solid #ece4d7; text-align: left; }
    .ranking-table th { color: #75685c; font-size: .78rem; }
    .ranking-table td.num { text-align: right; font-weight: 850; white-space: nowrap; }
    @media (max-width: 700px) {
      .stat { padding: 10px; }
      .stat strong { font-size: 1.15rem; }
    }
    .ranking-table td small { display: block; color: #75685c; font-size: .75rem; }
"""


def _head(title: str, description: str, canonical: str, json_ld: dict, with_map: bool) -> str:
    leaflet_css = (
        '  <link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css"\n'
        '    integrity="sha256-p4NxAoJBhIIN+hmNHrzRCf9tD/miZyoHS5obTRR9BMY=" crossorigin="">\n'
        if with_map else ""
    )
    return f"""<!doctype html>
<html lang="ja">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{escape(title)}</title>
  <meta name="description" content="{_escape_attr(description)}">
  <meta name="robots" content="index,follow">
  <meta property="og:type" content="website">
  <meta property="og:locale" content="ja_JP">
  <meta property="og:title" content="{_escape_attr(title)}">
  <meta property="og:description" content="{_escape_attr(description)}">
  <meta property="og:url" content="{_escape_attr(canonical)}">
  <meta property="og:image" content="{OG_IMAGE}">
  <meta name="twitter:card" content="summary_large_image">
  <meta name="twitter:title" content="{_escape_attr(title)}">
  <meta name="twitter:description" content="{_escape_attr(description)}">
  <meta name="twitter:image" content="{OG_IMAGE}">
  <link rel="canonical" href="{_escape_attr(canonical)}">
  <link rel="icon" href="/assets/pokefuta-marker.svg" type="image/svg+xml">
{leaflet_css}  <script type="application/ld+json">{_json_for_script(json_ld)}</script>
  <style>
{pref.PAGE_CSS}{EXTRA_CSS}  </style>
</head>
"""


def _analytics_script(page_path: str, page_type: str, prefecture_slug: str, municipality_slug: str) -> str:
    context = {
        "page_path": page_path,
        "site_type": "map",
        "page_type": page_type,
    }
    if prefecture_slug:
        context["prefecture"] = prefecture_slug
    defaults = {"event_category": "municipality_growth", "surface": f"{page_type}_page"}
    if municipality_slug:
        defaults["municipality"] = municipality_slug
    return f"""  <script src="/assets/analytics.js?v=20260929a"></script>
  <script>
    window.PokefutaAnalytics.init({_json_for_script(context)});
    const municipalityEventDefaults = {_json_for_script(defaults)};
    function trackMunicipalityEvent(name, params) {{
      window.PokefutaAnalytics.trackEvent(name, Object.assign({{}}, municipalityEventDefaults, params || {{}}));
    }}
    window.PokefutaAnalytics.bindClickTracking(municipalityEventDefaults, {{ detail: true }});
  </script>
"""


def build_page(
    municipality: Municipality,
    all_municipalities: list[Municipality],
    pokemon_slugs: dict[str, str],
    photos: dict[str, dict],
) -> str:
    m = municipality
    pref_slug = m.prefecture_slug
    canonical = f"{BASE_URL}{m.path}"
    title, description, h1 = _seo(m)
    records = m.records
    pokemons = _pokemon_summary(records)

    map_points = [
        {
            "id": str(record.get("id", "")),
            "lat": record.get("lat"),
            "lng": record.get("lng"),
            "name": pref._manhole_name(record),
            "pokemons": pref._clean_pokemons(record),
            "is_preinstall": record.get("installed") is False,
            "photo_url": (
                pref._photo_asset_url(record, photos.get(str(record.get("id", "")), {}))
                if record.get("installed") is not False
                and str(record.get("id", "")) in photos
                else ""
            ),
        }
        for record in records
        if isinstance(record.get("lat"), (int, float))
        and isinstance(record.get("lng"), (int, float))
    ]

    photo_html = _to_municipality_events(pref._photo_section(m.name, pref_slug, records, photos))
    manhole_html = _to_municipality_events(pref._manhole_cards(records, photos, pref_slug))
    pokemon_html = _to_municipality_events(pref._pokemon_cards(records, pokemon_slugs))
    route_html = _route_section(m)
    related_html = _related_html(m, all_municipalities)
    hero_summary = (
        f"{'・'.join(pokemons[:6])}{'など' if len(pokemons) > 6 else ''}、"
        f"{len(pokemons)}種類のポケモンに会えます。"
        if pokemons else f"{m.name}のポケふた{m.count}枚の場所をまとめています。"
    )

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
                {"@type": "ListItem", "position": 3, "name": m.prefecture,
                 "item": f"{BASE_URL}/prefectures/{pref_slug}/"},
                {"@type": "ListItem", "position": 4, "name": m.name, "item": canonical},
            ],
        },
        "mainEntity": {
            "@type": "ItemList",
            "numberOfItems": m.count,
            "itemListElement": [
                {
                    "@type": "ListItem",
                    "position": index,
                    "name": f"{pref._manhole_name(record)}のポケふた",
                    "url": f"{BASE_URL}/manholes/{quote(str(record.get('id', '')))}/",
                }
                for index, record in enumerate(
                    sorted(records, key=lambda r: (r.get("city", ""), str(r.get("id", "")))), start=1
                )
            ],
        },
    }

    route_button = (
        '<a class="button secondary" href="#route" data-track="municipality_route_click" '
        'data-surface="hero" data-destination="route">巡る順番を見る</a>'
        if route_html else ""
    )
    return _head(title, description, canonical, json_ld, with_map=True) + f"""<body>
  <main class="page">
    <nav class="breadcrumb" aria-label="パンくず">
      <a href="/">全国マップ</a><span>›</span>
      <a href="/summary/">全国一覧</a><span>›</span>
      <a href="/prefectures/{quote(pref_slug)}/">{escape(m.prefecture)}</a><span>›</span>
      <span>{escape(m.name)}</span>
    </nav>
    <header class="hero">
      <div class="hero-main">
        <p class="hero-kicker">市区町村別 ポケふたガイド</p>
        <h1>{escape(h1)}</h1>
        <p>{escape(_hero_intro(m))}</p>
        <div class="stats" aria-label="{_escape_attr(m.name)}の集計">
          <div class="stat"><span>設置枚数</span><strong>{m.count}枚</strong></div>
          <div class="stat"><span>市区町村別</span><strong>全国{m.national_rank}位</strong>{
            f'<small>{m.national_tied}自治体が同数</small>' if m.national_tied > 1 else ''}</div>
          <div class="stat"><span>{escape(m.prefecture)}内</span><strong>{m.count}/{m.prefecture_total}枚</strong></div>
        </div>
        <div class="hero-actions">
          <a class="button primary" href="#manhole-list" data-track="municipality_list_click"
            data-surface="hero" data-destination="manhole_list">場所一覧を見る</a>
          {route_button}
          <a class="button tertiary" href="#prefecture-map" data-track="municipality_map_click"
            data-surface="hero" data-destination="municipality_map">地図で探す</a>
        </div>
      </div>
      <div class="hero-summary" aria-label="{_escape_attr(m.name)}のサマリー">
        <span>会えるポケモン</span>
        <p>{escape(hero_summary)}</p>
      </div>
    </header>

    {route_html}

    <section aria-labelledby="map-heading">
      <div class="section-heading-row">
        <h2 id="map-heading">{escape(m.name)}のポケふたマップ</h2>
        <p>ピンから詳細・行き方へ。設置済みのポケふたは写真投稿にも進めます。</p>
      </div>
      <div class="map-toolbar">
        <div class="map-legend" aria-label="地図の凡例">
          <span><i class="legend-dot has-photo"></i>投稿写真あり</span>
          <span><i class="legend-dot needs-photo"></i>写真募集中</span>
          <span><i class="legend-dot preinstall"></i>設置予定</span>
        </div>
      </div>
      <div id="prefecture-map"></div>
      <p class="map-note">地図はドラッグとピンチ操作に対応。スクロール中の誤操作を防ぐため、マウスホイール拡大は無効です。</p>
    </section>

    <section id="manhole-list" aria-labelledby="manhole-heading">
      <div class="section-heading-row">
        <h2 id="manhole-heading">{escape(m.name)}のポケふた一覧</h2>
        <p>写真から詳細へ。訪れたポケふたは写真で記録できます。</p>
      </div>
      <div class="manhole-grid">{manhole_html}</div>
    </section>

    <section id="prefecture-photos" aria-labelledby="photo-heading">
      <div class="section-heading-row">
        <h2 id="photo-heading">{escape(m.name)}のポケふた写真</h2>
        <p>写真館に投稿された現地写真です。クリックするとマンホール詳細を確認できます。</p>
      </div>
      {photo_html}
    </section>

    <section aria-labelledby="pokemon-heading">
      <h2 id="pokemon-heading">{escape(m.name)}で会えるポケモン</h2>
      <div class="pokemon-grid">{pokemon_html}</div>
    </section>

    {related_html}
    <footer><a href="/prefectures/{quote(pref_slug)}/">{escape(m.prefecture)}のポケふたへ戻る</a></footer>
  </main>
{_analytics_script(m.path, "municipality", pref_slug, m.slug or "")}  <script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"
    integrity="sha256-20nQCchB9co0qIjJZRGuk2/Z9VM+kNiyxNV1lvTlZBo=" crossorigin=""></script>
{pref._map_script(map_points, pref._campaign_params(pref_slug), "municipality", "trackMunicipalityEvent")}
</body>
</html>
"""


def build_ranking_page(municipalities: list[Municipality], total_manholes: int, today: str) -> str:
    listed = [m for m in municipalities if m.count >= RANKING_MIN_MANHOLES]
    singles = sum(1 for m in municipalities if m.count < RANKING_MIN_MANHOLES)
    canonical = f"{BASE_URL}/municipalities/"
    top = listed[0] if listed else None
    title = "ポケふたが多い市区町村ランキング｜自治体別の設置枚数"
    description = (
        f"全国{total_manholes}枚のポケふたを市区町村別に集計。"
        + (f"最多は{top.prefecture}{top.name}の{top.count}枚。" if top else "")
        + f"{RANKING_MIN_MANHOLES}枚以上ある{len(listed)}自治体を多い順に、設置場所の一覧・地図へのリンクつきで紹介します。"
    )

    rows = []
    for m in listed:
        if m.path:
            target = m.path
            note = ""
            track_destination = m.slug or ""
        else:
            target = f"/prefectures/{quote(m.prefecture_slug)}/"
            note = (
                f"{_short_prefecture_name(m.prefecture)}のポケふたはすべて{m.name}にあります"
                if m.covers_prefecture else f"{m.prefecture}のページで見る"
            )
            track_destination = m.prefecture_slug
        note_html = f"<small>{escape(note)}</small>" if note else ""
        rows.append(
            "<tr>"
            f'<td class="num">{m.national_rank}位</td>'
            f'<td><a href="{_escape_attr(target)}" data-track="municipality_ranking_row_click" '
            f'data-surface="ranking_table" data-destination="{_escape_attr(track_destination)}">'
            f'{escape(m.name)}</a>{note_html}</td>'
            f"<td>{escape(m.prefecture)}</td>"
            f'<td class="num">{m.count}枚</td>'
            "</tr>"
        )
    lead = (
        f"全国{total_manholes}枚のポケふたは{len(municipalities)}の市区町村に設置されています。"
        f"{RANKING_MIN_MANHOLES}枚以上ある{len(listed)}自治体を多い順に並べました。"
        f"ほかの{singles}自治体には1枚ずつあります。"
    )
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
                {"@type": "ListItem", "position": 3, "name": "市区町村ランキング", "item": canonical},
            ],
        },
    }
    return _head(title, description, canonical, json_ld, with_map=False) + f"""<body>
  <main class="page">
    <nav class="breadcrumb" aria-label="パンくず">
      <a href="/">全国マップ</a><span>›</span>
      <a href="/summary/">全国一覧</a><span>›</span>
      <span>市区町村ランキング</span>
    </nav>
    <header class="hero">
      <div class="hero-main">
        <p class="hero-kicker">市区町村別 ポケふたガイド</p>
        <h1>ポケふたが多い市区町村ランキング</h1>
        <p>{escape(lead)}</p>
        <p class="hero-note">{escape(today)}時点の設置データから毎日作り直しています。</p>
      </div>
    </header>

    <section aria-labelledby="ranking-heading">
      <h2 id="ranking-heading">{RANKING_MIN_MANHOLES}枚以上ある市区町村</h2>
      <table class="ranking-table">
        <thead><tr><th>順位</th><th>市区町村</th><th>都道府県</th><th>枚数</th></tr></thead>
        <tbody>{"".join(rows)}</tbody>
      </table>
    </section>

    <section aria-labelledby="pref-heading">
      <h2 id="pref-heading">都道府県から探す</h2>
      <div class="municipality-actions">
        <a class="inline-link" href="/prefectures/" data-track="municipality_prefecture_click"
          data-surface="related" data-destination="prefectures">都道府県別のポケふた一覧</a>
        <a class="inline-link" href="/summary/" data-track="municipality_summary_click"
          data-surface="related" data-destination="summary">全国のポケふた一覧</a>
      </div>
    </section>
    <footer><a href="/summary/">全国のポケふた一覧へ戻る</a></footer>
  </main>
{_analytics_script("/municipalities/", "municipality_ranking", "", "")}</body>
</html>
"""


def generate_all(
    records: list[dict],
    slugs: dict[str, str],
    pokemon_slugs: dict[str, str],
    photos: dict[str, dict],
    output_dir: Path,
    today: str | None = None,
) -> list[Municipality]:
    municipalities = build_municipalities(records, slugs)
    pages = [m for m in municipalities if m.path]
    for m in pages:
        out_dir = output_dir / m.prefecture_slug / m.slug
        out_dir.mkdir(parents=True, exist_ok=True)
        (out_dir / "index.html").write_text(
            build_page(m, municipalities, pokemon_slugs, photos), encoding="utf-8"
        )
    output_dir.mkdir(parents=True, exist_ok=True)
    active_total = sum(m.count for m in municipalities)
    today = today or datetime.now(JST).strftime("%Y年%-m月%-d日")
    (output_dir / "index.html").write_text(
        build_ranking_page(municipalities, active_total, today), encoding="utf-8"
    )
    return pages


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--manholes", type=Path, default=pref.DEFAULT_MANHOLES)
    parser.add_argument("--pokemon", type=Path, default=pref.DEFAULT_POKEMON)
    parser.add_argument("--photos", type=Path, default=pref.DEFAULT_PHOTOS)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    records = pref.load_records(args.manholes)
    slugs = load_slugs()
    missing = missing_slugs(build_municipalities(records, slugs))
    if missing:
        # 新しく条件を満たした自治体。ページは作らないがデプロイは止めない（日次の自動更新で起きうる）。
        # dataset/municipality_slugs.json に足せば次のデプロイで出る。
        print(f"[generate_municipality_pages] WARNING: slug が無いので作らない: {', '.join(missing)}")
    pages = generate_all(
        records, slugs, pref.load_pokemon_slugs(args.pokemon), pref.load_photos(args.photos), args.output
    )
    print(
        f"[generate_municipality_pages] wrote {len(pages)} pages (>= {MIN_MANHOLES}枚) + ranking to "
        f"{args.output.relative_to(ROOT) if args.output.is_relative_to(ROOT) else args.output}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
