#!/usr/bin/env python3
"""/features/（特集）の一覧ページと特集ページを生成する。

- 特集は dataset/features/<slug>.json に1本1ファイルで手書きする（書式は features.py）
- 蓋のカード・地図・見た目は /trip/ と同じく都道府県ページの部品を使う
"""

from __future__ import annotations

import argparse
from pathlib import Path
from urllib.parse import quote
from xml.sax.saxutils import escape

try:
    from apps.scraper import generate_municipality_pages as muni_page
    from apps.scraper import generate_prefecture_pages as pref
    from apps.scraper.features import (
        DEFAULT_FEATURES_DIR, FEATURES_BASE, article_date, date_label, feature_path, load_features, safe_links,
    )
except ModuleNotFoundError as exc:
    if exc.name != "apps":
        raise
    import generate_municipality_pages as muni_page
    import generate_prefecture_pages as pref
    from features import (
        DEFAULT_FEATURES_DIR, FEATURES_BASE, article_date, date_label, feature_path, load_features, safe_links,
    )

ROOT = pref.ROOT
BASE_URL = pref.BASE_URL
DEFAULT_OUTPUT = ROOT / "dist" / "features"
IMAGE_DIR = muni_page.IMAGE_DIR

_escape_attr = pref._escape_attr
_json_for_script = pref._json_for_script

FEATURE_CSS = """
    .feature-notes { margin: 0; padding: 0; list-style: none; display: grid; gap: 10px; }
    .feature-notes li { padding: 12px 14px; border-radius: 14px; background: #fffaf0; border: 1px solid #ece4d7; }
    .feature-notes a { font-weight: 850; }
    .feature-notes .feature-pokemon { display: block; margin-top: 2px; color: #62564a; font-size: .85rem; }
    .feature-notes p { margin: 6px 0 0; }
    .feature-status { display: inline-block; margin-left: 6px; padding: 1px 8px; border-radius: 999px;
      background: #a85b2e; color: #fff; font-size: .72rem; font-weight: 700; vertical-align: 1px; }
    .feature-section p { margin: 0 0 10px; line-height: 1.8; }
    .feature-section p:last-child { margin-bottom: 0; }
    .feature-timeline { margin: 0; padding: 0; list-style: none; display: grid; gap: 8px; }
    .feature-timeline li { display: grid; grid-template-columns: minmax(0, 11em) minmax(0, 1fr); gap: 4px 12px; }
    .feature-timeline time, .feature-timeline .feature-when { color: #a85b2e; font-weight: 850; }
    @media (max-width: 560px) { .feature-timeline li { grid-template-columns: minmax(0, 1fr); } }
    .feature-news { margin: 0; padding: 0; list-style: none; display: grid; gap: 10px; }
    .feature-news a { font-weight: 800; }
    .feature-news small { display: block; margin-top: 2px; color: #75685c; font-size: .8rem; }
    .feature-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(min(100%, 260px), 1fr)); gap: 10px; }
    .feature-card { display: grid; align-content: start; gap: 4px; padding: 12px 14px; border-radius: 14px; background: #fffaf0;
      border: 1px solid #ece4d7; color: inherit; text-decoration: none; }
    .feature-card .feature-meta { color: #75685c; font-size: .75rem; }
    .feature-card .feature-title { font-weight: 850; }
    .feature-card small { color: #62564a; font-size: .82rem; }
"""


def _head(title: str, description: str, canonical: str, json_ld: dict, with_map: bool) -> str:
    head = muni_page._head(title, description, canonical, json_ld, with_map)
    return head.replace("  </style>", f"{FEATURE_CSS}  </style>", 1)


def _to_feature_events(html: str) -> str:
    """県ページの部品は prefecture_* のイベント名を直書きしているので、特集の名前に変える。"""
    return html.replace('data-track="prefecture_', 'data-track="feature_').replace(
        'data-legacy-track="prefecture_', 'data-legacy-track="feature_'
    )


def _format_date(value: str) -> str:
    year, month, day = value.split("-")
    return f"{int(year)}年{int(month)}月{int(day)}日"


def _status_html(record: dict) -> str:
    if record.get("installed") is not False:
        return ""
    note = str(record.get("installation_note") or "設置予定")
    return f'<span class="feature-status">{escape(note)}</span>'


def _notes_html(feature: dict) -> str:
    items = []
    for item, record in zip(feature["manholes"], feature["records"]):
        mid = str(record["id"])
        pokemons = "・".join(pref._clean_pokemons(record))
        note = f'<p>{escape(str(item["note"]))}</p>' if item.get("note") else ""
        items.append(
            f'<li><a href="/manholes/{quote(mid)}/" data-track="feature_manhole_click" '
            f'data-surface="feature_notes" data-destination="{_escape_attr(mid)}" '
            f'data-content-id="{_escape_attr(mid)}">{escape(pref._manhole_name(record))}</a>'
            f'{_status_html(record)}'
            f'<span class="feature-pokemon">{escape(pokemons)}</span>{note}</li>'
        )
    return f'<ol class="feature-notes">{"".join(items)}</ol>'


def _timeline_html(feature: dict) -> str:
    """お披露目・設置予定など（timeline）。見出しの直後に置く。"""
    items = "".join(
        "<li>"
        + (f'<time datetime="{_escape_attr(item["date"])}">{escape(item["when"])}</time>'
           if item.get("date") else f'<span class="feature-when">{escape(item["when"])}</span>')
        + f'<span>{escape(item["text"])}</span></li>'
        for item in feature.get("timeline", [])
    )
    if not items:
        return ""
    return (
        '\n    <section aria-labelledby="timeline-heading">'
        '\n      <h2 id="timeline-heading">お披露目と設置</h2>'
        f'\n      <ol class="feature-timeline">{items}</ol>'
        '\n    </section>\n'
    )


def _news_html(feature: dict) -> str:
    """公式発表・報道（news）。外部サイトなので別タブで開く。"""
    items = "".join(
        f'<li><a href="{_escape_attr(item["href"])}" target="_blank" rel="noopener noreferrer" '
        f'data-track="feature_news_click" data-surface="news" data-destination="{_escape_attr(item["source"])}">'
        f'{escape(item["title"])}</a>'
        f'<small>{escape(item["source"])}'
        + (f'・<time datetime="{_escape_attr(item["date"])}">{escape(_format_date(item["date"]))}</time>'
           if item.get("date") else "")
        + "</small></li>"
        for item in feature.get("news", [])
    )
    if not items:
        return ""
    return (
        '\n    <section aria-labelledby="news-heading">'
        '\n      <h2 id="news-heading">公式発表・ニュース</h2>'
        f'\n      <ul class="feature-news">{items}</ul>'
        '\n    </section>\n'
    )


def _sections_html(feature: dict) -> str:
    """手書きの読み物（sections）。本文は空行で段落に分ける。"""
    html = []
    for i, section in enumerate(feature.get("sections", []), start=1):
        paragraphs = "".join(
            f"<p>{escape(p.strip())}</p>" for p in section["body"].split("\n\n") if p.strip()
        )
        html.append(
            f'\n    <section class="feature-section" aria-labelledby="section-{i}-heading">'
            f'\n      <h2 id="section-{i}-heading">{escape(section["heading"])}</h2>'
            f'\n      {paragraphs}'
            f'\n    </section>\n'
        )
    return "".join(html)


def _analytics_script(page_path: str, page_type: str, feature_slug: str = "", prefecture_slug: str = "") -> str:
    context = {"page_path": page_path, "site_type": "map", "page_type": page_type}
    if prefecture_slug:
        context["prefecture"] = prefecture_slug
    defaults = {"event_category": "feature", "surface": f"{page_type}_page"}
    if feature_slug:
        defaults["content_group"] = feature_slug
    return f"""  <script src="/assets/analytics.js?v=20260929a"></script>
  <script>
    window.PokefutaAnalytics.init({_json_for_script(context)});
    const featureEventDefaults = {_json_for_script(defaults)};
    function trackFeatureEvent(name, params) {{
      window.PokefutaAnalytics.trackEvent(name, Object.assign({{}}, featureEventDefaults, params || {{}}));
    }}
    window.PokefutaAnalytics.bindClickTracking(featureEventDefaults, {{ detail: true }});
  </script>
"""


def build_feature_page(feature: dict, photos: dict[str, dict], others: list[dict]) -> str:
    records = feature["records"]
    path = feature_path(feature)
    canonical = f"{BASE_URL}{path}"
    prefecture = feature.get("prefecture") or ""
    pref_slug = pref.PREFECTURE_SLUGS.get(prefecture, "")
    title = f"{feature['title']}｜ポケふた特集"
    description = feature.get("description") or feature.get("lead") or feature["title"]
    lead = feature.get("lead") or ""
    kicker = feature.get("kicker") or "特集"
    mapped = [r for r in records if isinstance(r.get("lat"), (int, float)) and isinstance(r.get("lng"), (int, float))]
    map_points = [
        {
            "id": str(r["id"]),
            "lat": r["lat"],
            "lng": r["lng"],
            "name": pref._manhole_name(r),
            "pokemons": pref._clean_pokemons(r),
            "is_preinstall": r.get("installed") is False,
            "photo_url": pref._photo_asset_url(r, photos[str(r["id"])]) if str(r["id"]) in photos else "",
        }
        for r in mapped
    ]
    cards_html = _to_feature_events(pref._manhole_cards(records, photos, pref_slug, keep_order=True))
    links = "".join(
        f'<a class="inline-link" href="{_escape_attr(link["href"])}"'
        + (' target="_blank" rel="noopener noreferrer"' if link.get("external") else "")
        + f' data-track="feature_related_click" data-surface="related"'
        f' data-destination="{_escape_attr(link["href"])}">{escape(str(link["text"]))}</a>'
        for link in safe_links(feature)
    )
    other_links = "".join(
        f'<a class="inline-link" href="{_escape_attr(feature_path(other))}" data-track="feature_other_click" '
        f'data-surface="related" data-destination="{_escape_attr(other["slug"])}">{escape(other["title"])}</a>'
        for other in others[:4]
    )
    json_ld = {
        "@context": "https://schema.org",
        "@type": "Article",
        "headline": feature["title"],
        "description": description,
        **({"datePublished": article_date(feature)} if article_date(feature) else {}),
        "url": canonical,
        "mainEntity": {
            "@type": "ItemList",
            "numberOfItems": len(records),
            "itemListElement": [
                {
                    "@type": "ListItem",
                    "position": i,
                    "url": f"{BASE_URL}/manholes/{quote(str(r['id']))}/",
                    "name": f"{pref._manhole_name(r)}のポケふた",
                }
                for i, r in enumerate(records, start=1)
            ],
        },
    }
    map_html = (
        f"""
    <section aria-labelledby="map-heading">
      <h2 id="map-heading">地図で見る</h2>
      <div id="prefecture-map"></div>
    </section>
"""
        if map_points else ""
    )
    map_scripts = (
        """  <script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"
    integrity="sha256-20nQCchB9co0qIjJZRGuk2/Z9VM+kNiyxNV1lvTlZBo=" crossorigin=""></script>
"""
        + pref._map_script(map_points, pref._campaign_params(pref_slug), "feature", "trackFeatureEvent")
        if map_points else ""
    )
    return _head(title, description, canonical, json_ld, with_map=bool(map_points)) + f"""<body>
  <main class="page">
    <nav class="breadcrumb" aria-label="パンくず">
      <a href="/">全国マップ</a><span>›</span>
      <a href="{FEATURES_BASE}">特集</a><span>›</span>
      <span>{escape(feature['title'])}</span>
    </nav>
    <header class="hero">
      <div class="hero-main">
        <p class="hero-kicker">{escape(kicker)} <time datetime="{_escape_attr(feature['published'])}">{escape(_format_date(feature['published']))}{escape(date_label(feature))}</time></p>
        <h1>{escape(feature['title'])}</h1>
        {f'<p>{escape(lead)}</p>' if lead else ''}
        <div class="hero-actions">
          <a class="button primary" href="#manhole-list" data-track="feature_list_click"
            data-surface="hero" data-destination="manhole_list">ポケふたを見る</a>
          {'<a class="button tertiary" href="#prefecture-map" data-track="feature_map_click" data-surface="hero" data-destination="feature_map">地図で見る</a>' if map_points else ''}
        </div>
      </div>
    </header>
{_timeline_html(feature)}
    <section aria-labelledby="notes-heading">
      <h2 id="notes-heading">見どころ</h2>
      {_notes_html(feature)}
    </section>
{_sections_html(feature)}
    <section id="manhole-list" aria-labelledby="manhole-heading">
      <h2 id="manhole-heading">この特集のポケふた</h2>
      <div class="manhole-grid">{cards_html}</div>
    </section>
{map_html}{_news_html(feature)}
    <section aria-labelledby="related-heading">
      <h2 id="related-heading">あわせて見る</h2>
      <div class="municipality-actions">
        {links}
        {other_links}
        <a class="inline-link" href="{FEATURES_BASE}" data-track="feature_index_click"
          data-surface="related" data-destination="feature_index">特集の一覧</a>
      </div>
    </section>
    <footer><a href="{FEATURES_BASE}">特集の一覧へ戻る</a></footer>
  </main>
{_analytics_script(path, "feature", feature['slug'], pref_slug)}{map_scripts}</body>
</html>
"""


def build_index_page(features: list[dict]) -> str:
    title = "ポケふた特集｜新しいポケふたと、旅のテーマ"
    description = (
        "新しく設置・発表されたポケふた（ポケモンマンホール）や、テーマごとに集めたポケふたを"
        "特集としてまとめています。"
    )
    canonical = f"{BASE_URL}{FEATURES_BASE}"

    def card(feature: dict) -> str:
        records = feature["records"]
        meta = " / ".join(filter(None, [
            _format_date(feature["published"]) + ("" if date_label(feature) == "公開" else date_label(feature)),
            feature.get("prefecture"),
        ]))
        return (
            f'<a class="feature-card" href="{_escape_attr(feature_path(feature))}" data-track="feature_card_click" '
            f'data-surface="feature_index" data-destination="{_escape_attr(feature["slug"])}">'
            f'<span class="feature-meta">{escape(meta)}</span>'
            f'<span class="feature-title">{escape(feature["title"])}</span>'
            f'{muni_page.stop_thumbs_html(records, len(records), IMAGE_DIR)}'
            f'<small>ポケふた{len(records)}枚</small></a>'
        )

    json_ld = {
        "@context": "https://schema.org",
        "@type": "CollectionPage",
        "name": "ポケふた特集",
        "description": description,
        "url": canonical,
        "hasPart": [
            {"@type": "Article", "headline": f["title"], "url": f"{BASE_URL}{feature_path(f)}",
             **({"datePublished": article_date(f)} if article_date(f) else {})}
            for f in features
        ],
    }
    cards = "".join(card(f) for f in features) or '<p class="empty-state">特集はまだありません。</p>'
    return _head(title, description, canonical, json_ld, with_map=False) + f"""<body>
  <main class="page">
    <nav class="breadcrumb" aria-label="パンくず">
      <a href="/">全国マップ</a><span>›</span>
      <span>特集</span>
    </nav>
    <header class="hero">
      <div class="hero-main">
        <p class="hero-kicker">ポケふた特集</p>
        <h1>ポケふた特集</h1>
        <p>新しく置かれるポケふたや、テーマで集めたポケふたをまとめています。</p>
      </div>
    </header>
    <section aria-labelledby="feature-list-heading">
      <h2 id="feature-list-heading">特集の一覧</h2>
      <div class="feature-grid">{cards}</div>
    </section>
    <footer><a href="/summary/">ポケふたのまとめへ</a></footer>
  </main>
{_analytics_script(FEATURES_BASE, "feature_index")}</body>
</html>
"""


def generate_all(
    records: list[dict], photos: dict[str, dict], output_dir: Path, features_dir: Path = DEFAULT_FEATURES_DIR
) -> list[dict]:
    by_id = {str(r.get("id", "")): r for r in records if r.get("status", "active") == "active"}
    features = load_features(by_id, features_dir)
    for feature in features:
        out = output_dir / feature["slug"]
        out.mkdir(parents=True, exist_ok=True)
        others = [f for f in features if f["slug"] != feature["slug"]]
        (out / "index.html").write_text(build_feature_page(feature, photos, others), encoding="utf-8")
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "index.html").write_text(build_index_page(features), encoding="utf-8")
    return features


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--manholes", type=Path, default=pref.DEFAULT_MANHOLES)
    parser.add_argument("--photos", type=Path, default=pref.DEFAULT_PHOTOS)
    parser.add_argument("--features", type=Path, default=DEFAULT_FEATURES_DIR)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    features = generate_all(
        pref.load_records(args.manholes), pref.load_photos(args.photos), args.output, args.features
    )
    print(f"[generate_feature_pages] wrote {len(features)} feature pages + index to {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
