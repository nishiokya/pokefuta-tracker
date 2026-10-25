#!/usr/bin/env python3
"""Build the /characters/ index and static /characters/<slug>/ work guides."""

from __future__ import annotations

import argparse
import json
import math
import re
import sys
from collections import Counter, defaultdict
from datetime import datetime
from html import escape
from pathlib import Path
from urllib.parse import quote, urlencode, urlparse

try:
    from apps.scraper.character_manhole_works import (
        CHARACTER_CSS_VERSION, GUNDAM_WORK_QUERY, WORK_PAGES, WorkPage, available_pages, gundam_work_records,
    )
    from apps.scraper.generate_character_manhole_page import (
        BASE_URL, ROOT, _is_active, load_ndjson,
    )
    from apps.scraper.photo_caption import JST
    from apps.scraper.prefectures import PREFECTURE_ORDER, REGIONS
except ModuleNotFoundError as exc:
    if exc.name != "apps":
        raise
    from character_manhole_works import (
        CHARACTER_CSS_VERSION, GUNDAM_WORK_QUERY, WORK_PAGES, WorkPage, available_pages, gundam_work_records,
    )
    from generate_character_manhole_page import (
        BASE_URL, ROOT, _is_active, load_ndjson,
    )
    from photo_caption import JST
    from prefectures import PREFECTURE_ORDER, REGIONS

ASSET_BASE = "../../"
INDEX_ASSET_BASE = "../"
DEFAULT_EVENTS = ROOT / "dataset/character_manhole_events.json"
DEFAULT_GUNDAM = ROOT / "docs/gmanhole.ndjson"
DEFAULT_DESIGN_MANHOLES = ROOT / "docs/design_manholes.ndjson"
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


def attach_user_photos(records: list[dict], submissions: list[dict]) -> list[dict]:
    """Attach the newest linked public submission to each character record."""
    linked: dict[str, dict] = {}
    for submission in submissions:
        canonical_ref = str(submission.get("canonical_ref") or "")
        if (
            submission.get("status") != "active"
            or not canonical_ref.startswith("character:")
            or not safe_url(submission.get("photo_url"))
        ):
            continue
        current = linked.get(canonical_ref)
        if current is None or str(submission.get("created_at") or "") > str(
            current.get("created_at") or ""
        ):
            linked[canonical_ref] = submission

    enriched: list[dict] = []
    for record in records:
        item = dict(record)
        submission = linked.get(f"character:{record.get('id')}")
        if submission:
            item["user_photo_url"] = submission["photo_url"]
            item["user_photo_source_url"] = submission.get("source_url")
        enriched.append(item)
    return enriched


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
      <div><p class="cm-eyebrow">OFFICIAL SPOT CHECK-IN</p>
      <h2 id="check-in-heading">チェックイン企画の掲載期間は終了しました</h2>
      <p>公式掲載の期間は終了しています。新しい企画や現在の受付状況は、公式サイトの最新情報をご確認ください。</p>
      <p class="cw-deadline">公式掲載の終了日時：<time datetime="{escape(event['ends_at'])}">{deadline}</time></p>
      <p class="cw-note">確認日：{escape(str(event['verified_at']))}</p></div>
      <div class="cw-actions"><a class="cm-btn cm-btn--dark" href="{project_url}" target="_blank" rel="noopener noreferrer">公式プロジェクトの最新情報を見る ↗</a></div>
      <p class="cw-note">{source_links}</p>
    </section>"""
        return badge, html, active

    html = f"""<section class="cw-event" id="check-in" aria-labelledby="check-in-heading">
      <div><p class="cm-eyebrow">OFFICIAL SPOT CHECK-IN</p>
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
      <a class="cm-btn cm-btn--dark" href="{url}" target="_blank" rel="noopener noreferrer">公式でチェックイン方法を確認する ↗</a>
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
    # ガンダムは設置場所名がそのまま見出しになるので、同じ文字列を2行続けない
    location_html = "" if location == name else f'<p class="cw-location">{escape(location)}</p>'
    links = f'<a href="{escape(maps)}" target="_blank" rel="noopener noreferrer">{map_label} ↗</a>'
    if source:
        links += f'<a href="{escape(source)}" target="_blank" rel="noopener noreferrer">出典・設置案内 ↗</a>'
    if event_active and event and str(record["id"]) in event["spots"]:
        checkin = safe_url(event["url"].rstrip("/") + "/" + str(event["spots"][str(record["id"])]).lstrip("/"))
        links += f'<a href="{escape(checkin)}" target="_blank" rel="noopener noreferrer">公式スポット案内（ログインが必要）↗</a>'
    photo_url = safe_url(record.get("user_photo_url"))
    photo_source_url = safe_url(record.get("user_photo_source_url"))
    photo = ""
    if photo_url:
        image = (
            f'<img src="{escape(photo_url)}" alt="{escape(name)}のユーザー投稿写真" '
            'loading="lazy" decoding="async">'
        )
        if photo_source_url:
            image = (
                f'<a href="{escape(photo_source_url)}" target="_blank" '
                f'rel="noopener noreferrer">{image}</a>'
            )
        photo = f'<figure class="cw-spot-photo">{image}<figcaption>みんなの投稿写真</figcaption></figure>'
    return f"""<article class="cw-spot" id="{spot_id(record)}">
      {photo}
      <p class="cw-series">{escape(str(record.get('work') or ''))}</p>
      <h4>{escape(name)}</h4>{location_html}
      <p>{escape(address)}</p>{coordinate_note}<div class="cw-spot-links">{links}</div>
    </article>"""


def work_area(records: list[dict]) -> str:
    """設置場所が1つの市（区は市にまとめる）か1つの県に収まるなら、その名前。title に地名を入れる。"""
    prefs = {str(r.get("prefecture") or "") for r in records}
    if len(prefs) != 1 or "" in prefs:
        return ""  # 県がまたがる・不明なら、同名の市（北海道と福島の伊達市など）もあり得るので地名を出さない
    cities = {re.sub(r"^(.+?市).+区$", r"\1", str(r.get("city") or "")) for r in records}
    return cities.pop() if len(cities) == 1 and "" not in cities else prefs.pop()


def gundam_areas_html(groups: dict[tuple[str, str], list[dict]]) -> str:
    """ガンダムガイドの設置エリア。地方→都道府県→市町村（基数）だけを並べ、1基ずつの一覧はマップへ送る。"""
    by_pref: dict[str, list[tuple[str, int]]] = defaultdict(list)
    for (pref, city), rows in groups.items():
        by_pref[pref].append((city, len(rows)))
    counts = {n for cities in by_pref.values() for _, n in cities}
    # 掲載データでは市町村ごとに同じ数ずつ置かれている。そのときは1文で説明し、市町村ごとの「（2基）」は繰り返さない。
    # データが変わってそろわなくなったら、説明の文を出さず市町村ごとに基数を出す
    same_count = len(counts) == 1

    def city_label(city: str, n: int) -> str:
        name = city or "市町村未記録"
        return name if same_count else f"{name}（{n}基）"

    def pref_item(pref: str) -> str:
        heading = f'<strong>{escape(pref)}</strong> <small>{sum(n for _, n in by_pref[pref])}基</small>'
        # 都道府県が分からない行は地図の県絞り込みに渡せないので、リンクにしない
        if pref in PREFECTURE_ORDER:
            heading = f'<a href="{escape(map_href(GUNDAM_WORK_QUERY, pref))}">{heading}</a>'
        return f'<li>{heading}<span>{escape("・".join(city_label(city, n) for city, n in by_pref[pref]))}</span></li>'

    # 地方に属さない県名（都道府県未記録など）も件数には入っているので、黙って落とさず最後にまとめる
    known = {pref for _, prefs in REGIONS for pref in prefs}
    areas = [(region, [p for p in prefs if p in by_pref]) for region, prefs in REGIONS]
    areas.append(("地方未確認", [p for p in by_pref if p not in known]))
    sections = [
        f'<section class="cw-city"><h3>{escape(region)} <small>{len(present)}都道府県</small></h3>'
        f'<ul class="cw-areas">{"".join(pref_item(pref) for pref in present)}</ul></section>'
        for region, present in areas if present
    ]
    pair_note = (f'<p class="cm-lead">掲載データでは、どの市町村にも{next(iter(counts))}基ずつ設置されています。'
                 '同じ市町村の蓋をまとめて回る計画を立てやすい作品です。</p>') if same_count else ""
    return pair_note + "".join(sections)


def generate_html(page: WorkPage, records: list[dict], events: dict,
                  *, now: datetime | None = None, related: tuple[WorkPage, ...] = ()) -> str:
    selected = [r for r in records if _is_active(r) and r.get("work") in page.works]
    if not selected:
        raise ValueError(f"No active records for {page.slug}")
    now = now or datetime.now(JST)
    count = len(selected)
    pref_count = len({r.get("prefecture") for r in selected if r.get("prefecture")})
    area = work_area(selected)
    title = (f"{page.search_name}のマンホール一覧・地図｜{area}の設置場所マップ" if area
             else f"{page.search_name}のマンホール一覧・地図｜設置場所マップ")
    if page.slug == "idolmaster":
        title = "ふたマス一覧・設置場所マップ｜アイマスのマンホール写真と地図"
    if page.slug == "gundam":
        # 「ガンダムマンホール 一覧・地図」の検索は gmanhole_map.html が受ける（そちらの方が表示・順位とも上）。
        # 同じ語でこのページと取り合わないよう、こちらは巡り方のガイドとして名乗る
        title = "ガンダムマンホールの巡り方ガイド｜地方・都道府県別の設置エリア"
    description = f"{page.name}のマンホール{count}枚を掲載。{page.intro}"
    if page.slug == "idolmaster":
        description = (f"アイマスのマンホール『ふたマス!!!!!!』{count}枚・{pref_count}都道府県の設置場所を一覧と地図で紹介。"
                       "アイドル名・住所・現地写真から行き先を探せます。高槻やよい、前川みく、姫崎莉波などの設置案内と公式チェックイン方法も掲載。")
    if page.slug == "gundam":
        description = (f"ガンダムマンホール{count}基・{pref_count}都道府県を、地方・都道府県・市町村の設置エリアから紹介する巡り方ガイド。"
                       "設置場所の名前・住所・出典は全国の一覧・地図にまとめています。")
    canonical = BASE_URL + page.path
    event = event_for_page(page.slug, events)
    badge, event_section, event_active = event_html(event, now) if event else ("", "", False)
    hero_heading = "ふたマス一覧・設置場所マップ<br><small>アイマスのマンホールを探そう。</small>" if page.slug == "idolmaster" else f"{escape(page.name)}の<br>マンホールを探そう。"
    if page.slug == "gundam":
        hero_heading = "ガンダムマンホールを<br>巡る旅のガイド。"
    hero_note = "担当アイドルのふたを訪ねて、公式チェックインへ。" if event_active else "好きな作品を、次の旅の目的地に。"
    hero_cta = '<a class="cm-btn cm-btn--ghost" href="#check-in">チェックインの参加方法 →</a>' if event_active else ""
    # 全国一覧の作品カードと同じ色・同じ字の蓋を掲げ、2種類のページを同じ図鑑に見せる
    lid_color = next((str(r["marker_color"]) for r in selected if r.get("marker_color")), "#6C5CA6")
    lid_label = next((str(r["marker_label"]) for r in selected if r.get("marker_label")), page.name[:1])
    brand_counts = Counter(r["work"] for r in selected)
    brands_html = "".join(
        f'<a href="{escape(map_href(work if len(page.works) > 1 else page.map_query))}">{escape(work)} <span>{brand_counts[work]}枚 ↗</span></a>'
        for work in page.works if brand_counts[work]
    )
    pref_order = {pref: i for i, pref in enumerate(PREFECTURE_ORDER)}
    selected.sort(key=lambda r: (pref_order.get(r.get("prefecture"), 999), str(r.get("city") or ""), str(r["id"])))
    hero_photo = next((r for r in selected if safe_url(r.get("user_photo_url"))), None) if page.slug == "idolmaster" else None
    social_image = safe_url(hero_photo.get("user_photo_url")) if hero_photo else OG_IMAGE
    image_dimensions = '' if hero_photo else '<meta property="og:image:width" content="1200"><meta property="og:image:height" content="630">'
    hero_visual = f'''<aside class="cw-emblem" aria-label="掲載数"><span class="cm-lid cm-lid--lg" style="--c:{escape(lid_color)}" aria-hidden="true">{escape(lid_label[:1])}</span>
        <p class="cw-emblem-count"><strong class="cm-num">{count}</strong>枚 ・ {pref_count}都道府県</p></aside>'''
    image_alt = ""
    if hero_photo:
        name = str(hero_photo.get("character") or hero_photo.get("title") or "マンホール")
        place = str(hero_photo.get("prefecture") or "") + str(hero_photo.get("city") or "")
        image_alt = f"{place}に設置された{name}のふたマス（アイマスのマンホール）の投稿写真"
        hero_visual = f'''<figure class="cw-hero-photo"><a href="#{spot_id(hero_photo)}">
          <img src="{escape(social_image)}" alt="{escape(image_alt)}" width="640" height="640" fetchpriority="high" loading="eager" decoding="async"></a>
          <figcaption><strong>{escape(name)}のふたマス</strong><span>{escape(place)} · みんなの投稿写真</span><a href="#{spot_id(hero_photo)}">このマンホールの設置場所を見る →</a></figcaption></figure>'''
    index_html = "".join(
        f'<a href="#{spot_id(r)}"><strong>{escape(str(r.get("character") or r.get("title") or "マンホール"))}</strong>'
        f'<span>{escape(str(r.get("prefecture") or ""))} {escape(str(r.get("city") or ""))}</span></a>'
        for r in selected
    )
    # キャラから選ぶための目次なので、キャラ名の無い作品（ガンダム）では下の一覧の重複になる
    index_block = f'<div class="cw-index">{index_html}</div>' if any(r.get("character") for r in selected) else ""
    groups = defaultdict(list)
    for record in selected:
        groups[(str(record.get("prefecture") or "都道府県未記録"), str(record.get("city") or ""))].append(record)
    locations_html = "".join(
        f'<section class="cw-city"><h3>{escape(pref)} {escape(city)} <small>{len(rows)}枚</small></h3>'
        f'<div class="cw-spots">{"".join(spot_html(r, event, event_active) for r in rows)}</div></section>'
        for (pref, city), rows in groups.items()
    )
    locations_heading = ('ふたマス（アイマス）一覧・アイドル別の設置場所' if page.slug == 'idolmaster'
                         else escape(page.name) + 'のマンホール一覧')
    if page.slug == "gundam":
        # 1基ずつの一覧は gmanhole_map.html が持つ。ここでは地方→県→市町村の要約だけにして、
        # 「一覧・設置場所」の検索をマップと取り合わない
        locations_heading = "地方・都道府県別の設置エリア"
        locations_html = gundam_areas_html(groups)
    jump_label = {"idolmaster": "アイドル・設置場所を探す", "gundam": "設置エリアを見る"}.get(page.slug, "設置場所を探す")
    locations_cta = (f'<a class="cm-btn cm-btn--soft" href="{ASSET_BASE}gmanhole_map.html">全国の一覧・地図を見る →</a>'
                     if page.slug == "gundam" else
                     f'<a class="cm-btn cm-btn--soft" href="{escape(map_href(page.map_query))}">作品の全国地図を見る →</a>')
    related_html = "".join(f'<a href="../{other.slug}/">{escape("ふたマス（アイマス）の設置場所" if other.slug == "idolmaster" else other.name)}</a>' for other in related if other.slug != page.slug)
    faq = [
        (page.question, page.answer),
        ("掲載されているマンホールがすべてですか？", "掲載データに収録した設置場所の一覧です。全国すべての設置状況を網羅するものではありません。移設・撤去や施設の開放時間は、訪問前に出典の案内をご確認ください。"),
    ]
    if page.slug == "gundam":
        # ガンダムのガイドは一覧ではなく設置エリアの要約なので、一覧の場所を案内する
        faq[1] = ("掲載されているマンホールがすべてですか？",
                  "このガイドは、掲載データに収録した設置場所を地方・都道府県・市町村ごとにまとめたものです。"
                  "1基ずつの名称・住所・出典は「ガンダムマンホール一覧・地図」に載せています。"
                  "全国すべての設置状況を網羅するものではありません。移設・撤去や施設の開放時間は、訪問前に出典の案内をご確認ください。")
    if page.slug == "idolmaster":
        faq.append(("フタマスとふたマスは同じものですか？", "フタマスと検索されることもありますが、公式名称は『ふたマス!!!!!!』です。"))
        places = "、".join(pref + city for pref, city in groups)
        faq.append(("ふたマス（アイマスのマンホール）はどこにありますか？",
                    f"このページでは{places}の設置場所を掲載しています。アイドル名から一覧へ進むと、住所と設置案内を確認できます。ページ内の地図には座標を確認できた場所を表示しています。"))
        faq.append(("ふたマスは何枚掲載されていますか？",
                    f"現在、この図鑑には設置済みの{count}枚・{pref_count}都道府県を掲載しています。全国の総設置数ではなく、このページの収録数です。最新の設置状況は公式プロジェクトと各自治体の案内をご確認ください。"))
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
    if hero_photo:
        schema["@graph"][0]["primaryImageOfPage"] = {"@type": "ImageObject", "url": social_image, "caption": image_alt}
    if page.slug == "idolmaster":
        for item, record in zip(schema["@graph"][2]["itemListElement"], selected):
            place = {"@type": "Place", "name": str(record.get("character") or record.get("title")) + "のふたマス",
                     "url": item["url"], "address": str(record.get("address") or "")}
            if has_coordinates(record):
                place["geo"] = {"@type": "GeoCoordinates", "latitude": record["lat"], "longitude": record["lng"]}
            if safe_url(record.get("user_photo_url")):
                place["image"] = safe_url(record["user_photo_url"])
            item["item"] = place
    if page.slug == "gundam":
        # 1基ずつの一覧を持たないので CollectionPage / ItemList にしない（一覧はマップ側）
        schema = {"@context": "https://schema.org", "@graph": [
            {"@type": "WebPage", "@id": canonical, "url": canonical, "name": title, "description": description, "inLanguage": "ja",
             "about": {"@type": "Thing", "name": "ガンダムマンホール"},
             "relatedLink": BASE_URL + "gmanhole_map.html"},
            {"@type": "BreadcrumbList", "itemListElement": [
                {"@type": "ListItem", "position": 1, "name": "ポケふた図鑑", "item": BASE_URL},
                {"@type": "ListItem", "position": 2, "name": "キャラクターマンホール全国一覧", "item": BASE_URL + "character_manholes.html"},
                {"@type": "ListItem", "position": 3, "name": page.name, "item": canonical},
            ]},
        ]}
    analytics = {"page_path": "/" + page.path, "site_type": "map", "page_type": "lp_character_work", "work": page.slug}
    map_count = sum(has_coordinates(r) for r in selected)
    map_note = f"地図のピンは座標確認済みの{map_count}枚。" if map_count != count else ""
    map_section = map_assets = map_cta = ""
    if page.slug == "gundam":
        map_cta = f'<a class="cm-btn cm-btn--ghost" href="{ASSET_BASE}gmanhole_map.html">ガンダムマンホール一覧・地図 →</a>'
    # 「〜 マンホール 地図／マップ」で検索されるので、ページ内に設置場所の地図を置く。
    # ガンダムは1基ずつの地図・一覧を gmanhole_map.html が持つので置かない
    if page.slug != "gundam" and map_count:
        idolmaster = page.slug == "idolmaster"
        label = "ふたマス" if idolmaster else f"{page.name}のマンホール"
        lead = (f"アイマスのマンホール{map_count}枚を地図に表示。ピンを選ぶとアイドル名と住所が開き、設置場所の詳しい案内へ進めます。"
                if idolmaster else
                f"{page.name}のマンホール{map_count}枚を地図に表示。ピンを選ぶと名前と住所が開き、下の設置場所の案内へ進めます。")
        map_cta = f'<a class="cm-btn cm-btn--ghost" href="#location-map">{escape(label)}の地図を見る ↓</a>'
        points = [{"lat": r["lat"], "lng": r["lng"], "name": str(r.get("character") or r.get("title") or "マンホール"),
                   "alt": str(r.get("character") or r.get("title") or "マンホール") + ("のふたマス" if idolmaster else f"（{page.name}のマンホール）"),
                   "photo_url": safe_url(r.get("user_photo_url")),
                   "address": str(r.get("address") or ""), "anchor": spot_id(r)} for r in selected if has_coordinates(r)]
        map_section = f'''<section class="cm-section" id="location-map" aria-labelledby="map-heading">
          <div class="cm-section-head"><h2 id="map-heading">{escape(label)}の設置場所マップ</h2><a class="cm-btn cm-btn--soft" href="{escape(map_href(page.map_query))}">大きな地図で見る →</a></div>
          <p class="cm-lead">{escape(lead)}{map_note}</p>
          <p id="cw-map-status" class="cw-note" role="status">地図を読み込み中です。表示されない場合は、下の設置場所一覧をご利用ください。</p>
          <div id="cw-map" class="cw-map" role="region" aria-label="{escape(label)}の設置場所の地図"></div>
          <noscript><p>地図の表示にはJavaScriptが必要です。<a href="#locations">{escape(label)}の設置場所一覧</a>から住所と地図リンクを確認できます。</p></noscript>
          <script type="application/json" id="cw-map-data">{json_script(points)}</script>
        </section>'''
        map_assets = f'''<link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css" integrity="sha256-p4NxAoJBhIIN+hmNHrzRCf9tD/miZyoHS5obTRR9BMY=" crossorigin="">
          <script defer src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js" integrity="sha256-20nQCchB9co0qIjJZRGuk2/Z9VM+kNiyxNV1lvTlZBo=" crossorigin=""></script>
          <script defer src="{ASSET_BASE}assets/character-work-map.js?v=20261025a"></script>'''
    return f"""<!doctype html>
<html lang="ja"><head>
  <meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{escape(title)}</title><meta name="description" content="{escape(description)}">
  <link rel="canonical" href="{canonical}"><meta name="robots" content="index,follow,max-image-preview:large">
  <meta property="og:type" content="website"><meta property="og:locale" content="ja_JP">
  <meta property="og:title" content="{escape(title)}"><meta property="og:description" content="{escape(description)}">
  <meta property="og:url" content="{canonical}"><meta property="og:site_name" content="ポケふた図鑑">
  <meta property="og:image" content="{escape(social_image)}">{image_dimensions}
  <meta property="og:image:alt" content="{escape(image_alt or title)}">
  <meta name="twitter:card" content="summary_large_image"><meta name="twitter:image" content="{escape(social_image)}">
  <link rel="icon" href="{ASSET_BASE}assets/pokefuta_icon_32.png">
  <link rel="stylesheet" href="{ASSET_BASE}assets/top-page.css?v=20260707a">
  <link rel="stylesheet" href="{ASSET_BASE}assets/character-work.css?v={CHARACTER_CSS_VERSION}">
  {map_assets}
  <script type="application/ld+json">{json_script(schema)}</script>
  <script src="{ASSET_BASE}assets/analytics.js?v=20261018a"></script>
  <script>window.PokefutaAnalytics.init({json_script(analytics)});</script>
</head><body class="character-work-page cm-page">
  <main class="cm-wrap">
    <nav class="cw-breadcrumb" aria-label="パンくず"><a href="{ASSET_BASE}">ポケふた図鑑</a><span>/</span><a href="{ASSET_BASE}character_manholes.html">キャラクターマンホール</a><span>/</span><span>{escape(page.name)}</span></nav>
    <section class="cm-hero{' cw-hero--photo' if hero_photo else ''}" aria-labelledby="work-heading">
      <div class="cw-hero-copy"><p class="cm-eyebrow">CHARACTER MANHOLE GUIDE / {escape(page.name)}</p>{badge}
        <h1 id="work-heading">{hero_heading}</h1><p class="cm-hero-lead">{hero_note}</p>
        <p>{escape(page.intro)}</p><div class="cm-jump"><a class="cm-btn" href="#locations">{jump_label} ↓</a>{map_cta}{hero_cta}</div>
        <p class="cm-hero-note">掲載 {count}枚 / {pref_count}都道府県　{map_note}</p>
      </div>
      {hero_visual}
    </section>
    {map_section}
    <section class="cm-section" id="locations" aria-labelledby="locations-heading">
      <div class="cm-section-head"><h2 id="locations-heading"><span aria-hidden="true">FIND YOUR FAVORITE</span>{locations_heading}</h2>
        {locations_cta}</div>
      <p class="cm-lead">{escape(page.guide)}</p>{index_block}
      {locations_html}
    </section>
    {event_section}
    <section class="cm-section" aria-labelledby="series-heading"><div class="cm-section-head"><h2 id="series-heading">シリーズ別に地図で探す</h2></div><div class="cw-brand-links">{brands_html}</div></section>
    <section class="cm-section" aria-labelledby="visit-heading"><div class="cm-section-head"><h2 id="visit-heading">訪問前に確認したいこと</h2></div>
      <p class="cm-lead">施設の開放時間・移設・撤去などは出典の案内をご確認ください。地図の座標には誤差がある場合があります。
      この一覧はマンホール本体の設置場所です。マンホールカードの配布場所・配布時間・在庫は自治体や配布施設の案内で別途ご確認ください。</p>
      <div class="cm-faq">{faq_html}</div></section>
    <section class="cm-section"><div class="lp-promo"><div><h2><span aria-hidden="true">YOUR TRAVEL NOTES</span>出会ったふたを、写真で残そう。</h2>
      <p>位置情報つきの写真を、ポケふた写真館に投稿できます。</p></div>
      <div class="lp-promo-actions"><a class="cm-btn cm-btn--dark" href="{ASSET_BASE}design_manhole.html">写真投稿の方法を見る →</a></div></div></section>
    <nav class="cm-section cw-related" aria-label="ほかの作品"><h2>ほかの作品も探す</h2>{related_html}<a href="{ASSET_BASE}character_manholes.html#works">すべての作品・全国一覧へ →</a></nav>
  </main>
</body></html>"""


def generate_index_html(records: list[dict]) -> str:
    """/characters/ は全国一覧の作品セクションへ転送するだけのページ。

    以前は作品カードと都道府県×作品の早見表を持つハブだったが、全国一覧と中身が
    二重になっていたので character_manholes.html に統合した。静的ホスティングで
    301 は出せないため、canonical + meta refresh + リンクで転送する。
    """
    active = [record for record in records if _is_active(record)]
    if not available_pages(active):
        raise ValueError("No character work pages available")
    target = INDEX_ASSET_BASE + "character_manholes.html#works"
    canonical = BASE_URL + "character_manholes.html"
    return f"""<!doctype html>
<html lang="ja"><head>
  <meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
  <title>キャラクターマンホール全国一覧へ移動しました</title>
  <link rel="canonical" href="{canonical}"><meta name="robots" content="noindex,follow">
  <meta http-equiv="refresh" content="0; url={target}">
</head><body>
  <p>作品別の一覧は <a href="{target}">キャラクターマンホール全国一覧</a> に統合しました。</p>
</body></html>"""


def write_pages(
    records: list[dict],
    events: dict,
    output: Path,
    design_submissions: list[dict] | None = None,
) -> list[Path]:
    active = [r for r in attach_user_photos(records, design_submissions or []) if _is_active(r)]
    pages = available_pages(active)
    written = []
    index_path = output / "characters/index.html"
    if pages:
        index_path.parent.mkdir(parents=True, exist_ok=True)
        index_path.write_text(generate_index_html(active), encoding="utf-8")
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
    parser.add_argument("--design-manholes", type=Path, default=DEFAULT_DESIGN_MANHOLES)
    parser.add_argument("--output", type=Path, default=ROOT / "dist")
    args = parser.parse_args()
    records = load_ndjson(args.data) + gundam_work_records(load_ndjson(args.gundam))
    if not any(_is_active(r) for r in records):
        parser.error("No active character records; refusing to generate empty guides")
    written = write_pages(
        records,
        load_events(args.events),
        args.output,
        design_submissions=load_ndjson(args.design_manholes),
    )
    print(f"[generate_character_work_pages] wrote {len(written)} character pages")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
