#!/usr/bin/env python3
"""Build useful, static work guides at /characters/<slug>/ from curated datasets."""

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
    from apps.scraper.generate_character_manhole_page import BASE_URL, ROOT, _is_active, load_ndjson
    from apps.scraper.photo_caption import JST
    from apps.scraper.prefectures import PREFECTURE_ORDER
except ModuleNotFoundError as exc:
    if exc.name != "apps":
        raise
    from character_manhole_works import WORK_PAGES, WorkPage, available_pages
    from generate_character_manhole_page import BASE_URL, ROOT, _is_active, load_ndjson
    from photo_caption import JST
    from prefectures import PREFECTURE_ORDER

ASSET_BASE = "../../"
DEFAULT_EVENTS = ROOT / "dataset/character_manhole_events.json"
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
      <p class="cw-note">確認日：{escape(event['verified_at'])}。開始日時はスポットごとに異なり、期間は変更される場合があります。最新条件は公式で確認してください。</p></div>
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
    event = validate_event(page.slug, events.get(page.slug)) if events.get(page.slug) else None
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
            {"@type": "ListItem", "position": 3, "name": page.name, "item": canonical},
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
  <link rel="stylesheet" href="{ASSET_BASE}assets/character-work.css?v=20260920a">
  <script type="application/ld+json">{json_script(schema)}</script>
  <script src="{ASSET_BASE}assets/analytics.js?v=20260805a"></script>
  <script>window.PokefutaAnalytics.init({json_script(analytics)});</script>
</head><body class="character-work-page">
  <main class="cw-wrap">
    <nav class="cw-breadcrumb" aria-label="パンくず"><a href="{ASSET_BASE}">ポケふた図鑑</a><span>/</span><a href="{ASSET_BASE}character_manholes.html">キャラクターマンホール</a><span>/</span><span>{escape(page.name)}</span></nav>
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
    <nav class="cw-section cw-related" aria-label="ほかの作品"><h2>ほかの作品も探す</h2>{related_html}<a href="{ASSET_BASE}character_manholes.html">キャラクターマンホール全国一覧へ →</a></nav>
  </main>
</body></html>"""


def write_pages(records: list[dict], events: dict, output: Path) -> list[Path]:
    active = [r for r in records if _is_active(r)]
    pages = available_pages(active)
    written = []
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
    parser.add_argument("--output", type=Path, default=ROOT / "dist")
    args = parser.parse_args()
    records = load_ndjson(args.data)
    if not any(_is_active(r) for r in records):
        parser.error("No active character records; refusing to generate empty guides")
    written = write_pages(records, load_events(args.events), args.output)
    print(f"[generate_character_work_pages] wrote {len(written)} work guides")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
