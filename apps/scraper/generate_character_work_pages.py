#!/usr/bin/env python3
"""Build the /characters/ index and static /characters/<slug>/ work guides."""

from __future__ import annotations

import argparse
import json
import math
import sys
from collections import Counter, defaultdict
from datetime import datetime
from html import escape
from pathlib import Path
from urllib.parse import quote, urlencode, urlparse

try:
    from apps.scraper.character_manhole_works import WORK_PAGES, WorkPage, available_pages
    from apps.scraper.generate_character_manhole_page import (
        BASE_URL, GUNDAM_WORK_NAME, GUNDAM_WORK_QUERY, MAP_URL, ROOT, _is_active, load_ndjson,
    )
    from apps.scraper.photo_caption import JST
    from apps.scraper.prefectures import PREFECTURE_ORDER
except ModuleNotFoundError as exc:
    if exc.name != "apps":
        raise
    from character_manhole_works import WORK_PAGES, WorkPage, available_pages
    from generate_character_manhole_page import (
        BASE_URL, GUNDAM_WORK_NAME, GUNDAM_WORK_QUERY, MAP_URL, ROOT, _is_active, load_ndjson,
    )
    from photo_caption import JST
    from prefectures import PREFECTURE_ORDER

ASSET_BASE = "../../"
INDEX_ASSET_BASE = "../"
DEFAULT_EVENTS = ROOT / "dataset/character_manhole_events.json"
DEFAULT_GUNDAM = ROOT / "docs/gmanhole.ndjson"
CARD_CHARACTER_LIMIT = 4
OG_IMAGE = BASE_URL + "assets/ogp/pokefuta_map_ogp.png"
IDOLMASTER_EVENT_TYPE = "idolmaster_20th_checkin"
EVENT_REQUIRED_KEYS = {"type", "url", "project_url", "verified_at", "ends_at", "spots"}


def safe_url(value: object) -> str:
    url = str(value or "")
    try:
        parsed = urlparse(url)
        return url if parsed.scheme in {"https", "http"} and parsed.netloc else ""
    except ValueError:
        return ""


def json_script(value: object) -> str:
    return json.dumps(value, ensure_ascii=False).replace("<", "\\u003c")


def map_href(work: str, prefecture: str = "") -> str:
    params = {"work": work}
    if prefecture:
        params["pref"] = prefecture
    return f"{ASSET_BASE}gmanhole_map.html?{urlencode(params)}"


def spot_id(record: dict) -> str:
    return "spot-" + quote(str(record["id"]), safe="")


def has_coordinates(record: dict) -> bool:
    lat, lng = record.get("lat"), record.get("lng")
    return all(isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v)
               for v in (lat, lng)) and -90 <= lat <= 90 and -180 <= lng <= 180


def validate_event(slug: str, raw: object) -> dict | None:
    """ふたマス用イベント設定を検証し、壊れた任意情報は警告して無視する。"""
    if not isinstance(raw, dict):
        print(f"WARN: event {slug}: expected an object, skipping", file=sys.stderr)
        return None
    missing = EVENT_REQUIRED_KEYS - raw.keys()
    if missing:
        print(f"WARN: event {slug}: missing {sorted(missing)}, skipping", file=sys.stderr)
        return None
    if slug != "idolmaster" or raw.get("type") != IDOLMASTER_EVENT_TYPE:
        print(f"WARN: event {slug}: unsupported event type, skipping", file=sys.stderr)
        return None
    if not safe_url(raw.get("url")) or not safe_url(raw.get("project_url")):
        print(f"WARN: event {slug}: invalid official URL, skipping", file=sys.stderr)
        return None
    if not isinstance(raw.get("spots"), dict):
        print(f"WARN: event {slug}: spots must be an object, skipping", file=sys.stderr)
        return None
    try:
        end = datetime.fromisoformat(str(raw["ends_at"]))
    except (TypeError, ValueError):
        print(f"WARN: event {slug}: invalid ends_at, skipping", file=sys.stderr)
        return None
    if end.tzinfo is None:
        print(f"WARN: event {slug}: ends_at must include a timezone, skipping", file=sys.stderr)
        return None
    return {**raw, "_ends_at": end}


def load_events(path: Path) -> dict[str, dict]:
    """イベントJSONを読み、無効な任意設定でサイト全体の生成を止めない。"""
    try:
        raw_events = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        print(f"WARN: could not load character events: {exc}", file=sys.stderr)
        return {}
    if not isinstance(raw_events, dict):
        print("WARN: character events root must be an object, skipping", file=sys.stderr)
        return {}
    return {
        slug: event
        for slug, raw in raw_events.items()
        if (event := validate_event(str(slug), raw)) is not None
    }


def event_for_page(slug: str, events: dict) -> dict | None:
    """Return a loaded event as-is, while still accepting raw mappings in callers/tests."""
    raw = events.get(slug)
    if isinstance(raw, dict) and isinstance(raw.get("_ends_at"), datetime):
        return raw
    return validate_event(slug, raw) if raw is not None else None


def event_html(event: dict, now: datetime) -> tuple[str, str, bool]:
    """ふたマスの案内を生成し、期限後は参加手順とチェックイン導線を外す。"""
    end = event["_ends_at"]
    active = now < end
    deadline = f"{end.year}年{end.month}月{end.day}日 {end.hour}:{end.minute:02d}（日本時間）"
    label = "公式チェックイン企画" if active else "掲載期間は終了しました"
    url = escape(safe_url(event["url"]))
    project_url = escape(safe_url(event.get("project_url")))
    badge = f'<a class="cw-event-badge" href="#check-in">{label} →</a>'
    source_links = f"""出典：<a href="{url}" target="_blank" rel="noopener noreferrer">アイドルマスター ポータル・スポットチェックイン</a>。
      <a href="{project_url}" target="_blank" rel="noopener noreferrer">ふたマス!!!!!!公式プロジェクト</a>。"""
    if not active:
        html = f"""<section class="cw-event" id="check-in" aria-labelledby="check-in-heading">
      <div><p class="cw-eyebrow">OFFICIAL SPOT CHECK-IN</p>
      <h2 id="check-in-heading">チェックイン企画の掲載期間は終了しました</h2>
      <p>公式掲載の期間は終了しています。新しい企画や現在の受付状況は、公式サイトの最新情報をご確認ください。</p>
      <p class="cw-deadline">公式掲載の終了日時：<time datetime="{escape(event['ends_at'])}">{deadline}</time></p>
      <p class="cw-note">確認日：{escape(str(event['verified_at']))}</p></div>
      <div class="cw-actions"><a class="cw-button" href="{project_url}" target="_blank" rel="noopener noreferrer">公式プロジェクトの最新情報を見る ↗</a></div>
      <p class="cw-note">{source_links}</p>
    </section>"""
        return badge, html, active

    html = f"""<section class="cw-event" id="check-in" aria-labelledby="check-in-heading">
      <div><p class="cw-eyebrow">OFFICIAL SPOT CHECK-IN</p>
      <h2 id="check-in-heading">ふたを訪ねて、公式チェックイン。</h2>
      <p>ふたマスの対象スポットを訪ねると、公式ポータルのチェックイン企画に参加できます。
      公式マイデスクに表示できる称号の獲得が案内されています。チェックインはアイドルマスター ポータルで行います。</p>
      <p class="cw-deadline">公式掲載の終了予定：<time datetime="{escape(event['ends_at'])}">{deadline}</time></p>
      <p class="cw-note">確認日：{escape(str(event['verified_at']))}。開始日時はスポットごとに異なり、期間は変更される場合があります。最新条件は公式で確認してください。</p></div>
      <ol class="cw-steps">
        <li><strong>バンダイナムコIDを用意</strong><span>特典を受け取るアカウントで、公式ポータルにログインします。</span></li>
        <li><strong>対象のマンホールへ</strong><span>スマートフォンとブラウザで位置情報の利用を許可。安全な場所に立ち止まって操作します。</span></li>
        <li><strong>公式ページでチェックイン</strong><span>対象スポットの案内に従って参加。同じスポットは1回限り有効です。</span></li>
      </ol>
      <a class="cw-button" href="{url}" target="_blank" rel="noopener noreferrer">公式でチェックイン方法を確認する ↗</a>
      <p class="cw-note">{source_links} 本ページはポケふた図鑑による訪問ガイドです。写真投稿だけでは公式チェックインは完了しません。</p>
    </section>"""
    return badge, html, active


def spot_html(record: dict, event: dict | None, event_active: bool) -> str:
    name = str(record.get("character") or record.get("title") or "マンホール")
    location = str(record.get("landmark") or record.get("title") or "設置場所")
    source = safe_url(record.get("official_url") or record.get("source_url"))
    address = str(record.get("address") or "詳細な住所は出典でご確認ください")
    if has_coordinates(record):
        maps = "https://www.google.com/maps/search/?" + urlencode({"api": "1", "query": f"{record['lat']},{record['lng']}"})
        map_label = "設置場所の地図"
        coordinate_note = ""
    else:
        maps = "https://www.google.com/maps/search/?" + urlencode({"api": "1", "query": address + " " + location})
        map_label = "施設の住所を地図で確認"
        coordinate_note = '<p class="cw-note">正確な座標は確認中です。全国地図のピンにはまだ表示されません。</p>'
    links = f'<a href="{escape(maps)}" target="_blank" rel="noopener noreferrer">{map_label} ↗</a>'
    if source:
        links += f'<a href="{escape(source)}" target="_blank" rel="noopener noreferrer">出典・設置案内 ↗</a>'
    if event_active and event and str(record["id"]) in event["spots"]:
        checkin = safe_url(event["url"].rstrip("/") + "/" + str(event["spots"][str(record["id"])]).lstrip("/"))
        links += f'<a href="{escape(checkin)}" target="_blank" rel="noopener noreferrer">公式スポット案内（ログインが必要）↗</a>'
    return f"""<article class="cw-spot" id="{spot_id(record)}">
      <p class="cw-series">{escape(str(record.get('work') or ''))}</p>
      <h4>{escape(name)}</h4><p class="cw-location">{escape(location)}</p>
      <p>{escape(address)}</p>{coordinate_note}<div class="cw-spot-links">{links}</div>
    </article>"""


def generate_html(page: WorkPage, records: list[dict], events: dict,
                  *, now: datetime | None = None, related: tuple[WorkPage, ...] = ()) -> str:
    selected = [r for r in records if _is_active(r) and r.get("work") in page.works]
    if not selected:
        raise ValueError(f"No active records for {page.slug}")
    now = now or datetime.now(JST)
    count = len(selected)
    pref_count = len({r.get("prefecture") for r in selected if r.get("prefecture")})
    title = f"{page.search_name}マンホール一覧｜設置場所・地図"
    if page.slug == "idolmaster":
        title = "アイマス・ふたマスのマンホール一覧｜設置場所とチェックイン方法"
    description = f"{page.name}のマンホール{count}枚を掲載。{page.intro}"
    canonical = BASE_URL + page.path
    event = event_for_page(page.slug, events)
    badge, event_section, event_active = event_html(event, now) if event else ("", "", False)
    hero_heading = "アイマスのマンホール、<br>会いに行こう。" if event_active else f"{escape(page.name)}の<br>マンホールを探そう。"
    hero_note = "担当アイドルのふたを訪ねて、公式チェックインへ。" if event_active else "好きな作品を、次の旅の目的地に。"
    passport = ("場所を選ぶ", "会いに行く", "公式でチェックイン") if event_active else ("場所を選ぶ", "地図で確かめる", "現地で見つける")
    passport_html = "".join(f'<li><span>0{i}</span>{escape(text)}</li>' for i, text in enumerate(passport, 1))
    hero_cta = '<a class="cw-text-link" href="#check-in">チェックインの参加方法 →</a>' if event_active else ""
    brand_counts = Counter(r["work"] for r in selected)
    brands_html = "".join(
        f'<a href="{escape(map_href(work))}">{escape(work)} <span>{brand_counts[work]}枚 ↗</span></a>'
        for work in page.works if brand_counts[work]
    )
    pref_order = {pref: i for i, pref in enumerate(PREFECTURE_ORDER)}
    selected.sort(key=lambda r: (pref_order.get(r.get("prefecture"), 999), str(r.get("city") or ""), str(r["id"])))
    index_html = "".join(
        f'<a href="#{spot_id(r)}"><strong>{escape(str(r.get("character") or r.get("title") or "マンホール"))}</strong>'
        f'<span>{escape(str(r.get("prefecture") or ""))} {escape(str(r.get("city") or ""))}</span></a>'
        for r in selected
    )
    groups = defaultdict(list)
    for record in selected:
        groups[(str(record.get("prefecture") or "都道府県未記録"), str(record.get("city") or ""))].append(record)
    locations_html = "".join(
        f'<section class="cw-city"><h3>{escape(pref)} {escape(city)} <small>{len(rows)}枚</small></h3>'
        f'<div class="cw-spots">{"".join(spot_html(r, event, event_active) for r in rows)}</div></section>'
        for (pref, city), rows in groups.items()
    )
    related_html = "".join(f'<a href="../{other.slug}/">{escape(other.name)} →</a>' for other in related if other.slug != page.slug)
    faq = [
        (page.question, page.answer),
        ("掲載されているマンホールがすべてですか？", "掲載データに収録した設置場所の一覧です。全国すべての設置状況を網羅するものではありません。移設・撤去や施設の開放時間は、訪問前に出典の案内をご確認ください。"),
    ]
    if event_active:
        faq.append(("このサイトでチェックインできますか？", "チェックインは公式のアイドルマスター ポータルで行います。バンダイナムコIDでのログインと位置情報の許可が必要です。写真館への投稿とは別のサービスです。"))
    faq_html = "".join(f'<details><summary>{escape(q)}</summary><p>{escape(a)}</p></details>' for q, a in faq)
    schema = {"@context": "https://schema.org", "@graph": [
        {"@type": "CollectionPage", "@id": canonical, "url": canonical, "name": title, "description": description, "inLanguage": "ja", "mainEntity": {"@id": canonical + "#list"}},
        {"@type": "BreadcrumbList", "itemListElement": [
            {"@type": "ListItem", "position": 1, "name": "ポケふた図鑑", "item": BASE_URL},
            {"@type": "ListItem", "position": 2, "name": "キャラクターマンホール全国一覧", "item": BASE_URL + "character_manholes.html"},
            {"@type": "ListItem", "position": 3, "name": "作品から探す", "item": BASE_URL + "characters/"},
            {"@type": "ListItem", "position": 4, "name": page.name, "item": canonical},
        ]},
        {"@type": "ItemList", "@id": canonical + "#list", "numberOfItems": count, "itemListElement": [
            {"@type": "ListItem", "position": i, "name": str(r.get("title") or r.get("character") or "マンホール"), "url": canonical + "#" + spot_id(r)}
            for i, r in enumerate(selected, 1)
        ]},
    ]}
    analytics = {"page_path": "/" + page.path, "site_type": "map", "page_type": "lp_character_work", "work": page.slug}
    map_count = sum(has_coordinates(r) for r in selected)
    map_note = f"地図のピンは座標確認済みの{map_count}枚。" if map_count != count else ""
    return f"""<!doctype html>
<html lang="ja"><head>
  <meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{escape(title)}</title><meta name="description" content="{escape(description)}">
  <link rel="canonical" href="{canonical}"><meta name="robots" content="index,follow">
  <meta property="og:type" content="website"><meta property="og:locale" content="ja_JP">
  <meta property="og:title" content="{escape(title)}"><meta property="og:description" content="{escape(description)}">
  <meta property="og:url" content="{canonical}"><meta property="og:site_name" content="ポケふた図鑑">
  <meta property="og:image" content="{OG_IMAGE}"><meta property="og:image:width" content="1200"><meta property="og:image:height" content="630">
  <meta name="twitter:card" content="summary_large_image"><meta name="twitter:image" content="{OG_IMAGE}">
  <link rel="icon" href="{ASSET_BASE}assets/pokefuta_icon_32.png">
  <link rel="stylesheet" href="{ASSET_BASE}assets/top-page.css?v=20260707a">
  <link rel="stylesheet" href="{ASSET_BASE}assets/character-work.css?v=20260920c">
  <script type="application/ld+json">{json_script(schema)}</script>
  <script src="{ASSET_BASE}assets/analytics.js?v=20260805a"></script>
  <script>window.PokefutaAnalytics.init({json_script(analytics)});</script>
</head><body class="character-work-page">
  <main class="cw-wrap">
    <nav class="cw-breadcrumb" aria-label="パンくず"><a href="{ASSET_BASE}">ポケふた図鑑</a><span>/</span><a href="{ASSET_BASE}character_manholes.html">キャラクターマンホール</a><span>/</span><a href="../">作品から探す</a><span>/</span><span>{escape(page.name)}</span></nav>
    <section class="cw-hero" aria-labelledby="work-heading">
      <div class="cw-hero-copy"><p class="cw-eyebrow">MANHOLE TRIP GUIDE / {escape(page.name)}</p>{badge}
        <h1 id="work-heading">{hero_heading}</h1><p class="cw-hero-lead">{hero_note}</p>
        <p>{escape(page.intro)}</p><div class="cw-actions"><a class="cw-button" href="#locations">アイドル・設置場所を探す ↓</a>{hero_cta}</div>
        <p class="cw-note">掲載 {count}枚 / {pref_count}都道府県　{map_note}</p>
      </div>
      <aside class="cw-passport" aria-label="旅の流れ"><p class="cw-eyebrow">YOUR NEXT STOP</p><div class="cw-stamp" aria-hidden="true"><span>MEET<br>YOUR<br>FAVORITE</span></div><p class="cw-passport-title">街で出会う、<br>もうひとつの物語。</p><ol>{passport_html}</ol><span class="cw-passport-foot">POKEFUTA / TRAVEL NOTES</span></aside>
    </section>
    {event_section}
    <section class="cw-section" id="locations" aria-labelledby="locations-heading">
      <p class="cw-eyebrow">FIND YOUR FAVORITE</p><h2 id="locations-heading">{escape(page.name)}のマンホール一覧</h2>
      <p>{escape(page.guide)}</p><div class="cw-index">{index_html}</div>
      <div class="cw-actions"><a class="cw-button cw-button-secondary" href="{escape(map_href(page.map_query))}">作品の全国地図を見る →</a></div>
      {locations_html}
    </section>
    <section class="cw-section" aria-labelledby="series-heading"><h2 id="series-heading">シリーズ別に地図で探す</h2><div class="cw-brand-links">{brands_html}</div></section>
    <section class="cw-section" aria-labelledby="visit-heading"><h2 id="visit-heading">訪問前に確認したいこと</h2>
      <p>施設の開放時間・移設・撤去などは出典の案内をご確認ください。地図の座標には誤差がある場合があります。</p>
      <p>この一覧はマンホール本体の設置場所です。マンホールカードの配布場所・配布時間・在庫は自治体や配布施設の案内で別途ご確認ください。</p>
      <div class="cw-faq">{faq_html}</div></section>
    <section class="cw-section cw-post"><p class="cw-eyebrow">YOUR TRAVEL NOTES</p><h2>出会ったふたを、写真で残そう。</h2>
      <p>位置情報つきの写真を、ポケふた写真館に投稿できます。</p><a class="cw-button cw-button-secondary" href="{ASSET_BASE}design_manhole.html">写真投稿の方法を見る →</a></section>
    <nav class="cw-section cw-related" aria-label="ほかの作品"><h2>ほかの作品も探す</h2>{related_html}<a href="../">作品別ガイド一覧へ →</a><a href="{ASSET_BASE}character_manholes.html">全国一覧へ →</a></nav>
  </main>
</body></html>"""


def _sort_prefectures(prefectures: set[str]) -> list[str]:
    return sorted(prefectures, key=lambda pref: PREFECTURE_ORDER.index(pref)
                  if pref in PREFECTURE_ORDER else len(PREFECTURE_ORDER))


def index_entries(active: list[dict], gundam_records: list[dict]) -> list[dict]:
    """作品カードの素材。専用ページのない作品（ガンダム）は地図リンクで同じ並びに載せる。

    全国一覧(character_manholes.html)と同じ母集団・同じ件数降順にして、
    2ページ間で「何作品・何枚」が食い違わないようにする。
    """
    entries = []
    for page in available_pages(active):
        selected = [record for record in active if record.get("work") in page.works]
        entries.append({
            "name": page.name, "records": selected,
            "href": f"./{page.slug}/", "url": BASE_URL + page.path,
            "cta": "設置場所の一覧を見る →",
        })
    if gundam_records:
        entries.append({
            "name": GUNDAM_WORK_NAME, "records": gundam_records,
            "href": f"{INDEX_ASSET_BASE}gmanhole_map.html?work={quote(GUNDAM_WORK_QUERY)}",
            "url": f"{MAP_URL}?work={quote(GUNDAM_WORK_QUERY)}",
            "cta": "地図で設置場所を見る →",
        })
    return sorted(entries, key=lambda entry: (-len(entry["records"]), entry["name"]))


def _card_summary(entry: dict, prefectures: list[str]) -> str:
    """カードの説明文。作品ページのリード文を複製せず、データから書く。"""
    names: list[str] = []
    for record in entry["records"]:
        name = str(record.get("character") or "").strip()
        if name and name not in names:
            names.append(name)
    cities = {str(record.get("city")) for record in entry["records"] if record.get("city")}
    where = prefectures[0] if len(prefectures) == 1 else f"{len(prefectures)}都道府県"
    if len(cities) > 1:
        where += f"の{len(cities)}市区町村"
    if not names:
        return f"{where}に設置されています。"
    # キャラ名自体に「・」を含むものがある（例: まる子・友蔵）ので区切りは読点にする
    shown = "、".join(names[:CARD_CHARACTER_LIMIT])
    if len(names) > CARD_CHARACTER_LIMIT:
        shown += f" ほか{len(names) - CARD_CHARACTER_LIMIT}種"
    return f"{shown}の絵柄が、{where}に設置されています。"


def _cross_table_html(entries: list[dict]) -> str:
    """都道府県 × 作品の早見表。全国一覧は都道府県別、作品ページは作品別なので、この交差はここにしかない。"""
    grid: dict[str, list[tuple[str, int, str]]] = defaultdict(list)
    for entry in entries:
        counts = Counter(str(record.get("prefecture") or "") for record in entry["records"])
        for prefecture, count in counts.items():
            if prefecture:
                grid[prefecture].append((entry["name"], count, entry["href"]))
    rows = []
    for prefecture in _sort_prefectures(set(grid)):
        cells = "".join(
            f'<a href="{escape(href)}">{escape(name)} <span>{count}</span></a>'
            for name, count, href in sorted(grid[prefecture], key=lambda item: (-item[1], item[0]))
        )
        total = sum(count for _, count, _ in grid[prefecture])
        rows.append(f'<tr><th scope="row">{escape(prefecture)}<span>{total}枚</span></th>'
                    f'<td><div class="cw-cross-links">{cells}</div></td></tr>')
    return f"""<table class="cw-cross">
        <thead><tr><th scope="col">都道府県</th><th scope="col">掲載のある作品（枚数）</th></tr></thead>
        <tbody>{"".join(rows)}</tbody>
      </table>"""


def generate_index_html(records: list[dict], gundam_records: list[dict] | None = None) -> str:
    """Build the /characters/ hub from the same active records as work pages."""
    active = [record for record in records if _is_active(record)]
    gundam_active = [record for record in (gundam_records or []) if _is_active(record)]
    entries = index_entries(active, gundam_active)
    if not available_pages(active):
        raise ValueError("No character work pages available")
    canonical = BASE_URL + "characters/"
    title = "キャラクターマンホールを作品から探す｜作品別ガイド"
    total = sum(len(entry["records"]) for entry in entries)
    prefectures = {str(record.get("prefecture")) for entry in entries
                   for record in entry["records"] if record.get("prefecture")}
    lead_names = "・".join(entry["name"].split("（")[0] for entry in entries[:3])
    description = (f"{lead_names}など{len(entries)}作品、キャラクターマンホール{total}枚。"
                   "作品ごとのガイドと都道府県別の早見表から、設置場所を探せます。")
    cards = []
    item_list = []
    for position, entry in enumerate(entries, 1):
        entry_prefs = _sort_prefectures(
            {str(record.get("prefecture")) for record in entry["records"] if record.get("prefecture")}
        )
        pref_label = entry_prefs[0] if len(entry_prefs) == 1 else f"{len(entry_prefs)}都道府県"
        cards.append(f"""<article class="cw-work-card">
          <p class="cw-eyebrow">WORK {position:02d}</p><h3><a href="{escape(entry['href'])}">{escape(entry['name'])}</a></h3>
          <p>{escape(_card_summary(entry, entry_prefs))}</p><p class="cw-work-meta"><strong>{len(entry['records'])}枚</strong><span>{escape(pref_label)}</span></p>
          <p class="cw-note">{escape("・".join(entry_prefs))}</p><a class="cw-card-link" href="{escape(entry['href'])}">{escape(entry['cta'])}</a>
        </article>""")
        item_list.append({
            "@type": "ListItem", "position": position, "name": entry["name"],
            "url": entry["url"],
        })
    cross_table_html = _cross_table_html(entries)
    schema = {"@context": "https://schema.org", "@graph": [
        {"@type": "CollectionPage", "@id": canonical, "url": canonical, "name": title,
         "description": description, "inLanguage": "ja", "mainEntity": {"@id": canonical + "#list"}},
        {"@type": "BreadcrumbList", "itemListElement": [
            {"@type": "ListItem", "position": 1, "name": "ポケふた図鑑", "item": BASE_URL},
            {"@type": "ListItem", "position": 2, "name": "キャラクターマンホール全国一覧", "item": BASE_URL + "character_manholes.html"},
            {"@type": "ListItem", "position": 3, "name": "作品から探す", "item": canonical},
        ]},
        {"@type": "ItemList", "@id": canonical + "#list", "numberOfItems": len(entries),
         "itemListElement": item_list},
    ]}
    analytics = {"page_path": "/characters/", "site_type": "map", "page_type": "index_character_works"}
    return f"""<!doctype html>
<html lang="ja"><head>
  <meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{escape(title)}</title><meta name="description" content="{escape(description)}">
  <link rel="canonical" href="{canonical}"><meta name="robots" content="index,follow">
  <meta property="og:type" content="website"><meta property="og:locale" content="ja_JP">
  <meta property="og:title" content="{escape(title)}"><meta property="og:description" content="{escape(description)}">
  <meta property="og:url" content="{canonical}"><meta property="og:site_name" content="ポケふた図鑑">
  <meta property="og:image" content="{OG_IMAGE}"><meta property="og:image:width" content="1200"><meta property="og:image:height" content="630">
  <meta name="twitter:card" content="summary_large_image"><meta name="twitter:image" content="{OG_IMAGE}">
  <link rel="icon" href="{INDEX_ASSET_BASE}assets/pokefuta_icon_32.png">
  <link rel="stylesheet" href="{INDEX_ASSET_BASE}assets/top-page.css?v=20260707a">
  <link rel="stylesheet" href="{INDEX_ASSET_BASE}assets/character-work.css?v=20260920c">
  <script type="application/ld+json">{json_script(schema)}</script>
  <script src="{INDEX_ASSET_BASE}assets/analytics.js?v=20260805a"></script>
  <script>window.PokefutaAnalytics.init({json_script(analytics)});</script>
</head><body class="character-work-page character-index-page">
  <main class="cw-wrap">
    <nav class="cw-breadcrumb" aria-label="パンくず"><a href="{INDEX_ASSET_BASE}">ポケふた図鑑</a><span>/</span><a href="{INDEX_ASSET_BASE}character_manholes.html">キャラクターマンホール</a><span>/</span><span>作品から探す</span></nav>
    <section class="cw-hero" aria-labelledby="characters-heading">
      <div class="cw-hero-copy"><p class="cw-eyebrow">CHARACTER MANHOLE COLLECTION</p>
        <h1 id="characters-heading">好きな作品から、<br>マンホールを探そう。</h1>
        <p class="cw-hero-lead">行き先が決まっていないときは、推しの作品から。</p>
        <p>作品ごとのガイドで、設置場所・住所・地図・出典を確認できます。訪ねたい地域が決まっている場合は、下の都道府県別の早見表から作品を選べます。</p>
        <div class="cw-actions"><a class="cw-button" href="#works">作品を選ぶ ↓</a><a class="cw-text-link" href="#by-prefecture">都道府県から選ぶ →</a></div>
      </div>
      <aside class="cw-passport cw-index-stats" aria-label="掲載データ"><p class="cw-eyebrow">COLLECTION INDEX</p>
        <p class="cw-index-total"><strong>{total}</strong><span>MANHOLES</span></p>
        <dl><div><dt>作品</dt><dd>{len(entries)}</dd></div><div><dt>都道府県</dt><dd>{len(prefectures)}</dd></div></dl>
        <span class="cw-passport-foot">POKEFUTA / CHARACTER WORKS</span></aside>
    </section>
    <section class="cw-section" id="works" aria-labelledby="works-heading">
      <p class="cw-eyebrow">CHOOSE A WORK</p><h2 id="works-heading">作品から選ぶ</h2>
      <p>掲載枚数と地域を見比べて、訪ねたい作品を選べます。ガイドのある作品は設置場所の一覧へ、それ以外は絞り込み済みの地図へ進みます。</p><div class="cw-work-grid">{"".join(cards)}</div>
    </section>
    <section class="cw-section" id="by-prefecture" aria-labelledby="cross-heading">
      <p class="cw-eyebrow">WHERE TO FIND</p><h2 id="cross-heading">都道府県別の作品早見表</h2>
      <p>訪ねる地域が決まっているときに、その県で何の作品が何枚見られるかを確認できます。作品名から各ガイドへ進めます。</p>
      {cross_table_html}
    </section>
    <section class="cw-section cw-index-guide" aria-labelledby="guide-heading">
      <p class="cw-eyebrow">EXPLORE MORE</p><h2 id="guide-heading">地域や地図から探す</h2>
      <p>市町村・住所まで含めて通しで読む場合は全国一覧へ。現在地から絞り込む場合は地図が便利です。</p>
      <div class="cw-actions"><a class="cw-button cw-button-secondary" href="{INDEX_ASSET_BASE}character_manholes.html">全国一覧を見る →</a><a class="cw-button cw-button-secondary" href="{INDEX_ASSET_BASE}gmanhole_map.html">全国地図を開く →</a></div>
    </section>
    <section class="cw-section" aria-labelledby="notes-heading"><h2 id="notes-heading">訪問前に確認したいこと</h2>
      <p>掲載データは全国すべてを網羅するものではありません。移設・撤去、施設の開放時間、マンホールカードの配布状況は、訪問前に各ページの出典をご確認ください。</p>
    </section>
  </main>
</body></html>"""


def write_pages(records: list[dict], events: dict, output: Path,
                gundam_records: list[dict] | None = None) -> list[Path]:
    active = [r for r in records if _is_active(r)]
    pages = available_pages(active)
    written = []
    index_path = output / "characters/index.html"
    if pages:
        index_path.parent.mkdir(parents=True, exist_ok=True)
        index_path.write_text(generate_index_html(active, gundam_records), encoding="utf-8")
        written.append(index_path)
    elif index_path.exists():
        index_path.unlink()
    for page in WORK_PAGES:
        path = output / page.path / "index.html"
        if page not in pages:
            if path.exists():
                path.unlink()  # 再ビルド時に空になった作品の古い生成物を残さない
            continue
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(generate_html(page, active, events, related=tuple(pages)), encoding="utf-8")
        written.append(path)
    return written


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data", type=Path, default=ROOT / "docs/character_manholes.ndjson")
    parser.add_argument("--events", type=Path, default=DEFAULT_EVENTS)
    parser.add_argument("--gundam", type=Path, default=DEFAULT_GUNDAM)
    parser.add_argument("--output", type=Path, default=ROOT / "dist")
    args = parser.parse_args()
    records = load_ndjson(args.data)
    if not any(_is_active(r) for r in records):
        parser.error("No active character records; refusing to generate empty guides")
    written = write_pages(records, load_events(args.events), args.output,
                          gundam_records=load_ndjson(args.gundam))
    print(f"[generate_character_work_pages] wrote {len(written)} character pages")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
