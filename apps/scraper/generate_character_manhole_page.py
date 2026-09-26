#!/usr/bin/env python3
"""Generate /character_manholes.html — the national directory of character manholes.

`gmanhole_map.html` is a full-screen Leaflet map with no crawlable body text. This
page bakes the work / prefecture / city / place breakdown (from
docs/character_manholes.ndjson + docs/gmanhole.ndjson) into static HTML so that
searches such as "<作品名> マンホール", "<都道府県> キャラクターマンホール" or
"<キャラクター名> マンホール" land on readable place names.

Real manhole photos posted to ポケふた写真館 (docs/design_manholes.ndjson) are shown
alongside that text: a hero mosaic (loaded on first view) and a lazy-loaded gallery.
Only pokefuta.com `?size=small` photo URLs are embedded, and a photo is captioned as a
character manhole only when it references a listed one. No map library or tiles are
loaded; the map is one link away. Counts are always aggregated from the datasets at
generation time — never hardcoded in the HTML — and the same values feed the body
text and JSON-LD.
"""

from __future__ import annotations

import argparse
import json
import logging
import random
import re
from collections import Counter, defaultdict
from datetime import date, datetime
from pathlib import Path
from urllib.parse import parse_qs, quote, urlparse
from html import escape

try:
    from apps.scraper.photo_caption import JST, format_photo_date
except ModuleNotFoundError as exc:
    if exc.name != "apps":
        raise
    from photo_caption import JST, format_photo_date

try:
    from apps.scraper.character_manhole_works import (
        CHARACTER_CSS_VERSION, GUNDAM_MARKER_COLOR, GUNDAM_MARKER_LABEL, GUNDAM_WORK, GUNDAM_WORK_NAME,
        GUNDAM_WORK_QUERY, page_for_work,
    )
    from apps.scraper.prefectures import PREFECTURE_ORDER, PREFECTURE_SLUGS
except ModuleNotFoundError as exc:
    if exc.name != "apps":
        raise
    from character_manhole_works import (
        CHARACTER_CSS_VERSION, GUNDAM_MARKER_COLOR, GUNDAM_MARKER_LABEL, GUNDAM_WORK, GUNDAM_WORK_NAME,
        GUNDAM_WORK_QUERY, page_for_work,
    )
    from prefectures import PREFECTURE_ORDER, PREFECTURE_SLUGS

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
MAP_HREF = "./gmanhole_map.html"                  # ページ内ナビは他ページ同様に相対パス
DESIGN_MANHOLE_HREF = "./design_manhole.html"      # 同上（ローカル配信でも同一オリジンに留まる）
OG_IMAGE = f"{BASE_URL}assets/ogp/pokefuta_map_ogp.png"
STYLESHEET_HREF = f"./assets/character-work.css?v={CHARACTER_CSS_VERSION}"
DESIGN_MANHOLES_LIST_URL = "https://pokefuta.com/design-manholes?from=data"

# 写真。docs/design_manholes.ndjson（ポケふた写真館の投稿）の size=small だけを使う。
CHARACTER_LINKAGE_PREFIXES = ("gundam:", "character:")
HERO_PHOTO_LIMIT = 8
GALLERY_PHOTO_LIMIT = 12
PHOTO_BOX = 300  # size=small は 300×400。枠は正方形で予約する
UNLINKED_PHOTO_LABEL = "投稿されたデザインマンホール"
PHOTO_HOST = "pokefuta.com"
PHOTO_PATH_RE = re.compile(r"/api/design-manholes/[A-Za-z0-9-]+/photo")
DESIGN_PAGE_PATH_RE = re.compile(r"/design-manholes/[A-Za-z0-9-]+")

# 明示的に撤去・未設置と分かっているものだけ除外する。installation_status が
# None（=未記録）のレコードは許容する（プラン参照: キャラクターマンホール115件中100件はNone）。
REMOVED_INSTALLATION_STATUSES = {"removed", "not_installed", "uninstalled", "scheduled_removal"}

# ガンダムマンホールは "work" を持たない独立データセットなので、作品カードには
# 合成エントリとして差し込む（定義は character_manhole_works.py に集約）。
GUNDAM_PAGE = page_for_work(GUNDAM_WORK)

WORK_CARD_CHARACTER_LIMIT = 3
WORK_CARD_PREFECTURE_LIMIT = 3
PREF_ROW_WORK_LIMIT = 3
FEATURED_PLACES_PER_PREFECTURE = 3
MAJOR_PREFECTURE_MIN = 5  # これ未満の県は設置場所名を1行にまとめて全部見せる

# 画面とJSON-LDの両方に出す固定のFAQ。件数に依存する質問は build_faq_items() が前に足す。
FAQ_ITEMS: list[tuple[str, str]] = [
    (
        "アニメ・キャラクターマンホールの設置場所はどこで探せますか？",
        "このページの作品別・都道府県別の一覧と、全国の主な設置場所から探せます。"
        "設置場所名や市町村名での絞り込みと、作品や都道府県で絞り込める地図も用意しています。"
        "訪問前には各設置場所の出典で最新の案内を確認してください。",
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
        "見つけたマンホールの写真を投稿できますか？",
        # design_manhole.html の同種FAQ（GPS必須／撮影時にオンにする）と事実を揃えてある。
        "はい。ポケふた以外のデザインマンホールの写真を募集しています。"
        "設置場所を正確に記録するため、位置情報（GPS）付きの写真が必要です。",
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


def _main_prefectures(counts: Counter) -> list[tuple[str, int]]:
    """枚数の多い順（同数は北から）の (都道府県, 枚数)。"""
    order = {name: index for index, name in enumerate(PREFECTURE_ORDER)}
    return sorted(counts.items(), key=lambda pair: (-pair[1], order.get(pair[0], 999)))


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
        pref_counts = Counter(record.get("prefecture") for record in records if record.get("prefecture"))
        summaries.append({
            "main_prefectures": _main_prefectures(pref_counts),
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
            "main_prefectures": _main_prefectures(
                Counter(record.get("prefecture") for record in gundam_records if record.get("prefecture"))
            ),
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


def _summary_key(summary: dict) -> str:
    """作品サマリーを _work_meta_for と同じキー（作品ページの slug・ガンダム・作品名）に揃える。"""
    if summary["query"] == GUNDAM_WORK_QUERY:
        return GUNDAM_WORK_QUERY
    return summary["path"].split("/")[1] if summary.get("path") else summary["query"]


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
    # 本文（主な設置場所・1行の一覧）はランドマーク名とキャラ名で出すので、
    # 絞り込み（li のテキストを検索）で見つかるよう、ここにも必ず載せる
    landmark = str(record.get("landmark") or "").strip()
    character = str(record.get("character") or "").strip()
    work_line = work + (f"・{character}" if character and character not in name and character != work else "")
    landmark_html = (f'<p>設置場所：{escape(landmark)}</p>'
                     if landmark and landmark not in name and landmark not in address else "")
    return (
        f'<li style="--c:{escape(meta["color"])}"><strong>{escape(name)}</strong>'
        f'<p>{escape(work_line)} ／ {escape(prefecture)}{escape(city)}</p>{landmark_html}'
        f'<p>{escape(address)}{source_html}</p></li>'
    )


def _is_small_photo_url(url: str) -> bool:
    """ポケふた写真館の縮小画像 `https://pokefuta.com/api/design-manholes/<id>/photo?size=small` だけ許可する。

    - ホストとパスまで確かめる。?size=small だけで判定すると、投稿データ経由で
      外部ドメインの画像（トラッキングピクセル等）を埋め込めてしまう
    - size=medium/size=large は API 側で実装がなく、307 で ~2MB の原寸 JPEG に
      リダイレクトされる（size 未指定も同様に原寸へ落ちる可能性がある）
    """
    try:
        parsed = urlparse(url)
        query = parse_qs(parsed.query)
    except ValueError:
        return False
    return (
        parsed.scheme == "https"
        and parsed.netloc == PHOTO_HOST
        and PHOTO_PATH_RE.fullmatch(parsed.path) is not None
        and query == {"size": ["small"]}
    )


def _is_design_manhole_page(url: str) -> bool:
    """写真のリンク先に使ってよい、写真館の詳細ページ `https://pokefuta.com/design-manholes/<id>` か。"""
    try:
        parsed = urlparse(url)
    except ValueError:
        return False
    return (parsed.scheme == "https" and parsed.netloc == PHOTO_HOST
            and DESIGN_PAGE_PATH_RE.fullmatch(parsed.path) is not None and not parsed.query)


def _linked_ref(record: dict) -> str:
    """canonical_ref → nearby_refs の順に、gundam:/character: の参照を1つ返す（無ければ空）。"""
    refs = [str(record.get("canonical_ref") or "")]
    for entry in record.get("nearby_refs") or []:
        if isinstance(entry, dict):
            refs.append(str(entry.get("ref") or ""))
    return next((ref for ref in refs if ref.startswith(CHARACTER_LINKAGE_PREFIXES)), "")


def _with_from_data(url: str) -> str:
    """pokefuta.com への導線には from=data だけを付ける（AGENTS.md の計測ルール）。"""
    parsed = urlparse(url)
    if parsed.netloc != "pokefuta.com" or "from=" in parsed.query:
        return url
    return url + ("&" if parsed.query else "?") + "from=data"


def build_photos(path: Path | None, character_records: list[dict], gundam_records: list[dict]) -> list[dict]:
    """design_manholes.ndjson の写真を、キャラクターマンホールとの対応つきで返す。

    写真はポケふた写真館への投稿（サイト運営者・利用者が撮った実物）だけを使い、他サイトの画像は使わない。
    gundam:/character: 参照が掲載中のマンホールを指すものだけ「キャラクターマンホールの写真」として
    作品名・設置場所を出す。それ以外は「投稿されたデザインマンホール」と明記し、誤認させない。
    """
    if path is None:
        return []
    targets = {f"character:{r.get('id')}": (r, False) for r in character_records}
    targets.update({f"gundam:{r.get('id')}": (r, True) for r in gundam_records})
    photos = []
    for record in load_ndjson(path):
        url = str(record.get("photo_url") or "")
        if record.get("status") != "active" or not _is_small_photo_url(url):
            continue
        title = str(record.get("title") or "デザインマンホール").strip()
        photo = {
            "id": str(record.get("id") or url),
            "photo_url": url,
            "created_at": str(record.get("created_at") or ""),
            "date": format_photo_date(record.get("created_at")),
        }
        target = targets.get(_linked_ref(record))
        if target:
            manhole, is_gundam = target
            meta = _work_meta_for(manhole, is_gundam)
            place = str(manhole.get("landmark") or manhole.get("title") or title).strip()
            href = meta["href"]
            if href.startswith("./characters/"):
                href += "#spot-" + quote(str(manhole.get("id")), safe="")
            label = _short_work_name(meta["name"])
            prefecture = str(manhole.get("prefecture") or "")
            city = str(manhole.get("city") or "")
            # 写真の上に重ねるバッジは狭いので、ガンダムは短い呼び名にする
            badge = "ガンダム" if meta["key"] == GUNDAM_WORK_QUERY else label
            photo.update(linked=True, key=meta["key"], label=label, badge=badge, place=place, href=href,
                         prefecture=prefecture, city=city,
                         alt=f"{label}のマンホール {place}（{prefecture}{city}）")
        else:
            source = str(record.get("source_url") or "")
            prefecture = str(record.get("prefecture") or "")
            city = str(record.get("city") or "").replace("　", "")
            photo.update(linked=False, key="", label=UNLINKED_PHOTO_LABEL, place=title,
                         href=_with_from_data(source) if _is_design_manhole_page(source) else DESIGN_MANHOLE_HREF,
                         prefecture=prefecture, city=city,
                         alt=f"{UNLINKED_PHOTO_LABEL}「{title}」（{prefecture}{city}）")
        photos.append(photo)
    return photos


def select_photos(photos: list[dict], *, seed_date: date | None = None) -> tuple[list[dict], list[dict]]:
    """ヒーロー（6〜8枚）とギャラリー（約12枚）に、重複なく振り分ける。

    ヒーローはキャラクターマンホールの写真を先頭に、残りを JST の日付でシードした乱数で
    日替わりに（毎日のビルドで顔ぶれが変わる）。ギャラリーはヒーローに出なかった写真の新しい順。
    """
    rng = random.Random((seed_date or datetime.now(JST).date()).isoformat())
    linked = [p for p in photos if p["linked"]]
    others = [p for p in photos if not p["linked"]]
    rng.shuffle(linked)
    rng.shuffle(others)
    hero = (linked + others)[:HERO_PHOTO_LIMIT]
    shown = {p["id"] for p in hero}
    rest = sorted((p for p in photos if p["id"] not in shown), key=lambda p: p["created_at"], reverse=True)
    rest.sort(key=lambda p: not p["linked"])  # 安定ソートで「キャラクターマンホール → 新しい順」
    return hero, rest[:GALLERY_PHOTO_LIMIT]


def _photo_img(photo: dict, *, lazy: bool, size: int = PHOTO_BOX, priority: bool = False) -> str:
    # 元画像は 300×400 の縦長。枠は正方形で予約し（width/height + CSS の aspect-ratio）、
    # object-fit: cover で中央を切り抜くので、読み込み前後でレイアウトが動かない。
    attrs = 'loading="lazy" ' if lazy else ('fetchpriority="high" ' if priority else "")
    return (f'<img src="{escape(photo["photo_url"])}" alt="{escape(photo["alt"])}" '
            f'width="{size}" height="{size}" {attrs}decoding="async">')


def _hero_mosaic_html(photos: list[dict]) -> str:
    if not photos:
        return ""
    items = "".join(
        f'<li class="lp-hero-mosaic-item{" is-linked" if p["linked"] else ""}">'
        f'<a href="{escape(p["href"])}">{_photo_img(p, lazy=False, priority=i == 0)}'
        + (f'<span class="lp-photo-badge">{escape(p["badge"])}</span>' if p["linked"] else "")
        + '</a></li>'
        for i, p in enumerate(photos)
    )
    linked = [p for p in photos if p["linked"]]
    if linked:
        names = "、".join(dict.fromkeys(f'{p["label"]}（{p["place"]}）' for p in linked))
        note = f"うち{len(linked)}枚はキャラクターマンホール：{names}。ほかは{UNLINKED_PHOTO_LABEL}です。"
    else:
        note = f"キャラクターマンホールと確認できていない{UNLINKED_PHOTO_LABEL}を含みます。"
    return (f'<figure class="lp-hero-photos"><ul class="lp-hero-mosaic">{items}</ul>'
            f'<figcaption class="lp-hero-mosaic-caption">写真はポケふた写真館への投稿（{len(photos)}枚）。{escape(note)}</figcaption></figure>')


def _gallery_html(photos: list[dict]) -> str:
    items = "".join(
        f'<li class="lp-gallery-item{" is-linked" if p["linked"] else ""}"><figure>'
        f'<a href="{escape(p["href"])}">{_photo_img(p, lazy=True)}</a>'
        f'<figcaption><span class="lp-gallery-kind">{escape(p["label"])}</span>'
        f'<strong>{escape(p["place"])}</strong>'
        f'<span class="lp-gallery-where">{escape(p["prefecture"] + p["city"])}'
        + (f' · {escape(p["date"])}' if p["date"] else "")
        + '</span></figcaption></figure></li>'
        for p in photos
    )
    return f'<ul class="lp-gallery">{items}</ul>'


def _join_counts(pairs: list[tuple[str, int]], limit: int) -> str:
    shown = "・".join(f"{name} {count}" for name, count in pairs[:limit])
    if len(pairs) > limit:
        shown += f" ほか{len(pairs) - limit}"
    return shown


def build_faq_items(work_summaries: list[dict], pref_summaries: list[dict]) -> list[tuple[str, str]]:
    """画面とJSON-LDの両方に出すFAQ。件数はここで一度だけ組み立て、両方に同じ文字列を渡す。"""
    items = [FAQ_ITEMS[0]]
    if pref_summaries:
        # 同数の県が並ぶときは1県だけを「最多」と言い切らない
        best = pref_summaries[0]["count"]
        leaders = [e["prefecture"] for e in pref_summaries if e["count"] == best]
        if len(leaders) == 1:
            answer = f"掲載データで最も多いのは{leaders[0]}（{best}枚）"
        else:
            answer = f"掲載データで最も多いのは{'と'.join(leaders[:3])}{'など' if len(leaders) > 3 else ''}（各{best}枚）"
        followers = [e for e in pref_summaries if e["count"] < best][:2]
        if followers and len(leaders) < 3:
            answer += "で、" + "、".join(f"{e['prefecture']}（{e['count']}枚）" for e in followers) + "が続きます。"
        else:
            answer += "です。"
        answer += "都道府県別の一覧から、それぞれの県で見られる作品と設置場所を確認できます。"
        items.append(("キャラクターマンホールが多い都道府県はどこですか？", answer))
    gundam = next((s for s in work_summaries if s["query"] == GUNDAM_WORK_QUERY), None)
    if gundam:
        answer = f"掲載データでは{len(gundam['prefectures'])}都道府県に{gundam['count']}枚あります。"
        if gundam.get("path"):
            answer += "市町村ごとの設置場所と住所は、機動戦士ガンダムの作品ガイドで確認できます。"
        else:
            answer += "設置場所は地図で「ガンダム」に絞り込んで確認できます。"
        items.append(("ガンダムマンホールはどこにありますか？", answer))
    return items + FAQ_ITEMS[1:]


def _work_card_html(summary: dict, photo: dict | None = None) -> str:
    href = _work_href(summary.get("path", ""), summary["query"])
    # キャラ名自体に「・」を含むものがある（例: まる子・友蔵）ので区切りは読点にする
    characters = summary.get("characters") or []
    character_text = "、".join(characters[:WORK_CARD_CHARACTER_LIMIT])
    if len(characters) > WORK_CARD_CHARACTER_LIMIT:
        character_text += f" ほか{len(characters) - WORK_CARD_CHARACTER_LIMIT}種"
    pref_text = _join_counts(summary["main_prefectures"], WORK_CARD_PREFECTURE_LIMIT)
    go_text = "設置場所ガイドへ →" if summary.get("path") else "地図で見る →"
    return (
        f'<li><a class="lp-work-card" href="{href}" style="--c:{escape(summary["color"])}">'
        + (f'<span class="lp-work-thumb">{_photo_img(photo, lazy=True, size=96)}</span>' if photo
           else _lid_html(summary["color"], summary["label"]))
        + f'<strong>{escape(summary["work"])}</strong>'
        f'<span class="lp-work-count"><b class="cm-num">{summary["count"]}</b>枚</span>'
        + (f'<small class="lp-work-chars"><span>主なキャラクター</span>{escape(character_text)}</small>' if character_text else '')
        + (f'<small class="lp-work-prefs"><span>主な都道府県</span>{escape(pref_text)}</small>' if pref_text else '')
        + (f'<small class="lp-work-photo"><span>写真</span>{escape(photo["place"])}（{escape(photo["prefecture"] + photo["city"])}）</small>' if photo else '')
        + f'<span class="lp-work-go">{go_text}</span></a></li>'
    )


def _pref_anchor(prefecture: str) -> str:
    return "pref-" + PREFECTURE_SLUGS.get(prefecture, quote(prefecture, safe=""))


def _place_label(record: dict, meta: dict) -> str:
    """「設置場所（キャラクター／作品）」。ガンダムは設置場所名だけ。"""
    place = str(record.get("landmark") or record.get("title") or "設置場所").strip()
    character = str(record.get("character") or "").strip()
    work = _short_work_name(meta["name"])
    # title にキャラ名が入っているもの・キャラ名が作品名そのものは重ねない
    if character and character not in place and character != work:
        return f"{place}（{character}／{work}）"
    return f"{place}（{work}）" if meta["key"] != GUNDAM_WORK_QUERY else place


def build_prefecture_groups(character_records: list[dict], gundam_records: list[dict]) -> list[dict]:
    """都道府県ごとのレコードと作品内訳。都道府県一覧と設置場所一覧が同じ集計を使う。"""
    by_pref: dict[str, list[tuple[dict, dict]]] = defaultdict(list)
    for records, is_gundam in ((character_records, False), (gundam_records, True)):
        for record in records:
            prefecture = str(record.get("prefecture") or "").strip() or "都道府県未記録"
            by_pref[prefecture].append((record, _work_meta_for(record, is_gundam)))

    order = {name: index for index, name in enumerate(PREFECTURE_ORDER)}
    groups = []
    for prefecture in sorted(by_pref, key=lambda name: (order.get(name, 999), name)):
        items = sorted(by_pref[prefecture], key=lambda item: (
            str(item[0].get("city") or ""), item[1]["name"], str(item[0].get("id") or "")
        ))
        works: dict[str, dict] = {}
        for _, meta in items:
            works.setdefault(meta["key"], {**meta, "count": 0})["count"] += 1
        cities = Counter(str(record.get("city") or "").strip() for record, _ in items if record.get("city"))
        groups.append({
            "prefecture": prefecture,
            "region": _region_of(prefecture),
            "items": items,
            "works": sorted(works.values(), key=lambda w: (-w["count"], w["name"])),
            "cities": sorted(cities.items(), key=lambda pair: (-pair[1], pair[0])),
        })
    return groups


def _featured_items(group: dict) -> list[tuple[dict, dict]]:
    """県ごとに本文へ出す代表の設置場所。枚数の多い作品から1枚ずつ順に取り、作品が偏らないようにする。"""
    queues = {w["key"]: [item for item in group["items"] if item[1]["key"] == w["key"]] for w in group["works"]}
    picked: list[tuple[dict, dict]] = []
    while len(picked) < FEATURED_PLACES_PER_PREFECTURE and any(queues.values()):
        for work in group["works"]:
            if queues[work["key"]] and len(picked) < FEATURED_PLACES_PER_PREFECTURE:
                picked.append(queues[work["key"]].pop(0))
    return picked


def _prefecture_list_html(groups: list[dict]) -> str:
    """地方ごとの「都道府県名・枚数・主な作品」の文字の一覧。県名は下の設置場所一覧へのページ内リンク。"""
    regions: dict[str, list[dict]] = defaultdict(list)
    for group in groups:
        regions[group["region"]].append(group)
    blocks = []
    for region in [name for name, _, _ in REGIONS] + ["その他"]:
        if region not in regions:
            continue
        rows = "".join(
            f'<li data-pref="{escape(g["prefecture"])}"><a href="#{_pref_anchor(g["prefecture"])}">{escape(g["prefecture"])}</a>'
            f'<b><span class="cm-num">{len(g["items"])}</span>枚</b>'
            f'<span class="lp-pref-works">{escape(_join_counts([(_short_work_name(w["name"]), w["count"]) for w in g["works"]], PREF_ROW_WORK_LIMIT))}</span></li>'
            for g in regions[region]
        )
        blocks.append(f'<div class="lp-region"><h3>{escape(region)}</h3><ul class="lp-pref-list">{rows}</ul></div>')
    return '<div class="lp-regions">' + "".join(blocks) + '</div>'


def _places_html(groups: list[dict]) -> str:
    """県ごとの設置場所。市町村と設置場所名は本文に出し、住所・出典つきの全件は details に入れる。

    枚数の多い県は「市町村」「主な設置場所」の2行、少ない県は市町村ごとの設置場所名を
    1行に収めて、スマホでも縦に伸びすぎないようにする。
    """
    major = sorted((g for g in groups if len(g["items"]) >= MAJOR_PREFECTURE_MIN),
                   key=lambda g: -len(g["items"]))
    minor = [g for g in groups if len(g["items"]) < MAJOR_PREFECTURE_MIN]

    def block(group: dict, compact: bool) -> str:
        prefecture = group["prefecture"]
        anchor = _pref_anchor(prefecture)
        total = len(group["items"])
        locations = "".join(_location_item_html(record, meta, prefecture) for record, meta in group["items"])
        map_link = (
            f'<p class="lp-place-map"><a href="{MAP_HREF}?pref={quote(prefecture)}">{escape(prefecture)}の地図を見る →</a></p>'
            if prefecture in PREFECTURE_SLUGS else ""
        )
        if compact:
            by_city: dict[str, list[str]] = defaultdict(list)
            for record, meta in group["items"]:
                by_city[str(record.get("city") or "市町村未記録")].append(_place_label(record, meta))
            body = f'<p class="lp-place-line">{escape(" ／ ".join(f"{city}：" + "、".join(names) for city, names in by_city.items()))}</p>'
            summary = "住所・出典"
        else:
            featured = "、".join(escape(_place_label(record, meta)) for record, meta in _featured_items(group))
            body = (f'<p class="lp-place-line"><span>市町村</span>{escape(_join_counts(group["cities"], 8))}</p>'
                    f'<p class="lp-place-line"><span>主な設置場所</span>{featured}</p>')
            summary = f"{escape(prefecture)}の設置場所{total}枚をすべて見る"
        return (
            f'<section class="lp-place-pref{" lp-place-pref--mini" if compact else ""}" id="{anchor}" '
            f'data-pref="{escape(prefecture)}" aria-labelledby="{anchor}-h">'
            f'<h3 id="{anchor}-h">{escape(prefecture)}<small>{total}枚</small></h3>{body}'
            f'<details class="lp-places"><summary>{summary}</summary>'
            f'<ul class="lp-location-list">{locations}</ul>{map_link}</details></section>'
        )

    html = ""
    if major:
        html += ('<p class="lp-place-group">設置数の多い都道府県</p><div class="lp-place-grid">'
                 + "".join(block(g, False) for g in major) + '</div>')
    if minor:
        html += ('<p class="lp-place-group">そのほかの都道府県</p><div class="lp-place-grid lp-place-grid--mini">'
                 + "".join(block(g, True) for g in minor) + '</div>')
    return html


def generate_html(
    character_records: list[dict],
    gundam_records: list[dict],
    design_manhole_path: Path | None = None,
    *,
    seed_date: date | None = None,
) -> str:
    work_summaries = build_work_summaries(character_records, gundam_records)
    pref_summaries = build_prefecture_summaries(character_records, gundam_records)
    groups = build_prefecture_groups(character_records, gundam_records)
    faq_items = build_faq_items(work_summaries, pref_summaries)

    total_count = len(character_records) + len(gundam_records)
    work_count = len(work_summaries)
    pref_count = len(pref_summaries)

    title = f"アニメ・キャラクターマンホール全国一覧｜{total_count}枚の設置場所・地図"
    description = (
        f"全国{pref_count}都道府県・{work_count}作品、{total_count}枚のアニメ・キャラクターマンホールを一覧で紹介。"
        "ガンダムやゾンビランドサガなどを作品別・都道府県別に探し、市町村・設置場所・出典と地図を確認できます。"
        "キャラクター名や設置場所名からも探せます。"
    )

    top_works = "、".join(f"{s['work']}（{s['count']}枚）" for s in work_summaries[:3])
    all_cities = Counter(
        str(r.get("city")) for r in (*character_records, *gundam_records) if r.get("city")
    )
    sample_city = all_cities.most_common(1)[0][0] if all_cities else "市町村名"
    sample_character = next(
        (s["characters"][0] for s in work_summaries if s.get("characters")), "キャラクター名"
    )

    photos = build_photos(design_manhole_path, character_records, gundam_records)
    hero_photos, gallery_photos = select_photos(photos, seed_date=seed_date)
    gallery_lead = (
        "ポケふた写真館に届いた、実物のマンホールの写真です。キャラクターマンホールと確認できた写真には"
        f"作品名と設置場所を、確認できていないものには「{UNLINKED_PHOTO_LABEL}」と表示しています。"
        if gallery_photos else
        "ポケふた写真館に届いた実物のマンホール写真を、ここで紹介します。旅先で撮った1枚をお待ちしています。"
    )
    work_photos: dict[str, dict] = {}
    for photo in photos:
        if photo["linked"]:
            work_photos.setdefault(photo["key"], photo)
    work_items_html = "\n".join(
        _work_card_html(summary, work_photos.get(_summary_key(summary))) for summary in work_summaries
    )
    prefecture_list_html = _prefecture_list_html(groups)
    places_html = _places_html(groups)
    faq_html = "".join(
        f'<details><summary>{escape(question)}</summary><p>{escape(answer)}</p></details>'
        for question, answer in faq_items
    )

    works_list_id = f"{CANONICAL_URL}#works"
    json_ld_webpage = {
        "@type": "CollectionPage",
        "@id": CANONICAL_URL,
        "url": CANONICAL_URL,
        "name": title,
        "description": description,
        "inLanguage": "ja",
        "isPartOf": {"@type": "WebSite", "name": "ポケふたDATABASE", "url": BASE_URL},
        "primaryImageOfPage": {"@type": "ImageObject", "url": OG_IMAGE, "width": 1200, "height": 630},
        "breadcrumb": {"@id": f"{CANONICAL_URL}#breadcrumb"},
        "mainEntity": {"@id": works_list_id},
    }
    json_ld_breadcrumb = {
        "@type": "BreadcrumbList",
        "@id": f"{CANONICAL_URL}#breadcrumb",
        "itemListElement": [
            {"@type": "ListItem", "position": 1, "name": "ポケふた図鑑", "item": BASE_URL},
            {"@type": "ListItem", "position": 2, "name": "キャラクターマンホール全国一覧", "item": CANONICAL_URL},
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
            for question, answer in faq_items
        ],
    }
    json_ld_itemlist = {
        "@type": "ItemList",
        "@id": works_list_id,
        "name": "アニメ・キャラクターマンホールを作品から探す",
        "numberOfItems": work_count,
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
        {"@context": "https://schema.org", "@graph": [json_ld_webpage, json_ld_breadcrumb, json_ld_itemlist, json_ld_faq]},
        ensure_ascii=False,
    ).replace("<", "\\u003c")

    return f"""<!doctype html>
<html lang="ja">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>{escape(title)}</title>
  <meta name="description" content="{escape(description)}">
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
    <nav class="cw-breadcrumb" aria-label="パンくず"><a href="./">ポケふた図鑑</a><span>/</span><span aria-current="page">キャラクターマンホール全国一覧</span></nav>

    <section class="cm-hero cm-hero--lp{"" if hero_photos else " cm-hero--no-photos"}" id="lp-intro" aria-labelledby="lp-h1">
      <div>
        <p class="cm-eyebrow">CHARACTER MANHOLE DIRECTORY</p>
        <h1 id="lp-h1">アニメ・キャラクターマンホール<br>全国一覧・設置場所</h1>
        <p class="cm-hero-lead">全国{total_count}枚の設置場所を、作品・キャラクター・都道府県・市町村から探せる図鑑です。</p>
        <ul class="cm-stats" aria-label="掲載数">
          <li><strong class="cm-num">{total_count}</strong>枚</li>
          <li><strong class="cm-num">{work_count}</strong>作品</li>
          <li><strong class="cm-num">{pref_count}</strong>都道府県</li>
        </ul>
        <p class="cm-hero-note">掲載データ：{total_count}枚・{work_count}作品・{pref_count}都道府県。全国すべてを網羅するものではありません。</p>
      </div>
      {_hero_mosaic_html(hero_photos)}
      <nav class="lp-hub" aria-label="探し方">
        <a class="lp-hub-item" href="#works"><b>作品から探す</b><span>{work_count}作品</span></a>
        <a class="lp-hub-item" href="#prefectures"><b>都道府県から探す</b><span>{pref_count}都道府県</span></a>
        <form class="lp-hub-item lp-hub-search" role="search" action="#places">
          <label for="place-q"><b>設置場所名・市町村から探す</b></label>
          <input id="place-q" name="q" type="search" enterkeyhint="search" autocomplete="off" placeholder="例：{escape(sample_city)}、{escape(sample_character)}">
          <span class="lp-hub-status" id="place-q-status" aria-live="polite"></span>
        </form>
        <a class="lp-hub-item lp-hub-map" href="{MAP_HREF}"
           onclick="trackEvent('click_map_cta',{{surface:'character_search_hub',cta:'map_hub',from:'character_manholes_lp'}})"><b>地図で探す</b><span>地図で{total_count}件を見る →</span></a>
      </nav>
    </section>

    <section class="lp-intro" aria-label="このページについて">
      <div>
        <strong>キャラクターマンホールとは</strong>
        <p>アニメ・漫画・ゲームのキャラクターを絵柄に入れたマンホールの蓋です。作品の舞台になった街や作者ゆかりの自治体が、観光やまちおこしの一環として設置していることが多く、その土地を訪ねないと見ることができません。</p>
      </div>
      <div>
        <strong>このページで分かること</strong>
        <p>全国{pref_count}都道府県・{work_count}作品の{total_count}枚について、作品名・キャラクター名・都道府県・市町村から設置場所を探せます。収録が多いのは{escape(top_works)}です。設置場所ごとに施設名・住所・出典と地図へのリンクを載せています。</p>
      </div>
      <div>
        <strong>掲載範囲と注意</strong>
        <p>収録は出典を確認できたものに限られ、全国の設置をすべて集めたものではありません。移設・撤去や施設の開放時間が変わることもあるため、訪問前に出典の最新案内をご確認ください。マンホールカードの配布状況とは別の一覧です。ポケモンのマンホールは<a href="./">ポケふた図鑑</a>で紹介しています。</p>
      </div>
    </section>

    <section class="cm-section" id="works" aria-labelledby="lp-works-heading">
      <div class="cm-section-head">
        <h2 id="lp-works-heading">アニメ・キャラクターマンホールを作品から探す</h2>
      </div>
      <p class="cm-lead">枚数の多い順です。作品を選ぶと、キャラクター・市町村・設置場所・住所・出典をまとめた作品ガイドへ進みます。アイマスは各シリーズをまとめて1作品として数えています。</p>
      <ul class="lp-work-grid">
{work_items_html}
      </ul>
    </section>

    <section class="cm-section" id="prefectures" aria-labelledby="lp-pref-heading">
      <div class="cm-section-head">
        <h2 id="lp-pref-heading">都道府県から設置場所を探す</h2>
      </div>
      <p class="cm-lead">掲載のある{pref_count}都道府県を、地方ごとに北から並べています。県名を選ぶと、その県の市町村と設置場所の一覧へ移動します。掲載のない地域にも未収録のマンホールがある場合があります。</p>
{prefecture_list_html}
    </section>

    <section class="cm-section" id="places" aria-labelledby="lp-places-heading">
      <div class="cm-section-head">
        <h2 id="lp-places-heading">全国の主な設置場所</h2>
        <a class="cm-btn cm-btn--soft" href="{MAP_HREF}"
           onclick="trackEvent('click_map_cta',{{surface:'character_places',cta:'map_places',from:'character_manholes_lp'}})">地図で{total_count}件を見る →</a>
      </div>
      <p class="cm-lead">都道府県ごとの市町村と主な設置場所です。「すべて見る」を開くと、全{total_count}枚の設置場所・住所・出典を確認できます。移設・撤去や施設の開放時間は、訪問前に出典の案内をご確認ください。</p>
{places_html}
    </section>

    <section class="cm-section" id="photos" aria-labelledby="lp-photos-heading">
      <div class="cm-section-head">
        <h2 id="lp-photos-heading">投稿されたマンホール写真</h2>
        <a href="{DESIGN_MANHOLES_LIST_URL}" target="_blank" rel="noopener noreferrer">すべての投稿を見る →</a>
      </div>
      <p class="cm-lead">{gallery_lead}</p>
{_gallery_html(gallery_photos) if gallery_photos else ""}
      <div class="lp-promo lp-promo--photos">
        <div>
          <h3>その1枚、まだカメラロールにありますか？</h3>
          <p>旅先で撮ったマンホールの写真を、場所と一緒に残せます。キャラクターものでなくても構いません。位置情報（GPS）付きの写真なら、設置場所は自動で入ります。</p>
        </div>
        <div class="lp-promo-actions">
          <a class="cm-btn cm-btn--dark" href="{DESIGN_MANHOLE_HREF}"
             onclick="trackEvent('click_design_manhole_lp',{{surface:'character_cta',from:'character_manholes_lp'}})">写真を投稿する</a>
        </div>
      </div>
    </section>

    <!-- キャラクターマンホールとは（検索語のためh2は変更しない） -->
    <section class="cm-section" aria-labelledby="lp-about-heading">
      <div class="cm-section-head">
        <h2 id="lp-about-heading">キャラクターマンホールとは</h2>
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

    <section class="cm-section" aria-labelledby="lp-faq-heading">
      <div class="cm-section-head">
        <h2 id="lp-faq-heading">よくある質問</h2>
      </div>
      <div class="cm-faq">
        {faq_html}
      </div>
    </section>

    <footer class="cm-footer" role="contentinfo">
      <a href="./">ポケふたマップ</a>/<a href="{MAP_HREF}">キャラクターマンホールマップ</a>/<a href="{DESIGN_MANHOLE_HREF}">デザインマンホール投稿</a>/<a href="./character_manholes.ndjson" target="_blank" rel="noopener">キャラNDJSON</a>/<a href="./gmanhole.ndjson" target="_blank" rel="noopener">ガンダムNDJSON</a>
    </footer>
  </main>

  <script>
  // 設置場所名・市町村の絞り込み。JSが無くても一覧は静的HTMLで全件読める（段階的強化）。
  (function() {{
    var input = document.getElementById('place-q');
    var status = document.getElementById('place-q-status');
    if (!input || !status) return;
    var blocks = [].slice.call(document.querySelectorAll('.lp-place-pref'));
    function norm(s) {{ return (s || '').replace(/\\s+/g, '').toLowerCase(); }}
    function apply() {{
      var q = norm(input.value), hits = 0;
      blocks.forEach(function(block) {{
        var found = 0;
        [].forEach.call(block.querySelectorAll('.lp-location-list li'), function(li) {{
          var ok = !q || norm(block.dataset.pref + li.textContent).indexOf(q) !== -1;
          li.hidden = !ok;
          if (ok && q) found++;
        }});
        block.hidden = !!q && !found;
        var details = block.querySelector('details');
        if (details) details.open = !!q && found > 0;
        hits += found;
      }});
      status.innerHTML = q
        ? (hits ? hits + '件見つかりました <a href="#places">一覧を見る ↓</a>' : '見つかりませんでした')
        : '';
    }}
    input.addEventListener('input', apply);
    input.form.addEventListener('submit', function(event) {{
      event.preventDefault();
      apply();
      document.getElementById('places').scrollIntoView();
    }});
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
