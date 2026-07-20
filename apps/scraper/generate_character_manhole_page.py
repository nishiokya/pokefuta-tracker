#!/usr/bin/env python3
"""Generate /character_manholes.html — the SEO landing page for character manholes.

`gmanhole_map.html` is a full-screen Leaflet map with no crawlable body text and
no explanation of what a "character manhole" even is. This script bakes the
work/prefecture breakdown (from docs/character_manholes.ndjson +
docs/gmanhole.ndjson) and a design-manhole submission CTA into a static page at
build time, so first-time visitors land on something readable before the map,
and crawlers see real content instead of an empty <div id="map">.

Follows the same conventions as generate_pokemon_index_page.py /
generate_prefecture_pages.py: read ndjson, fill a string template, write to
--output. Counts are always aggregated from the datasets at generation time —
never hardcoded in the HTML.
"""

from __future__ import annotations

import argparse
import json
import logging
from collections import Counter, defaultdict
from pathlib import Path
from urllib.parse import quote
from xml.sax.saxutils import escape

try:
    from apps.scraper.photo_caption import (
        CAPTION_ELLIPSIS_CSS,
        caption_meta,
        format_display_name,
        format_photo_date,
        poster_profile_url,
    )
except ModuleNotFoundError as exc:
    if exc.name != "apps":
        raise
    from photo_caption import (
        CAPTION_ELLIPSIS_CSS,
        caption_meta,
        format_display_name,
        format_photo_date,
        poster_profile_url,
    )

try:
    from apps.scraper.prefectures import PREFECTURE_ORDER
except ModuleNotFoundError as exc:
    if exc.name != "apps":
        raise
    from prefectures import PREFECTURE_ORDER

logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger(__name__)

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CHARACTER_MANHOLES = ROOT / "docs" / "character_manholes.ndjson"
DEFAULT_GUNDAM = ROOT / "docs" / "gmanhole.ndjson"
DEFAULT_DESIGN_MANHOLES = ROOT / "docs" / "design_manholes.ndjson"
DEFAULT_OUTPUT = ROOT / "dist" / "character_manholes.html"

BASE_URL = "https://data.pokefuta.com/"
CANONICAL_URL = f"{BASE_URL}character_manholes.html"
MAP_URL = f"{BASE_URL}gmanhole_map.html"          # JSON-LD / OGP など絶対URLが必要な箇所専用
DESIGN_MANHOLE_URL = f"{BASE_URL}design_manhole.html"  # 同上
MAP_HREF = "./gmanhole_map.html"                  # ページ内ナビは他ページ同様に相対パス
DESIGN_MANHOLE_HREF = "./design_manhole.html"      # 同上（ローカル配信でも同一オリジンに留まる）
OG_IMAGE = f"{BASE_URL}assets/ogp/pokefuta_map_ogp.png"

# 明示的に撤去・未設置と分かっているものだけ除外する。installation_status が
# None（=未記録）のレコードは許容する（プラン参照: キャラ蓋115件中100件はNone）。
REMOVED_INSTALLATION_STATUSES = {"removed", "not_installed", "uninstalled", "scheduled_removal"}

# ガンダムマンホールは character_manholes.ndjson の "work" を持たない独立データセット
# なので、作品カードには合成エントリとして差し込む。
GUNDAM_WORK_NAME = "機動戦士ガンダム（ガンダムマンホール）"
GUNDAM_WORK_QUERY = "gundam"  # gmanhole_map.html の ?work= に渡す値（chk-gundam を選択する特別値）
GUNDAM_MARKER_COLOR = "#0044aa"
GUNDAM_MARKER_LABEL = "G"

LATEST_POSTS_LIMIT = 4

FAQ_ITEMS: list[tuple[str, str]] = [
    (
        "ポケふたとの違いは何ですか？",
        "ポケふたはポケモン公式の全国シリーズで、市区町村と経済産業省の連携で設置されています。"
        "一方でキャラクターマンホールは、ガンダムやゾンビランドサガなど作品ごと・自治体ごとに"
        "独自に設置されているマンホールです。このマップでは両方をまとめて探せます。",
    ),
    (
        "地図に載っていないマンホールがあるのですが？",
        "このマップに載っているのは確認できている設置情報のみです。載っていないキャラクターマンホールや"
        "ご当地デザインのマンホールを見つけたら、ぜひ写真を投稿してみんなの地図に追加してください。",
    ),
    (
        "写真は載せられますか？",
        "はい。無料アカウントでログインし、位置情報（GPS）付きの写真を投稿すると、"
        "みんなのデザインマンホールの一覧と地図に掲載されます。",
    ),
]


def _is_active(record: dict) -> bool:
    """status=='active' かつ、明示的な撤去・未設置でないもの。"""
    if record.get("status") != "active":
        return False
    installation_status = record.get("installation_status")
    if installation_status is None:
        return True
    return str(installation_status).strip().lower() not in REMOVED_INSTALLATION_STATUSES


def load_ndjson(path: Path) -> list[dict]:
    if not path.exists():
        logger.warning(f"Dataset not found: {path}")
        return []
    records: list[dict] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            record = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(record, dict):
            records.append(record)
    return records


def load_active_manholes(path: Path) -> list[dict]:
    return [record for record in load_ndjson(path) if _is_active(record)]


def build_work_summaries(character_records: list[dict], gundam_records: list[dict]) -> list[dict]:
    """作品別の件数降順サマリ（キャラ蓋の work ごと + ガンダムを1エントリとして合成）。"""
    groups: dict[str, list[dict]] = defaultdict(list)
    for record in character_records:
        work = str(record.get("work") or "").strip()
        if not work:
            continue
        groups[work].append(record)

    summaries: list[dict] = []
    for work, records in groups.items():
        prefectures = sorted(
            {record.get("prefecture") for record in records if record.get("prefecture")},
            key=lambda pref: PREFECTURE_ORDER.index(pref) if pref in PREFECTURE_ORDER else 999,
        )
        color = next((record.get("marker_color") for record in records if record.get("marker_color")), "")
        label = next((record.get("marker_label") for record in records if record.get("marker_label")), work[:1])
        summaries.append({
            "work": work,
            "count": len(records),
            "prefectures": prefectures,
            "color": color or "#6C5CA6",
            "label": label,
            "query": work,
        })

    if gundam_records:
        prefectures = sorted(
            {record.get("prefecture") for record in gundam_records if record.get("prefecture")},
            key=lambda pref: PREFECTURE_ORDER.index(pref) if pref in PREFECTURE_ORDER else 999,
        )
        summaries.append({
            "work": GUNDAM_WORK_NAME,
            "count": len(gundam_records),
            "prefectures": prefectures,
            "color": GUNDAM_MARKER_COLOR,
            "label": GUNDAM_MARKER_LABEL,
            "query": GUNDAM_WORK_QUERY,
        })

    return sorted(summaries, key=lambda summary: (-summary["count"], summary["work"]))


def build_prefecture_summaries(character_records: list[dict], gundam_records: list[dict]) -> list[dict]:
    """都道府県別の件数降順サマリ（キャラ蓋＋ガンダム蓋の合算）。"""
    counts: Counter[str] = Counter()
    for record in (*character_records, *gundam_records):
        prefecture = record.get("prefecture")
        if prefecture:
            counts[prefecture] += 1
    order_index = {name: index for index, name in enumerate(PREFECTURE_ORDER)}
    return sorted(
        ({"prefecture": prefecture, "count": count} for prefecture, count in counts.items()),
        key=lambda entry: (-entry["count"], order_index.get(entry["prefecture"], 999)),
    )


def build_latest_posts(path: Path, limit: int = LATEST_POSTS_LIMIT) -> list[dict]:
    """design_manholes.ndjson から、写真付きの最新投稿を最大 limit 件。"""
    records = [
        record for record in load_ndjson(path)
        if record.get("status") == "active" and str(record.get("photo_url") or "").strip()
    ]
    records.sort(key=lambda record: str(record.get("created_at", "")), reverse=True)

    posts: list[dict] = []
    for record in records[:limit]:
        location = "".join(
            part for part in (record.get("prefecture", ""), record.get("city", "")) if part
        )
        poster_name = format_display_name(record.get("display_name"))
        posts.append({
            "title": str(record.get("title") or "デザインマンホール").strip(),
            "photo_url": str(record.get("photo_url", "")),
            "location": location,
            "source_url": str(record.get("source_url", "")),
            "date": format_photo_date(record.get("created_at")),
            "poster": poster_name,
            "poster_profile_url": poster_profile_url(record.get("public_user_id")),
        })
    return posts


PAGE_STYLE = """
    /* ===== キャラクターマンホールLP（design_manhole.html を手本に top-page.css のトークンを使用） ===== */
    body.character-manhole-lp {
      margin: 0;
      padding: 0;
      background: var(--top-bg);
      font-family: 'Noto Sans JP', system-ui, -apple-system, sans-serif;
      color: var(--top-text);
      -webkit-font-smoothing: antialiased;
      line-height: 1.7;
    }
    .lp-wrap { max-width: 760px; margin: 0 auto; padding: 0 var(--top-pad); }

    /* ── Hero ── */
    .lp-hero { padding: 40px 0 28px; text-align: center; }
    .lp-eyebrow {
      display: inline-block;
      font-family: 'IBM Plex Mono', 'Courier New', monospace;
      font-size: 11px; letter-spacing: 0.22em; font-weight: 600;
      color: var(--top-eyebrow); margin: 0 0 14px;
    }
    .lp-hero h1 {
      margin: 0 0 14px; font-size: clamp(24px, 6vw, 34px);
      font-weight: 900; letter-spacing: -0.01em; line-height: 1.4;
      color: var(--top-purple-dark);
    }
    .lp-hero .lp-lead { margin: 0 auto 22px; max-width: 36em; font-size: 15px; color: var(--top-text-muted); }
    .lp-lead b { color: var(--top-text); }

    .lp-stats-row { display: flex; justify-content: center; gap: 10px; margin: 0 0 24px; flex-wrap: wrap; }
    .lp-stat {
      display: flex; flex-direction: column; align-items: center; gap: 2px;
      min-width: 84px; padding: 10px 16px;
      background: var(--top-card-bg); border: 1px solid var(--top-border);
      border-radius: var(--top-radius-card);
    }
    .lp-stat strong { font-size: 22px; font-weight: 900; color: var(--top-purple-dark); line-height: 1.1; }
    .lp-stat span { font-size: 11px; color: var(--top-text-muted); }

    .lp-cta-row { display: flex; flex-direction: column; align-items: center; gap: 12px; }
    .lp-cta {
      display: inline-flex; align-items: center; justify-content: center; gap: 8px;
      background: var(--top-purple); color: #fff;
      font-size: 16px; font-weight: 800; letter-spacing: 0.02em;
      padding: 15px 34px; border-radius: var(--top-radius-pill);
      box-shadow: 0 6px 18px rgba(108, 92, 166, 0.35);
      transition: background 120ms ease, transform 120ms ease;
    }
    .lp-cta:hover { background: var(--top-purple-dark); transform: translateY(-1px); }
    .lp-cta small { font-size: 11px; font-weight: 600; opacity: 0.85; }
    .lp-cta-sub { font-size: 13px; color: var(--top-purple); text-decoration: underline; }

    /* ── セクション共通 ── */
    .lp-section { padding: 28px 0; }
    .lp-section + .lp-section { border-top: 1px solid var(--top-border-light); }
    .lp-section h2 {
      margin: 0 0 14px; font-size: 19px; font-weight: 900; text-align: center;
      color: var(--top-purple-dark);
    }
    .lp-section h2 span {
      display: block; margin-bottom: 6px;
      font-family: 'IBM Plex Mono', 'Courier New', monospace;
      font-size: 10px; letter-spacing: 0.2em; font-weight: 500; color: var(--top-purple-light);
    }
    .lp-section-lead { margin: 0 auto 18px; max-width: 40em; font-size: 13.5px; color: var(--top-text-muted); text-align: center; }

    /* ── キャラクターマンホールとは ── */
    .lp-explain-grid { display: grid; gap: 10px; margin: 0 0 14px; padding: 0; list-style: none; }
    @media (min-width: 560px) { .lp-explain-grid { grid-template-columns: 1fr 1fr; } }
    .lp-explain-card {
      background: var(--top-card-bg); border: 1px solid var(--top-border);
      border-radius: var(--top-radius-card); padding: 16px;
    }
    .lp-explain-card strong { display: block; margin-bottom: 6px; font-size: 14px; }
    .lp-explain-card p { margin: 0; font-size: 13px; color: var(--top-text-muted); }

    /* ── 作品カード ── */
    .lp-work-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(200px, 1fr)); gap: 10px; margin: 0; padding: 0; list-style: none; }
    .lp-work-card {
      display: block; padding: 14px 16px;
      background: var(--top-card-bg); border: 1px solid var(--top-border);
      border-radius: var(--top-radius-card); text-decoration: none; color: inherit;
      transition: border-color 120ms ease, box-shadow 120ms ease;
    }
    .lp-work-card:hover { border-color: var(--top-purple); box-shadow: 0 4px 14px rgba(108,92,166,.15); }
    .lp-work-chip { display: inline-flex; align-items: center; justify-content: center; width: 22px; height: 22px; border-radius: 50%; color: #fff; font-size: 11px; font-weight: 800; margin-bottom: 8px; }
    .lp-work-card strong { display: block; font-size: 14px; font-weight: 800; margin-bottom: 4px; }
    .lp-work-card small { display: block; font-size: 12px; color: var(--top-text-muted); }

    /* ── 都道府県から探す ── */
    .lp-pref-list { display: grid; grid-template-columns: repeat(auto-fill, minmax(140px, 1fr)); gap: 8px; margin: 0; padding: 0; list-style: none; }
    .lp-pref-item {
      display: flex; align-items: center; justify-content: space-between; gap: 8px;
      padding: 10px 14px;
      background: var(--top-card-bg); border: 1px solid var(--top-border);
      border-radius: var(--top-radius-card); text-decoration: none; color: var(--top-text);
      font-size: 13px; font-weight: 700;
    }
    .lp-pref-item:hover { border-color: var(--top-purple); }
    .lp-pref-item span { font-size: 12px; font-weight: 800; color: var(--top-purple); }

    /* ── 地図で探す ── */
    .lp-map-card {
      display: flex; align-items: center; gap: 14px; text-decoration: none; color: inherit;
      background: var(--top-purple-pale); border-radius: var(--top-radius-card-lg);
      padding: 22px; transition: background 120ms ease;
    }
    .lp-map-card:hover { background: #E4DDF2; }
    .lp-map-card-icon { font-size: 32px; line-height: 1; }
    .lp-map-card strong { display: block; font-size: 16px; font-weight: 900; color: var(--top-purple-dark); margin-bottom: 4px; }
    .lp-map-card p { margin: 0; font-size: 12.5px; color: var(--top-purple-dark); opacity: .85; }
    .lp-map-card-arrow { margin-left: auto; font-weight: 800; color: var(--top-purple); font-size: 20px; }

    /* ── デザインマンホール投稿導線 ── */
    .lp-promo-card {
      display: flex; align-items: center; gap: 14px; text-decoration: none; color: inherit;
      background: var(--top-card-bg); border: 1px solid var(--top-border);
      border-radius: var(--top-radius-card-lg); padding: 20px;
      transition: border-color 120ms ease, box-shadow 120ms ease;
    }
    .lp-promo-card:hover { border-color: var(--top-purple); box-shadow: 0 6px 18px rgba(108,92,166,.15); }
    .lp-promo-icon { font-size: 30px; line-height: 1; }
    .lp-promo-card strong { display: block; font-size: 15px; font-weight: 800; margin-bottom: 4px; }
    .lp-promo-card p { margin: 0; font-size: 12.5px; color: var(--top-text-muted); }
    .lp-promo-arrow { margin-left: auto; font-weight: 800; color: var(--top-purple); font-size: 20px; }
    .lp-promo-sub { margin: 12px 0 0; text-align: center; font-size: 13px; }
    .lp-promo-sub a { color: var(--top-purple); text-decoration: underline; }

    /* ── みんなの投稿 ── */
    .lp-photo-grid { display: grid; grid-template-columns: repeat(2, 1fr); gap: 10px; margin: 0; padding: 0; list-style: none; }
    @media (min-width: 560px) { .lp-photo-grid { grid-template-columns: repeat(4, 1fr); } }
    .lp-photo-card { overflow: hidden; border: 1px solid var(--top-border); border-radius: var(--top-radius-card); background: var(--top-card-bg); color: inherit; }
    .lp-photo-card-main { display: block; color: inherit; text-decoration: none; }
    .lp-photo-card img { display: block; width: 100%; aspect-ratio: 4 / 3; object-fit: cover; background: var(--top-purple-pale); }
    .lp-photo-card-copy { display: block; padding: 8px 10px 2px; font-size: 12.5px; font-weight: 700; }
    .lp-photo-card-meta { display: block; padding: 0 10px 10px; font-size: 11px; color: var(--top-text-muted); __CAPTION_ELLIPSIS_CSS__ }
    .lp-photo-card-meta .poster-link { color: var(--top-purple); font-weight: 700; text-decoration: underline; text-underline-offset: 2px; }

    /* ── FAQ ── */
    .lp-faq { display: grid; gap: 10px; }
    .lp-faq details {
      background: var(--top-card-bg); border: 1px solid var(--top-border);
      border-radius: var(--top-radius-card); padding: 0 16px;
    }
    .lp-faq summary {
      cursor: pointer; list-style: none; position: relative;
      padding: 14px 26px 14px 0; font-size: 14px; font-weight: 700;
    }
    .lp-faq summary::-webkit-details-marker { display: none; }
    .lp-faq summary::after {
      content: '+'; position: absolute; right: 2px; top: 50%; transform: translateY(-50%);
      color: var(--top-purple); font-weight: 800; font-size: 18px;
    }
    .lp-faq details[open] summary::after { content: '−'; }
    .lp-faq details p { margin: 0 0 14px; font-size: 13px; color: var(--top-text-muted); }

    footer.data-links { margin: 8px 0 28px; text-align: center; font-size: 0.85rem; color: var(--top-text-muted); }
    footer.data-links a { color: var(--top-purple); text-decoration: underline; }
""".replace("__CAPTION_ELLIPSIS_CSS__", CAPTION_ELLIPSIS_CSS)


def _work_card_html(summary: dict) -> str:
    pref_text = "・".join(summary["prefectures"][:3])
    if len(summary["prefectures"]) > 3:
        pref_text += " ほか"
    map_href = f"{MAP_HREF}?work={quote(summary['query'])}"
    return (
        f'<li><a class="lp-work-card" href="{map_href}">'
        f'<span class="lp-work-chip" style="background:{escape(summary["color"])}">{escape(str(summary["label"])[:1])}</span>'
        f'<strong>{escape(summary["work"])}</strong>'
        f'<small>{summary["count"]}枚'
        + (f' ／ {escape(pref_text)}' if pref_text else '')
        + '</small></a></li>'
    )


def _pref_item_html(entry: dict) -> str:
    map_href = f"{MAP_HREF}?pref={quote(entry['prefecture'])}"
    return (
        f'<a class="lp-pref-item" href="{map_href}">'
        f'{escape(entry["prefecture"])}<span>{entry["count"]}枚</span></a>'
    )


def _photo_card_html(post: dict) -> str:
    poster_html = escape(post["poster"])
    if post["poster"] and post["poster_profile_url"]:
        poster_html = (
            f'<a class="poster-link" href="{escape(post["poster_profile_url"])}" '
            f'target="_blank" rel="noopener noreferrer">{escape(post["poster"])}</a>'
        )
    meta = caption_meta(
        escape(post["location"]),
        poster_html,
        escape(post["date"]) if post["date"] else "",
    )
    link_href = post["source_url"] or DESIGN_MANHOLE_HREF
    return (
        '<li class="lp-photo-card">'
        f'<a class="lp-photo-card-main" href="{escape(link_href)}" target="_blank" rel="noopener noreferrer">'
        f'<img src="{escape(post["photo_url"])}" alt="{escape(post["title"])} {escape(post["location"])}" '
        'loading="lazy" decoding="async" width="320" height="240">'
        f'<span class="lp-photo-card-copy">{escape(post["title"])}</span>'
        '</a>'
        f'<small class="lp-photo-card-meta">{meta}</small>'
        '</li>'
    )


def generate_html(
    character_records: list[dict],
    gundam_records: list[dict],
    design_manhole_path: Path,
) -> str:
    work_summaries = build_work_summaries(character_records, gundam_records)
    pref_summaries = build_prefecture_summaries(character_records, gundam_records)
    latest_posts = build_latest_posts(design_manhole_path)

    total_count = len(character_records) + len(gundam_records)
    work_count = len(work_summaries)
    pref_count = len(pref_summaries)

    title = f"キャラクターマンホールとは｜全国{total_count}枚・{work_count}作品のマンホールマップ"
    description = (
        f"ガンダムやゾンビランドサガなど、全国{total_count}枚・{work_count}作品のキャラクターマンホールを紹介。"
        "作品別・都道府県別に探せる一覧から、設置場所を地図で確認できます。"
        "ポケふた以外の面白いマンホールを見つけたら写真投稿でみんなの地図に追加できます。"
    )

    work_items_html = "\n".join(_work_card_html(summary) for summary in work_summaries)
    pref_items_html = "\n".join(_pref_item_html(entry) for entry in pref_summaries)

    if latest_posts:
        photo_items_html = "\n".join(_photo_card_html(post) for post in latest_posts)
        latest_section_html = f"""
    <section class="lp-section" aria-labelledby="lp-latest-heading">
      <h2 id="lp-latest-heading"><span>LATEST POSTS</span>みんなの投稿</h2>
      <p class="lp-section-lead">投稿されたデザインマンホールの最新写真です。</p>
      <ul class="lp-photo-grid">
{photo_items_html}
      </ul>
      <p class="lp-promo-sub"><a href="https://pokefuta.com/design-manholes" target="_blank" rel="noopener noreferrer">すべての投稿を見る →</a></p>
    </section>"""
    else:
        latest_section_html = ""

    faq_html = "".join(
        f'<details><summary>{escape(question)}</summary><p>{escape(answer)}</p></details>'
        for question, answer in FAQ_ITEMS
    )

    json_ld_webpage = {
        "@type": "WebPage",
        "@id": CANONICAL_URL,
        "url": CANONICAL_URL,
        "name": title,
        "description": description,
        "inLanguage": "ja",
        "isPartOf": {"@type": "WebSite", "name": "ポケふたDATABASE", "url": BASE_URL},
        "primaryImageOfPage": {"@type": "ImageObject", "url": OG_IMAGE, "width": 1200, "height": 630},
    }
    json_ld_breadcrumb = {
        "@type": "BreadcrumbList",
        "itemListElement": [
            {"@type": "ListItem", "position": 1, "name": "ホーム", "item": BASE_URL},
            {"@type": "ListItem", "position": 2, "name": "キャラクターマンホール", "item": CANONICAL_URL},
        ],
    }
    json_ld_faq = {
        "@type": "FAQPage",
        "mainEntity": [
            {
                "@type": "Question",
                "name": question,
                "acceptedAnswer": {"@type": "Answer", "text": answer},
            }
            for question, answer in FAQ_ITEMS
        ],
    }
    json_ld_itemlist = {
        "@type": "ItemList",
        "name": "収録しているキャラクターマンホールの作品",
        "itemListElement": [
            {
                "@type": "ListItem",
                "position": index,
                "name": summary["work"],
                "url": f"{MAP_URL}?work={quote(summary['query'])}",
            }
            for index, summary in enumerate(work_summaries, start=1)
        ],
    }
    json_ld = json.dumps(
        {"@context": "https://schema.org", "@graph": [json_ld_webpage, json_ld_breadcrumb, json_ld_faq, json_ld_itemlist]},
        ensure_ascii=False,
    )

    return f"""<!doctype html>
<html lang="ja">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>{escape(title)}</title>
  <meta name="description" content="{escape(description)}">
  <meta name="keywords" content="キャラクターマンホール,ガンダムマンホール,ゾンビランドサガ マンホール,ロマンシング サガ マンホール,弱虫ペダル マンホール,ちびまる子ちゃん マンホール,ポケふた,マンホールマップ,聖地巡礼">
  <meta name="robots" content="index,follow">
  <meta property="og:type" content="website">
  <meta property="og:locale" content="ja_JP">
  <meta property="og:site_name" content="ポケふたDATABASE">
  <meta property="og:title" content="{escape(title)}">
  <meta property="og:description" content="{escape(description)}">
  <meta property="og:url" content="{escape(CANONICAL_URL)}">
  <meta property="og:image" content="{escape(OG_IMAGE)}">
  <meta property="og:image:width" content="1200">
  <meta property="og:image:height" content="630">
  <meta name="twitter:card" content="summary_large_image">
  <meta name="twitter:title" content="{escape(title)}">
  <meta name="twitter:description" content="{escape(description)}">
  <meta name="twitter:image" content="{escape(OG_IMAGE)}">
  <link rel="canonical" href="{escape(CANONICAL_URL)}">
  <script type="application/ld+json">{json_ld}</script>
  <link rel="stylesheet" href="./assets/top-page.css?v=20260707a" />
  <script src="./assets/session-badge.js" defer></script>
  <style>{PAGE_STYLE}</style>
  <link rel="icon" href="./assets/pokefuta_icon_32.png" type="image/png" />
  <!-- Google Analytics -->
  <script async src="https://www.googletagmanager.com/gtag/js?id=G-K18NR4GZG2"></script>
  <script>
    window.dataLayer = window.dataLayer || [];
    function gtag(){{dataLayer.push(arguments);}}
    gtag('js', new Date());
    gtag('config', 'G-K18NR4GZG2', {{
      'anonymize_ip': true,
      'page_path': '/character_manholes',
      site_type: 'map',
      page_type: 'lp_character_manholes',
    }});
    window.trackEvent = function(action, params = {{}}) {{
      gtag('event', action, params);
    }};
  </script>
  <!-- End GA -->
</head>
<body class="character-manhole-lp">
  <!-- ===== APP BAR（ビルド時に inject_site_header.py が共通ヘッダーへ差し替える） ===== -->
  <header class="top-app-bar">
    <div class="top-app-bar-inner">
      <a class="top-brand" href="./" onclick="trackEvent('click_nav',{{nav:'home',from:'character_manholes_lp'}})">
        <span class="brand-name">ポケふた図鑑</span>
      </a>
      <div class="top-nav-right">
        <nav class="top-nav" aria-label="メインナビ">
          <a class="top-nav-link" href="map.html" onclick="trackEvent('click_nav',{{nav:'map',from:'character_manholes_lp'}})">マップ</a>
          <a class="top-nav-link" href="pokemon/" onclick="trackEvent('click_nav',{{nav:'pokemon',from:'character_manholes_lp'}})">ポケモン</a>
          <a class="top-nav-link top-nav-link--active" href="character_manholes.html" aria-current="page">キャラマンホール</a>
          <a class="top-nav-link" data-login-link data-nav-target="login" data-stamp-page="https://pokefuta.com/" data-stamp-label="スタンプ帳" href="https://pokefuta.com/login?from=data" onclick="trackEvent('click_nav',{{nav:this.dataset.navTarget,from:'character_manholes_lp'}})">ログイン</a>
        </nav>
      </div>
    </div>
  </header>

  <main class="lp-wrap">
    <!-- ── Hero ── -->
    <section class="lp-hero">
      <p class="lp-eyebrow">CHARACTER MANHOLE COLLECTION</p>
      <h1>キャラクターマンホールって<br>知っていますか？</h1>
      <p class="lp-lead">
        ガンダム、ゾンビランドサガ、ロマンシング サガ、弱虫ペダル——。
        <b>アニメ・漫画・ご当地キャラの絵柄</b>をあしらったマンホール蓋が、全国の自治体に設置されています。
        聖地巡礼とセットで巡れる、もうひとつのマンホール蒐集です。
      </p>
      <div class="lp-stats-row">
        <div class="lp-stat"><strong>{total_count}</strong><span>枚</span></div>
        <div class="lp-stat"><strong>{work_count}</strong><span>作品</span></div>
        <div class="lp-stat"><strong>{pref_count}</strong><span>都道府県</span></div>
      </div>
      <div class="lp-cta-row">
        <a class="lp-cta" href="{MAP_HREF}"
           onclick="trackEvent('click_map_cta',{{cta:'hero',from:'character_manholes_lp'}})">
          🗺 地図で探す
        </a>
        <a class="lp-cta-sub" href="#lp-works-heading"
           onclick="trackEvent('click_nav',{{nav:'works_anchor',from:'character_manholes_lp'}})">収録している作品を見る</a>
      </div>
    </section>

    <!-- ── キャラクターマンホールとは ── -->
    <section class="lp-section" aria-labelledby="lp-about-heading">
      <h2 id="lp-about-heading"><span>WHAT IS IT</span>キャラクターマンホールとは</h2>
      <ul class="lp-explain-grid">
        <li class="lp-explain-card">
          <strong>作品・自治体ごとに1枚1枚違う</strong>
          <p>アニメや漫画とタイアップした自治体が、その土地ならではのデザインで設置するマンホール蓋です。設置場所は聖地巡礼スポットと重なることが多く、キャラクターに会いに行くような感覚で巡れます。</p>
        </li>
        <li class="lp-explain-card">
          <strong>ポケふたとの違い</strong>
          <p>ポケふた（ポケモンマンホール）はポケモン公式の全国シリーズです。キャラクターマンホールはガンダムやゾンビランドサガなど作品ごと・自治体ごとに独自展開されており、このマップでは両方を重ねて表示できます。</p>
        </li>
      </ul>
    </section>

    <!-- ── 収録している作品 ── -->
    <section class="lp-section" aria-labelledby="lp-works-heading">
      <h2 id="lp-works-heading"><span>WORKS</span>収録している作品</h2>
      <p class="lp-section-lead">作品をタップすると、その作品だけを表示した地図が開きます。</p>
      <ul class="lp-work-grid">
{work_items_html}
      </ul>
    </section>

    <!-- ── 都道府県から探す ── -->
    <section class="lp-section" aria-labelledby="lp-pref-heading">
      <h2 id="lp-pref-heading"><span>PREFECTURES</span>都道府県から探す</h2>
      <p class="lp-section-lead">都道府県をタップすると、その地域にズームした地図が開きます。</p>
      <div class="lp-pref-list">
{pref_items_html}
      </div>
    </section>

    <!-- ── 地図で探す ── -->
    <section class="lp-section" aria-labelledby="lp-map-heading">
      <h2 id="lp-map-heading"><span>MAP</span>地図で探す</h2>
      <a class="lp-map-card" href="{MAP_HREF}"
         onclick="trackEvent('click_map_cta',{{cta:'map_section',from:'character_manholes_lp'}})">
        <span class="lp-map-card-icon" aria-hidden="true">🗺</span>
        <span>
          <strong>{total_count}枚を地図に表示</strong>
          <p>現在地から近いマンホールを探したり、作品ごとに絞り込んで表示できます。</p>
        </span>
        <span class="lp-map-card-arrow" aria-hidden="true">→</span>
      </a>
    </section>

    <!-- ── デザインマンホール投稿導線 ── -->
    <section class="lp-section" aria-labelledby="lp-post-heading">
      <h2 id="lp-post-heading"><span>SUBMIT</span>ほかにも面白いマンホールを見つけたら</h2>
      <a class="lp-promo-card" href="{DESIGN_MANHOLE_HREF}"
         onclick="trackEvent('click_design_manhole_lp',{{from:'character_manholes_lp'}})">
        <span class="lp-promo-icon" aria-hidden="true">📸</span>
        <span>
          <strong>この地図にない1枚も、投稿でマップに。</strong>
          <p>ポケふた以外の「オンリーワンな1枚」を写真で投稿すると、みんなのデザインマンホールマップに掲載されます。</p>
        </span>
        <span class="lp-promo-arrow" aria-hidden="true">→</span>
      </a>
      <p class="lp-promo-sub"><a href="https://pokefuta.com/design-manholes" target="_blank" rel="noopener noreferrer">みんなの投稿を見る →</a></p>
    </section>
{latest_section_html}

    <!-- ── FAQ ── -->
    <section class="lp-section" aria-labelledby="lp-faq-heading">
      <h2 id="lp-faq-heading"><span>FAQ</span>よくある質問</h2>
      <div class="lp-faq">
        {faq_html}
      </div>
    </section>

    <footer class="data-links" role="contentinfo">
      <p style="margin:0;">
        <a href="./">ポケふたマップ</a>
        /
        <a href="{MAP_HREF}">キャラクターマンホールマップ</a>
        /
        <a href="{DESIGN_MANHOLE_HREF}">デザインマンホール投稿</a>
        /
        <a href="./character_manholes.ndjson" target="_blank" rel="noopener">キャラNDJSON</a>
        /
        <a href="./gmanhole.ndjson" target="_blank" rel="noopener">ガンダムNDJSON</a>
      </p>
    </footer>
  </main>
</body>
</html>
"""


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--character-manholes", default=str(DEFAULT_CHARACTER_MANHOLES))
    parser.add_argument("--gundam", default=str(DEFAULT_GUNDAM))
    parser.add_argument("--design-manholes", default=str(DEFAULT_DESIGN_MANHOLES))
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    args = parser.parse_args()

    character_records = load_active_manholes(Path(args.character_manholes))
    gundam_records = load_active_manholes(Path(args.gundam))
    if not character_records and not gundam_records:
        logger.error("No active character/gundam manholes loaded — refusing to write an empty page")
        return 1

    html = generate_html(character_records, gundam_records, Path(args.design_manholes))

    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(html, encoding="utf-8")
    logger.info(
        f"[generate_character_manhole_page] wrote {output_path} "
        f"({len(character_records) + len(gundam_records)} manholes)"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
