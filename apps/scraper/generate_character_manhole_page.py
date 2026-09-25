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
import math
import random
from collections import Counter, defaultdict
from datetime import date, datetime
from pathlib import Path
from urllib.parse import parse_qs, quote, urlparse
from html import escape

try:
    from apps.scraper.photo_caption import (
        JST,
        caption_meta,
        format_display_name,
        format_photo_date,
        poster_profile_url,
    )
except ModuleNotFoundError as exc:
    if exc.name != "apps":
        raise
    from photo_caption import (
        JST,
        caption_meta,
        format_display_name,
        format_photo_date,
        poster_profile_url,
    )

try:
    from apps.scraper.character_manhole_works import (
        GUNDAM_MARKER_COLOR, GUNDAM_MARKER_LABEL, GUNDAM_WORK, GUNDAM_WORK_NAME, GUNDAM_WORK_QUERY, page_for_work,
    )
    from apps.scraper.prefectures import PREFECTURE_ORDER
except ModuleNotFoundError as exc:
    if exc.name != "apps":
        raise
    from character_manhole_works import (
        GUNDAM_MARKER_COLOR, GUNDAM_MARKER_LABEL, GUNDAM_WORK, GUNDAM_WORK_NAME, GUNDAM_WORK_QUERY, page_for_work,
    )
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
# None（=未記録）のレコードは許容する（プラン参照: キャラクターマンホール115件中100件はNone）。
REMOVED_INSTALLATION_STATUSES = {"removed", "not_installed", "uninstalled", "scheduled_removal"}

# ガンダムマンホールは "work" を持たない独立データセットなので、作品カードには
# 合成エントリとして差し込む（定義は character_manhole_works.py に集約）。
GUNDAM_PAGE = page_for_work(GUNDAM_WORK)

LATEST_POSTS_LIMIT = 4

# ヒーローセクションの写真モザイク用。デザインマンホール投稿のうち
# canonical_ref / nearby_refs がこのプレフィックスで始まる参照を持つものは
# 「キャラクターマンホールと確認できる投稿」として優先枠に入れる。
CHARACTER_LINKAGE_PREFIXES = ("gundam:", "character:")
HERO_MOSAIC_LIMIT = 6
WORK_CARD_CHARACTER_LIMIT = 3

FAQ_ITEMS: list[tuple[str, str]] = [
    (
        "アニメ・キャラクターマンホールの設置場所はどこで探せますか？",
        "このページの作品別一覧と都道府県別の設置場所一覧から探せます。"
        "地図では作品や都道府県で絞り込めます。訪問前には各設置場所の出典で最新の案内を確認してください。",
    ),
    (
        "全国すべてのキャラクターマンホールが載っていますか？",
        "いいえ。掲載データに収録しているマンホールの一覧で、全国すべてを網羅しているわけではありません。"
        "アニメ・漫画のほかゲームなどのキャラクターも含みます。ポケモンのマンホール「ポケふた」は別の図鑑・地図で紹介しています。",
    ),
    (
        "マンホールカードの配布場所も同じですか？",
        "この一覧はマンホール本体の設置場所を紹介しています。カードの有無・配布場所・在庫を示すものではありません。"
        "マンホールカードを集める場合は、訪問前に自治体や配布施設の案内を別途確認してください。",
    ),
    (
        "ポケふた以外の蓋でも投稿していいんですか？",
        "はい。むしろそれを集めています。ポケふたはこのサイトの図鑑側で網羅しているので、"
        "写真館で待っているのは「ポケふた以外の、あなたが見つけた蓋」のほうです。",
    ),
    (
        "キャラクターものじゃないんですが",
        "問題ありません。花や名所、マスコット、古い市町村名の蓋も歓迎です。"
        "デザインが入っていれば対象になります。",
    ),
    (
        "同じ蓋がもう載っていたら？",
        "そのまま投稿してください。撮った日も角度も違えば別の記録になりますし、"
        "近い座標のものは自動で紐づきます。",
    ),
    (
        "位置情報のない写真は使えますか？",
        # design_manhole.html の同種FAQ（GPS必須／撮影時にオンにする）と事実を揃えてある。
        "いいえ、投稿できません。設置場所を正確に記録するため、位置情報（GPS）付きの写真が必要です。"
        "スマホのカメラの位置情報記録をオンにして撮影したものをご利用ください。",
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
    """作品別の件数降順サマリ（キャラクターマンホールの work ごと + ガンダムを1エントリとして合成）。"""
    groups: dict[str, dict] = {}
    for record in character_records:
        work = str(record.get("work") or "").strip()
        if not work:
            continue
        page = page_for_work(work)
        key = page.slug if page else work
        group = groups.setdefault(key, {
            "name": page.name if page else work,
            "page": page,
            "records": [],
        })
        group["records"].append(record)

    summaries: list[dict] = []
    for group in groups.values():
        work = group["name"]
        page = group["page"]
        records = group["records"]
        prefectures = sorted(
            {record.get("prefecture") for record in records if record.get("prefecture")},
            key=lambda pref: PREFECTURE_ORDER.index(pref) if pref in PREFECTURE_ORDER else 999,
        )
        color = next((record.get("marker_color") for record in records if record.get("marker_color")), "")
        label = next((record.get("marker_label") for record in records if record.get("marker_label")), work[:1])
        characters: list[str] = []
        for record in records:
            name = str(record.get("character") or "").strip()
            if name and name not in characters:
                characters.append(name)
        summaries.append({
            "characters": characters,
            "work": work,
            "count": len(records),
            "prefectures": prefectures,
            "color": color or "#6C5CA6",
            "label": label,
            "query": page.map_query if page else work,
            "path": page.path if page else "",
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
            "path": GUNDAM_PAGE.path if GUNDAM_PAGE else "",
            "characters": [],
        })

    return sorted(summaries, key=lambda summary: (-summary["count"], summary["work"]))


def build_prefecture_summaries(character_records: list[dict], gundam_records: list[dict]) -> list[dict]:
    """都道府県別の件数降順サマリ（キャラクターマンホール＋ガンダム蓋の合算）。"""
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


def _has_character_linkage(record: dict) -> bool:
    """canonical_ref または nearby_refs に gundam:/character: 参照を持つか。"""
    canonical_ref = str(record.get("canonical_ref") or "")
    if canonical_ref.startswith(CHARACTER_LINKAGE_PREFIXES):
        return True
    nearby_refs = record.get("nearby_refs")
    if isinstance(nearby_refs, list):
        for entry in nearby_refs:
            if not isinstance(entry, dict):
                continue
            ref = str(entry.get("ref") or "")
            if ref.startswith(CHARACTER_LINKAGE_PREFIXES):
                return True
    return False


def _is_small_photo_url(url: str) -> bool:
    """?size=small のみ許可する。

    size=medium/size=large は API 側で実装がなく、307 で ~2MB の原寸 JPEG に
    リダイレクトされる（size 未指定も同様に原寸へ落ちる可能性がある）。
    ヒーローモザイクは複数枚を初期表示に並べるため、size=small だと
    確認できないものは安全側で除外する。
    """
    try:
        query = parse_qs(urlparse(url).query)
    except ValueError:
        return False
    return query.get("size") == ["small"]


def build_hero_mosaic(
    path: Path,
    limit: int = HERO_MOSAIC_LIMIT,
    *,
    seed_date: date | None = None,
) -> list[dict]:
    """ヒーローセクション用の写真モザイクを、実際の投稿からランダムに選ぶ。

    g-manhole.net の画像やキャラクターマンホールNDJSON自体には使ってよい写真が無いため
    （他者サイトのホットリンクになる／画像フィールドが無い）、写真は
    docs/design_manholes.ndjson のサイト運営者自身の投稿からのみ使う。

    canonical_ref または nearby_refs でキャラクターマンホールと確認できる投稿
    （gundam:/character: 参照）を優先枠に入れ、残りをその他のアクティブな
    写真付き投稿で埋める。並びは JST の日付でシードした乱数で、優先度の
    階層内だけシャッフルする（index.html の HEROES 日替わりローテーションと
    同じ「毎日ビルドすれば毎日変わる」idiom）。
    """
    records = [
        record for record in load_ndjson(path)
        if record.get("status") == "active"
        and _is_small_photo_url(str(record.get("photo_url") or ""))
    ]
    if not records:
        return []

    priority: list[dict] = []
    others: list[dict] = []
    for record in records:
        (priority if _has_character_linkage(record) else others).append(record)

    if seed_date is None:
        seed_date = datetime.now(JST).date()
    rng = random.Random(seed_date.isoformat())
    rng.shuffle(priority)
    rng.shuffle(others)

    selected = (priority + others)[:limit]

    posts: list[dict] = []
    for record in selected:
        location = "".join(
            part for part in (record.get("prefecture", ""), record.get("city", "")) if part
        )
        posts.append({
            "title": str(record.get("title") or "デザインマンホール").strip(),
            "photo_url": str(record.get("photo_url", "")),
            "location": location,
        })
    return posts


def build_mini_map_pins(character_records: list[dict], gundam_records: list[dict]) -> list[list[float]]:
    """地図ゲートウェイの非操作ミニ地図（index.html の #mini-map と同方式）に焼き込む
    ピン座標。件数が169件程度と少ないため全件をそのままビルド時にJSONへ埋め込む
    （index.html の #mini-map のように pokefuta.ndjson をクライアント側 fetch する
    方式ではなく、このLPはビルド時確定なのでここも確定値にする）。
    """
    pins: list[list[float]] = []
    for record in (*character_records, *gundam_records):
        lat = record.get("lat")
        lng = record.get("lng")
        if not isinstance(lat, (int, float)) or not isinstance(lng, (int, float)):
            continue
        if isinstance(lat, bool) or isinstance(lng, bool):  # bool は int のサブクラスなので明示的に除外
            continue
        pins.append([round(float(lat), 5), round(float(lng), 5)])
    return pins


STYLESHEET_HREF = "./assets/character-work.css?v=20260925a"

# 都道府県一覧を地方ごとに束ねる。PREFECTURE_ORDER（北→南）の区切り位置で持つ。
REGIONS: list[tuple[str, str, str]] = [
    ("北海道・東北", "北海道", "福島県"),
    ("関東", "茨城県", "神奈川県"),
    ("中部", "新潟県", "愛知県"),
    ("近畿", "三重県", "和歌山県"),
    ("中国・四国", "鳥取県", "高知県"),
    ("九州・沖縄", "福岡県", "沖縄県"),
]


def _region_of(prefecture: str) -> str:
    if prefecture not in PREFECTURE_ORDER:
        return "その他"
    index = PREFECTURE_ORDER.index(prefecture)
    for name, first, last in REGIONS:
        if PREFECTURE_ORDER.index(first) <= index <= PREFECTURE_ORDER.index(last):
            return name
    return "その他"


def _short_work_name(name: str) -> str:
    """早見表のチップ用。「機動戦士ガンダム（ガンダムマンホール）」の括弧書きを落とす。"""
    return name.split("（")[0]


def _lid_html(color: str, label: str, extra_class: str = "") -> str:
    classes = "cm-lid" + (f" {extra_class}" if extra_class else "")
    return (
        f'<span class="{classes}" style="--c:{escape(color)}" aria-hidden="true">'
        f'{escape(str(label)[:1])}</span>'
    )


def _work_card_html(summary: dict) -> str:
    pref_text = "・".join(summary["prefectures"][:3])
    if len(summary["prefectures"]) > 3:
        pref_text += f" ほか{len(summary['prefectures']) - 3}"
    href = _work_href(summary.get("path", ""), summary["query"])
    # キャラ名自体に「・」を含むものがある（例: まる子・友蔵）ので区切りは読点にする
    characters = summary.get("characters") or []
    character_text = "、".join(characters[:WORK_CARD_CHARACTER_LIMIT])
    if len(characters) > WORK_CARD_CHARACTER_LIMIT:
        character_text += f" ほか{len(characters) - WORK_CARD_CHARACTER_LIMIT}種"
    go_text = "設置場所ガイドへ →" if summary.get("path") else "地図で見る →"
    return (
        f'<li><a class="lp-work-card" href="{href}" style="--c:{escape(summary["color"])}">'
        + _lid_html(summary["color"], summary["label"])
        + f'<strong>{escape(summary["work"])}</strong>'
        f'<span class="lp-work-count"><b class="cm-num">{summary["count"]}</b>枚</span>'
        + (f'<small>{escape(pref_text)}</small>' if pref_text else '')
        + (f'<small class="lp-work-chars">{escape(character_text)}</small>' if character_text else '')
        + f'<span class="lp-work-go">{go_text}</span></a></li>'
    )


def _work_href(summary_path: str, query: str) -> str:
    return f"./{summary_path}" if summary_path else f"{MAP_HREF}?work={quote(query)}"


def _work_meta_for(record: dict, is_gundam: bool) -> dict:
    """1枚のレコードが属する作品の表示情報（作品カードと同じ束ね方・同じ色・同じリンク先）。"""
    if is_gundam:
        return {"key": GUNDAM_WORK_QUERY, "name": GUNDAM_WORK_NAME, "color": GUNDAM_MARKER_COLOR,
                "label": GUNDAM_MARKER_LABEL,
                "href": _work_href(GUNDAM_PAGE.path if GUNDAM_PAGE else "", GUNDAM_WORK_QUERY)}
    work = str(record.get("work") or "").strip() or "作品不明"
    page = page_for_work(work)
    name = page.name if page else work
    return {
        "key": page.slug if page else work,
        "name": name,
        "color": str(record.get("marker_color") or "#6C5CA6"),
        "label": str(record.get("marker_label") or name[:1]),
        "href": _work_href(page.path if page else "", work),
    }


def _location_item_html(record: dict, meta: dict, prefecture: str) -> str:
    city = str(record.get("city") or "")
    work = str(record.get("work") or meta["name"])
    name = str(record.get("title") or record.get("landmark") or record.get("character") or work)
    address = str(record.get("address") or record.get("landmark") or "詳細な住所は未記録")
    source = str(record.get("official_url") or record.get("source_url") or record.get("detail_url") or "")
    try:
        parsed = urlparse(source)
        safe_source = parsed.scheme in {"http", "https"} and bool(parsed.netloc)
    except ValueError:
        safe_source = False
    source_html = (
        f' · <a href="{escape(source)}" target="_blank" rel="noopener noreferrer">出典・設置案内</a>'
        if safe_source else ""
    )
    return (
        f'<li style="--c:{escape(meta["color"])}"><strong>{escape(name)}</strong>'
        f'<p>{escape(work)} ／ {escape(prefecture)}{escape(city)}</p>'
        f'<p>{escape(address)}{source_html}</p></li>'
    )


def _prefecture_directory_html(character_records: list[dict], gundam_records: list[dict]) -> str:
    """地方 → 都道府県 → 設置場所を1本の一覧にする。

    旧ページは「県ボタン」「都道府県×作品の早見表」「県ごとの設置場所一覧」を
    縦に3回並べていて、同じ県名を3回読ませていた。1県1行にまとめ、閉じた状態で
    作品の内訳（色の帯）と枚数、開くと作品別ガイドへのリンクと全設置場所が出る。
    設置場所は <details> の中でも静的HTMLなので、JSなしでもクロール・閲覧できる。
    """
    by_pref: dict[str, list[tuple[dict, dict]]] = defaultdict(list)
    for records, is_gundam in ((character_records, False), (gundam_records, True)):
        for record in records:
            prefecture = str(record.get("prefecture") or "").strip() or "都道府県未記録"
            by_pref[prefecture].append((record, _work_meta_for(record, is_gundam)))

    order = {name: index for index, name in enumerate(PREFECTURE_ORDER)}
    regions: dict[str, list[str]] = defaultdict(list)
    for prefecture in sorted(by_pref, key=lambda name: (order.get(name, 999), name)):
        regions[_region_of(prefecture)].append(prefecture)

    # 帯の長さは最多県との比。枚数差が大きい（最多66枚・最少1枚）ので平方根で縮め、1枚の県も見えるようにする
    max_total = max((len(items) for items in by_pref.values()), default=1)
    region_names = [name for name, _, _ in REGIONS] + ["その他"]
    blocks = []
    for region in region_names:
        prefectures = regions.get(region)
        if not prefectures:
            continue
        rows = []
        for prefecture in prefectures:
            items = by_pref[prefecture]
            works: dict[str, dict] = {}
            for _, meta in items:
                entry = works.setdefault(meta["key"], {**meta, "count": 0})
                entry["count"] += 1
            ordered = sorted(works.values(), key=lambda w: (-w["count"], w["name"]))
            total = len(items)
            bar = "".join(
                f'<i style="--c:{escape(w["color"])};width:{w["count"] / total * 100:.2f}%"></i>'
                for w in ordered
            )
            chips = "".join(
                f'<a href="{escape(w["href"])}" style="--c:{escape(w["color"])}">'
                + _lid_html(w["color"], w["label"])
                + f'{escape(_short_work_name(w["name"]))} <span>{w["count"]}</span></a>'
                for w in ordered
            )
            locations = "".join(
                _location_item_html(record, meta, prefecture)
                for record, meta in sorted(items, key=lambda item: (
                    str(item[0].get("city") or ""), item[1]["name"], str(item[0].get("id") or "")
                ))
            )
            map_link = (
                f'<a class="lp-pref-map" href="{MAP_HREF}?pref={quote(prefecture)}">{escape(prefecture)}の地図を見る →</a>'
                if prefecture in order else ""
            )
            rows.append(
                f'<details class="lp-pref" data-pref="{escape(prefecture)}">'
                f'<summary><span class="lp-pref-name">{escape(prefecture)}</span>'
                f'<span class="lp-pref-track" aria-hidden="true"><span class="lp-pref-bar" style="width:{math.sqrt(total / max_total) * 100:.1f}%">{bar}</span></span>'
                f'<span class="lp-pref-count"><span class="cm-num">{total}</span>枚</span></summary>'
                f'<div class="lp-pref-body"><div class="lp-cross-links">{chips}</div>{map_link}'
                f'<ul class="lp-location-list">{locations}</ul></div></details>'
            )
        region_total = sum(len(by_pref[p]) for p in prefectures)
        blocks.append(
            f'<div class="lp-region"><h3>{escape(region)}<small>{len(prefectures)}都道府県・{region_total}枚</small></h3>'
            + "".join(rows) + '</div>'
        )
    return '<div class="lp-regions">' + "".join(blocks) + '</div>'


def _hero_mosaic_item_html(post: dict) -> str:
    alt_text = f"{post['title']} {post['location']}".strip()
    # 元画像は 300×400 のポートレートだが、丸抜き（object-fit: cover）で表示するため
    # 属性は正方形の値にしておく（CLS防止）。ヒーローなので lazy にはしない。
    return (
        '<li class="lp-hero-mosaic-item">'
        f'<img src="{escape(post["photo_url"])}" alt="{escape(alt_text)}" '
        'width="300" height="300" decoding="async">'
        '</li>'
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
    hero_mosaic_posts = build_hero_mosaic(design_manhole_path)
    mini_map_pins = build_mini_map_pins(character_records, gundam_records)
    mini_map_pins_json = json.dumps(mini_map_pins)

    total_count = len(character_records) + len(gundam_records)
    work_count = len(work_summaries)
    pref_count = len(pref_summaries)

    title = f"アニメ・キャラクターマンホール全国一覧｜{total_count}枚の設置場所・地図"
    description = (
        f"全国{pref_count}都道府県・{work_count}作品、{total_count}枚のアニメ・キャラクターマンホールを一覧で紹介。"
        "ガンダムやゾンビランドサガなどを作品別・都道府県別に探し、市町村・設置場所・出典と地図を確認できます。"
        "ポケふた以外のデザインマンホールの写真投稿も受付中。"
    )

    work_items_html = "\n".join(_work_card_html(summary) for summary in work_summaries)
    prefecture_directory_html = _prefecture_directory_html(character_records, gundam_records)

    if hero_mosaic_posts:
        hero_mosaic_items_html = "\n".join(_hero_mosaic_item_html(post) for post in hero_mosaic_posts)
        hero_aside_html = f"""
      <div class="lp-hero-photos">
        <ul class="lp-hero-mosaic">
{hero_mosaic_items_html}
        </ul>
        <p class="lp-hero-mosaic-caption">写真はすべて、みんなが投稿した実物です</p>
      </div>"""
    else:
        hero_aside_html = ""

    if latest_posts:
        photo_items_html = "\n".join(_photo_card_html(post) for post in latest_posts)
        latest_section_html = f"""
    <section class="cm-section" aria-labelledby="lp-latest-heading">
      <div class="cm-section-head">
        <h2 id="lp-latest-heading"><span aria-hidden="true">LATEST POSTS</span>先に出してくれた人たち</h2>
        <a href="https://pokefuta.com/design-manholes" target="_blank" rel="noopener noreferrer">すべての投稿を見る →</a>
      </div>
      <p class="cm-lead">ポケふたを撮りに行った先で、ついでに撮られた蓋です。</p>
      <ul class="lp-photo-grid">
{photo_items_html}
      </ul>
    </section>"""
    else:
        latest_section_html = ""

    faq_html = "".join(
        f'<details><summary>{escape(question)}</summary><p>{escape(answer)}</p></details>'
        for question, answer in FAQ_ITEMS
    )

    json_ld_webpage = {
        "@type": "CollectionPage",
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
                "url": (f"{BASE_URL}{summary['path']}" if summary.get("path")
                        else f"{MAP_URL}?work={quote(summary['query'])}"),
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
  <link rel="stylesheet" href="{STYLESHEET_HREF}" />
  <link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css"
    integrity="sha256-p4NxAoJBhIIN+hmNHrzRCf9tD/miZyoHS5obTRR9BMY=" crossorigin="">
  <script src="./assets/session-badge.js" defer></script>
  <link rel="icon" href="./assets/pokefuta_icon_32.png" type="image/png" />
  <!-- Google Analytics -->
  <script src="/assets/analytics.js?v=20260805a"></script>
  <script>
    window.PokefutaAnalytics.init({{
      'page_path': '/character_manholes',
      site_type: 'map',
      page_type: 'lp_character_manholes',
    }});
  </script>
  <!-- End GA -->
</head>
<body class="character-manhole-lp cm-page">
  <!-- ===== APP BAR（ビルド時に inject_site_header.py が共通ヘッダーへ差し替える） ===== -->
  <header class="top-app-bar">
    <div class="top-app-bar-inner">
      <a class="top-brand" href="./" onclick="trackEvent('click_nav',{{surface:'site_nav',nav:'home',from:'character_manholes_lp'}})">
        <span class="brand-name">ポケふた図鑑</span>
      </a>
      <div class="top-nav-right">
        <nav class="top-nav" aria-label="メインナビ">
          <a class="top-nav-link" href="map.html" onclick="trackEvent('click_nav',{{surface:'site_nav',nav:'map',from:'character_manholes_lp'}})">マップ</a>
          <a class="top-nav-link" href="pokemon/" onclick="trackEvent('click_nav',{{surface:'site_nav',nav:'pokemon',from:'character_manholes_lp'}})">ポケモン</a>
          <a class="top-nav-link top-nav-link--active" href="character_manholes.html" aria-current="page">キャラふた</a>
          <a class="top-nav-link" data-login-link data-nav-target="login" data-stamp-page="https://pokefuta.com/" data-stamp-label="スタンプ帳" href="https://pokefuta.com/login?from=data" onclick="trackEvent('click_nav',{{surface:'site_nav',nav:this.dataset.navTarget,from:'character_manholes_lp'}})">ログイン</a>
        </nav>
      </div>
    </div>
  </header>

  <main class="cm-wrap">
    <section class="cm-hero" id="lp-intro" aria-labelledby="lp-h1">
      <div>
        <p class="cm-eyebrow">CHARACTER MANHOLE / キャラふた図鑑</p>
        <h1 id="lp-h1">アニメ・キャラクターマンホール<br>全国一覧・設置場所マップ</h1>
        <p class="cm-hero-lead">アニメ・漫画・ゲームのキャラクターが描かれた、ご当地マンホールの図鑑です。
          <b>作品から</b>でも<b>行き先の都道府県から</b>でも、設置場所・住所・出典・地図までたどれます。
          ポケモンのマンホールは<a href="./">ポケふた図鑑</a>へ。</p>
        <ul class="cm-stats" aria-label="掲載数">
          <li><strong class="cm-num">{total_count}</strong>枚</li>
          <li><strong class="cm-num">{work_count}</strong>作品</li>
          <li><strong class="cm-num">{pref_count}</strong>都道府県</li>
        </ul>
        <nav class="cm-jump" aria-label="このページの目次">
          <a class="cm-btn" href="#works">作品から探す</a>
          <a class="cm-btn cm-btn--ghost" href="#prefectures">都道府県から探す</a>
          <a class="cm-btn cm-btn--ghost" href="#lp-map-heading">地図で探す</a>
        </nav>
        <p class="cm-hero-note">掲載データ：{total_count}枚・{work_count}作品・{pref_count}都道府県。全国すべてを網羅するものではありません。</p>
      </div>{hero_aside_html}
    </section>

    <section class="cm-section" id="works" aria-labelledby="lp-works-heading">
      <div class="cm-section-head">
        <h2 id="lp-works-heading"><span aria-hidden="true">BY WORK</span>アニメ・キャラクターマンホールの作品別一覧</h2>
      </div>
      <p class="cm-lead">掲載中の{work_count}作品・シリーズを枚数の多い順に。作品を選ぶと、キャラクター・設置場所・住所・出典をまとめたガイドへ進みます。アイマスは各シリーズをまとめて1作品として数えています。</p>
      <ul class="lp-work-grid">
{work_items_html}
      </ul>
    </section>

    <section class="cm-section" id="prefectures" aria-labelledby="lp-pref-heading">
      <div class="cm-section-head">
        <h2 id="lp-pref-heading"><span aria-hidden="true">BY PREFECTURE</span>都道府県別の設置場所一覧</h2>
      </div>
      <p class="cm-lead">行き先の県を開くと、見られる作品とすべての設置場所・出典が出ます。色の帯はその県の作品の内訳です。掲載のない地域にも未収録のマンホールがある場合があります。移設・撤去や施設の開放時間は、訪問前に出典の案内をご確認ください。</p>
{prefecture_directory_html}
    </section>

    <section class="cm-section" aria-labelledby="lp-map-heading">
      <div class="cm-section-head">
        <h2 id="lp-map-heading"><span aria-hidden="true">MAP</span>地図で探す</h2>
      </div>
      <a class="map-gateway-card" href="{MAP_HREF}"
         onclick="trackEvent('click_map_cta',{{surface:'character_map_section',cta:'map_section',from:'character_manholes_lp'}})">
        <div id="cm-mini-map" class="map-gateway-minimap" aria-hidden="true"></div>
        <span class="map-gateway-badge">🗺 全国 <b>{total_count}</b>枚</span>
        <span class="map-gateway-attr">© OpenStreetMap contributors</span>
        <div class="map-gateway-overlay">
          <div class="map-gateway-title">アニメ・キャラクターマンホールの設置場所を探す</div>
          <div class="map-gateway-sub">作品・都道府県で絞り込み、現在地からも探せます</div>
          <div class="map-gateway-cta">🗺 地図を全画面で開く</div>
        </div>
      </a>
    </section>

    <!-- キャラクターマンホールとは（検索語のためh2は変更しない） -->
    <section class="cm-section" aria-labelledby="lp-about-heading">
      <div class="cm-section-head">
        <h2 id="lp-about-heading"><span aria-hidden="true">WHAT IS IT</span>キャラクターマンホールとは</h2>
      </div>
      <ul class="lp-explain-grid">
        <li class="lp-explain-card">
          <strong>その土地に行かないと踏めない蓋</strong>
          <p>自治体がアニメ・漫画・ご当地キャラの絵柄を入れて設置している蓋です。作品の舞台になった街や、作者の出身地に置かれていることが多く、その土地に行かないと踏めません。</p>
        </li>
        <li class="lp-explain-card">
          <strong>作品や自治体の枠を越えて探せる一覧</strong>
          <p>このページでは、作品ごと・自治体ごとに案内されている設置場所をまとめています。花・名所・市の鳥などの絵柄も含む<b>デザインマンホール</b>のうち、キャラクターを題材にした蓋を紹介しています。</p>
        </li>
      </ul>
      <p class="cm-lead">掲載データは手作業で出典を確認しながら追加しているため、「全国{total_count}枚」は<b>まだすべてを網羅した数ではありません</b>。</p>
    </section>

    <section class="cm-section" aria-labelledby="lp-post-heading">
      <div class="lp-promo">
        <div>
          <h2 id="lp-post-heading"><span aria-hidden="true">SUBMIT</span>その1枚、まだカメラロールにありますか？</h2>
          <p>撮ったときは「珍しいな」で終わった写真でも、場所と一緒に載せると、次に同じ街を歩く人の寄り道先になります。</p>
          <p><b>キャラクターものでなくても構いません。</b>花、名所、市の鳥、消防、旧市町村名の蓋——「これは撮っておくか」と思った理由があるなら、それで十分です。位置情報つきの写真なら、設置場所は自動で入ります。</p>
        </div>
        <div class="lp-promo-actions">
          <a class="cm-btn cm-btn--dark" href="{DESIGN_MANHOLE_HREF}"
             onclick="trackEvent('click_design_manhole_lp',{{surface:'character_cta',from:'character_manholes_lp'}})">📸 カメラロールの1枚を投稿する</a>
          <a class="cm-btn cm-btn--soft" href="https://pokefuta.com/design-manholes" target="_blank" rel="noopener noreferrer">みんなの投稿を見る →</a>
        </div>
      </div>
    </section>
{latest_section_html}

    <section class="cm-section" aria-labelledby="lp-faq-heading">
      <div class="cm-section-head">
        <h2 id="lp-faq-heading"><span aria-hidden="true">FAQ</span>よくある質問</h2>
      </div>
      <div class="cm-faq">
        {faq_html}
      </div>
    </section>

    <footer class="cm-footer" role="contentinfo">
      <a href="./">ポケふたマップ</a>/<a href="{MAP_HREF}">キャラクターマンホールマップ</a>/<a href="{DESIGN_MANHOLE_HREF}">デザインマンホール投稿</a>/<a href="./character_manholes.ndjson" target="_blank" rel="noopener">キャラNDJSON</a>/<a href="./gmanhole.ndjson" target="_blank" rel="noopener">ガンダムNDJSON</a>
    </footer>
  </main>

  <!-- ── 地図ゲートウェイの非操作ミニ地図（index.html の #mini-map と同じ実装方針）── -->
  <script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"
    integrity="sha256-20nQCchB9co0qIjJZRGuk2/Z9VM+kNiyxNV1lvTlZBo=" crossorigin=""></script>
  <script>
  (function() {{
    var miniMapEl = document.getElementById('cm-mini-map');
    if (!miniMapEl || typeof L === 'undefined') return;
    // このLPはビルド時確定なので、ピン座標はfetchせずJSONとして直接埋め込む
    var CM_MAP_PINS = {mini_map_pins_json};
    var miniMap = L.map('cm-mini-map', {{
      zoomControl: false, scrollWheelZoom: false, dragging: false,
      touchZoom: false, doubleClickZoom: false, boxZoom: false,
      keyboard: false, attributionControl: false,
    }});
    L.tileLayer('https://{{s}}.tile.openstreetmap.org/{{z}}/{{x}}/{{y}}.png', {{
      maxZoom: 19,
    }}).addTo(miniMap);
    CM_MAP_PINS.forEach(function(p) {{
      L.circleMarker([p[0], p[1]], {{
        radius: 4, color: '#fff', weight: 1, fillColor: '#6C5CA6', fillOpacity: 0.9,
      }}).addTo(miniMap);
    }});
    // 収録データは九州（全体の約6割）に強く偏るため、index.html の全国均等な
    // setView をそのまま使うと過半数のピンが画面外に出る。実データに合わせる。
    // 下側は .map-gateway-overlay のグラデーションが覆うぶん厚くpaddingを取り、
    // 最密の九州クラスタがオーバーレイの下に隠れないようにする。
    function fitToPins() {{
      if (CM_MAP_PINS.length) {{
        miniMap.fitBounds(CM_MAP_PINS, {{
          paddingTopLeft: [20, 20], paddingBottomRight: [20, 150], maxZoom: 8,
        }});
      }} else {{
        miniMap.setView([37.6, 137.5], 5);
      }}
    }}
    fitToPins();
    if (typeof IntersectionObserver !== 'undefined') {{
      new IntersectionObserver(function(entries, obs) {{
        if (entries[0].isIntersecting) {{ miniMap.invalidateSize(); fitToPins(); obs.disconnect(); }}
      }}, {{ threshold: 0.1 }}).observe(miniMapEl);
    }}
    window.addEventListener('resize', fitToPins);
  }})();
  </script>
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
