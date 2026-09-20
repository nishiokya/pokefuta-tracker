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
import random
from collections import Counter, defaultdict
from datetime import date, datetime
from pathlib import Path
from urllib.parse import parse_qs, quote, urlparse
from html import escape

try:
    from apps.scraper.photo_caption import (
        CAPTION_ELLIPSIS_CSS,
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
        CAPTION_ELLIPSIS_CSS,
        JST,
        caption_meta,
        format_display_name,
        format_photo_date,
        poster_profile_url,
    )

try:
    from apps.scraper.character_manhole_works import page_for_work
    from apps.scraper.prefectures import PREFECTURE_ORDER
except ModuleNotFoundError as exc:
    if exc.name != "apps":
        raise
    from character_manhole_works import page_for_work
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

# ガンダムマンホールは character_manholes.ndjson の "work" を持たない独立データセット
# なので、作品カードには合成エントリとして差し込む。
GUNDAM_WORK_NAME = "機動戦士ガンダム（ガンダムマンホール）"
GUNDAM_WORK_QUERY = "gundam"  # gmanhole_map.html の ?work= に渡す値（chk-gundam を選択する特別値）
GUNDAM_MARKER_COLOR = "#0044aa"
GUNDAM_MARKER_LABEL = "G"

LATEST_POSTS_LIMIT = 4

# ヒーローセクションの写真モザイク用。デザインマンホール投稿のうち
# canonical_ref / nearby_refs がこのプレフィックスで始まる参照を持つものは
# 「キャラクターマンホールと確認できる投稿」として優先枠に入れる。
CHARACTER_LINKAGE_PREFIXES = ("gundam:", "character:")
HERO_MOSAIC_LIMIT = 6

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
    groups: dict[str, list[dict]] = defaultdict(list)
    for record in character_records:
        work = str(record.get("work") or "").strip()
        if not work:
            continue
        page = page_for_work(work)
        groups[page.name if page else work].append(record)

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
            "query": page_for_work(work).map_query if page_for_work(work) else work,
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

    /* ── ファーストView（#lp-intro）は index.html の #sec-intro と同じ top-page.css
       クラス（.sec-eyebrow/.top-h1/.top-intro-text/.top-stats-note 等）をそのまま使う。
       掲載範囲を示す統計は stats-note の1行にまとめる（3タイル用CSSクラスは
       このファイルからは一切参照しない）。
       ID は #sec-intro を再利用しない: top-page.css は @media (min-width: 960px) 内で
       #sec-intro/#sec-map/#sec-hero/#sec-hub/#sec-pref/#sec-events/#sec-newrelease を
       index.html 専用の重なりレイアウト（#sec-intro と #sec-map を同じグリッドに重ねて
       pointer-events:none で下の地図へクリックを透過させる設計）でID指定しており、
       このLPで同じIDを使うと 52%幅の左寄せ・クリック不能というバグを引く
       （実際に発生した回帰。top-page.css は共有ファイルなので編集しない）。
       .lp-wrap 自身の左右 padding と .top-section 自身の padding が二重にならないよう、
       この1セクションだけ打ち消しておく（他の .lp-section は元々 .lp-wrap の padding
       のみに依存しているため対象外）。 */
    #lp-intro { margin: 0 calc(-1 * var(--top-pad)); }

    /* ── ヒーロー写真モザイク（design_manholes.ndjson の投稿写真、size=small のみ）
       元画像は 300×400 のポートレートだが、タイルは固定サイズの正方形クリップで揃える
       （可変グリッドで伸び縮みさせない）。flex-wrap で並べるだけなので、幅に応じて
       自然に1行あたりの枚数が変わり、モバイル/デスクトップ別のブレークポイントは不要。 */
    .lp-hero-mosaic {
      display: flex; flex-wrap: wrap; justify-content: center; gap: 6px;
      max-width: 640px; margin: 10px auto 6px; padding: 0; list-style: none;
    }
    .lp-hero-mosaic-item {
      flex: 0 0 auto; width: 96px; height: 96px;
      overflow: hidden; border-radius: var(--top-radius-card);
      background: var(--top-purple-pale); box-shadow: 0 2px 8px rgba(0,0,0,0.08);
    }
    .lp-hero-mosaic-item img {
      display: block; width: 100%; height: 100%;
      object-fit: cover; object-position: center;
    }
    .lp-hero-mosaic-caption { margin: 0 0 14px; font-size: 11px; color: var(--top-text-muted); }

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

    .lp-jump-links { display: flex; flex-wrap: wrap; justify-content: center; gap: 10px 18px; }
    .lp-jump-links a, .lp-locations a { color: var(--top-purple); text-underline-offset: 3px; }
    .lp-locations { margin-top: 16px; border: 1px solid var(--top-border); border-radius: var(--top-radius-card); padding: 12px 16px; }
    .lp-locations summary { cursor: pointer; font-weight: 700; }
    .lp-location-list { list-style: none; padding: 0; margin: 12px 0 0; }
    .lp-location-list li { padding: 12px 0; border-top: 1px solid var(--top-border-light); overflow-wrap: anywhere; }
    .lp-location-list p { margin: 4px 0; font-size: 13px; }

    /* ── 地図で探す（.map-gateway-card 等は top-page.css の index.html 用スタイルを流用） ── */

    /* top-page.css の @media (min-width: 960px) は、#sec-intro を「地図の左に重ねる
       オーバーレイパネル」として扱うことを前提に、対になる .top-intro-text の幅を
       狭め、.map-gateway-title/.map-gateway-sub を隠し、.map-gateway-badge を右寄せ、
       .map-gateway-overlay を右下のCTAピルだけに縮小している
       （index.html はオーバーレイパネル側に同じ説明文がある前提）。
       このLPは #sec-intro を使わない（id="lp-intro"）ので対になるパネルが無く、
       そのままではデスクトップ幅で本文とCTA説明文が消えてしまう。
       top-page.css 自体は編集せず、詳細度で勝つセレクタでこのページの範囲内だけ
       打ち消す（960px未満では元々の値と一致するため no-op）。
       （3タイル統計用のCSSクラスはヒーローから削除したのでこのLPではもう
       使っていない。打ち消しも不要）。 */
    .character-manhole-lp .top-intro-text { max-width: none; }
    .character-manhole-lp .map-gateway-title,
    .character-manhole-lp .map-gateway-sub { display: block; }
    .character-manhole-lp .map-gateway-overlay {
      inset: 0; width: auto; padding: 26px 13px 13px;
      background: linear-gradient(to top, rgba(26,38,46,.9) 40%, rgba(26,38,46,0));
    }
    .character-manhole-lp .map-gateway-cta { display: block; margin-top: 11px; padding: 13px; }
    .character-manhole-lp .map-gateway-badge { left: 11px; right: auto; }

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
    .lp-photo-grid { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 10px; margin: 0; padding: 0; list-style: none; }
    @media (min-width: 560px) { .lp-photo-grid { grid-template-columns: repeat(4, minmax(0, 1fr)); } }
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
    page = page_for_work(summary["work"])
    href = f"./{page.path}" if page else map_href
    return (
        f'<li><a class="lp-work-card" href="{href}">'
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


def _location_directory_html(character_records: list[dict], gundam_records: list[dict]) -> str:
    """設置場所と出典を静的HTMLに出す。地図のJSを実行しなくても読める一覧。"""
    groups: dict[str, list[tuple[str, dict]]] = defaultdict(list)
    for records, fallback_work in ((character_records, "作品不明"), (gundam_records, GUNDAM_WORK_NAME)):
        for record in records:
            groups[str(record.get("prefecture") or "都道府県未記録")].append(
                (str(record.get("work") or fallback_work), record)
            )
    order = {name: index for index, name in enumerate(PREFECTURE_ORDER)}
    sections = []
    for prefecture in sorted(groups, key=lambda name: (order.get(name, 999), name)):
        rows = []
        for work, record in sorted(groups[prefecture], key=lambda item: (
            str(item[1].get("city") or ""), item[0], str(item[1].get("id") or "")
        )):
            city = str(record.get("city") or "")
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
            rows.append(
                f'<li><strong>{escape(name)}</strong>'
                f'<p>{escape(work)} ／ {escape(prefecture)}{escape(city)}</p>'
                f'<p>{escape(address)}{source_html}</p></li>'
            )
        sections.append(
            '<details class="lp-locations">'
            f'<summary class="lp-location-summary">{escape(prefecture)}の設置場所一覧（{len(rows)}枚）</summary>'
            f'<p><a href="{MAP_HREF}?pref={quote(prefecture)}">{escape(prefecture)}の地図を見る</a></p>'
            f'<ul class="lp-location-list">{"".join(rows)}</ul></details>'
        )
    return "\n".join(sections)


def _hero_mosaic_item_html(post: dict) -> str:
    alt_text = f"{post['title']} {post['location']}".strip()
    # 元画像は 300×400 のポートレートだが、タイルは正方形クリップ（CSS側の
    # aspect-ratio ではなく固定 width/height）で表示するため、属性も正方形の
    # 値にしておく（CLS防止。実際のクロップは object-fit: cover が担う）。
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
    pref_items_html = "\n".join(_pref_item_html(entry) for entry in pref_summaries)
    location_directory_html = _location_directory_html(character_records, gundam_records)

    if hero_mosaic_posts:
        hero_mosaic_items_html = "\n".join(_hero_mosaic_item_html(post) for post in hero_mosaic_posts)
        hero_mosaic_html = f"""
      <ul class="lp-hero-mosaic">
{hero_mosaic_items_html}
      </ul>
      <p class="lp-hero-mosaic-caption">写真はすべて、みんなが投稿した実物です</p>"""
    else:
        hero_mosaic_html = ""

    if latest_posts:
        photo_items_html = "\n".join(_photo_card_html(post) for post in latest_posts)
        latest_section_html = f"""
    <section class="lp-section" aria-labelledby="lp-latest-heading">
      <h2 id="lp-latest-heading"><span aria-hidden="true">LATEST POSTS</span>先に出してくれた人たち</h2>
      <p class="lp-section-lead">ポケふたを撮りに行った先で、ついでに撮られた蓋です。</p>
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
                "url": (f"{BASE_URL}{page_for_work(summary['work']).path}"
                        if page_for_work(summary['work']) else f"{MAP_URL}?work={quote(summary['query'])}"),
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
  <link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css"
    integrity="sha256-p4NxAoJBhIIN+hmNHrzRCf9tD/miZyoHS5obTRR9BMY=" crossorigin="">
  <script src="./assets/session-badge.js" defer></script>
  <style>{PAGE_STYLE}</style>
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
<body class="character-manhole-lp">
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

  <main class="lp-wrap">
    <!-- ── H1 + INTRO + STATS（index.html の #sec-intro と同じ構造・同じCSSクラス。
         ID は index.html の #sec-intro/#sec-map 重なりレイアウト用IDと衝突しないよう
         lp-intro にしている。詳細は PAGE_STYLE 側のコメント参照） ── -->
    <section class="top-section" id="lp-intro">
      <div class="sec-eyebrow">
        <span class="sec-num"></span>
        <span class="sec-eyebrow-text">CHARACTER MANHOLE / キャラクターマンホール</span>
      </div>
      <h1 class="top-h1">アニメ・キャラクターマンホール<br>全国一覧・設置場所マップ</h1>
{hero_mosaic_html}
      <p class="top-intro-text">
        アニメ・漫画・ゲームなどのキャラクターが描かれた、ご当地マンホールを探せます。
        <b>作品別・都道府県別の一覧</b>から、設置されている市町村・場所・地図を確認してください。
        ポケモンのマンホールは<a href="./">ポケふた図鑑</a>で紹介しています。
      </p>
      <p class="top-stats-note">掲載データ：{total_count}枚・{work_count}作品・{pref_count}都道府県。全国すべてを網羅するものではありません。</p>
      <nav class="lp-jump-links" aria-label="このページの目次">
        <a href="#lp-works-heading">作品別一覧</a>
        <a href="#lp-pref-heading">都道府県別・設置場所一覧</a>
        <a href="#lp-map-heading">全国地図</a>
      </nav>
    </section>

    <!-- ── 地図で探す（index.html と同じ並び: #sec-intro の直後。
         map-gateway-card は index.html と同じ、操作不能な実地図プレビュー） ── -->
    <section class="lp-section" aria-labelledby="lp-map-heading">
      <h2 id="lp-map-heading"><span aria-hidden="true">MAP</span>地図で探す</h2>
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

    <!-- ── キャラクターマンホールとは（検索語のためh2は変更しない） ── -->
    <section class="lp-section" aria-labelledby="lp-about-heading">
      <h2 id="lp-about-heading"><span aria-hidden="true">WHAT IS IT</span>キャラクターマンホールとは</h2>
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
      <p class="lp-section-lead">だからこのページの「全国{total_count}枚」も、<b>まだ全部ではありません</b>。</p>
    </section>

    <!-- ── いま集まっている作品 ── -->
    <section class="lp-section" aria-labelledby="lp-works-heading">
      <h2 id="lp-works-heading"><span aria-hidden="true">WORKS</span>アニメ・キャラクターマンホールの作品別一覧</h2>
      <p class="lp-section-lead">掲載中の{work_count}作品・シリーズの枚数と都道府県を紹介。作品名から設置場所の詳しい一覧や地図へ進めます。アイマスは各シリーズをまとめて紹介しています。</p>
      <ul class="lp-work-grid">
{work_items_html}
      </ul>
    </section>

    <!-- ── 都道府県から探す ── -->
    <section class="lp-section" aria-labelledby="lp-pref-heading">
      <h2 id="lp-pref-heading"><span aria-hidden="true">PREFECTURES</span>都道府県別の設置場所一覧</h2>
      <p class="lp-section-lead">都道府県のボタンから地図へ進めます。その下の一覧を開くと、市町村・設置場所・出典を確認できます。掲載がない地域も未収録のマンホールがある場合があります。移設・撤去や施設の開放時間は訪問前に出典の案内をご確認ください。</p>
      <div class="lp-pref-list">
{pref_items_html}
      </div>
{location_directory_html}
    </section>

    <!-- ── 一覧を見た人への写真投稿導線 ── -->
    <section class="lp-section" aria-labelledby="lp-post-heading">
      <h2 id="lp-post-heading"><span aria-hidden="true">SUBMIT</span>その1枚、まだカメラロールにありますか？</h2>
      <a class="lp-promo-card" href="{DESIGN_MANHOLE_HREF}"
         onclick="trackEvent('click_design_manhole_lp',{{surface:'character_cta',from:'character_manholes_lp'}})">
        <span class="lp-promo-icon" aria-hidden="true">📸</span>
        <span>
          <strong>カメラロールの1枚を投稿する</strong>
          <p>撮ったときは「珍しいな」で終わった写真でも、場所と一緒に載せると、次に同じ街を歩く人の寄り道先になります。
          <b>キャラクターものでなくても構いません。</b>花、名所、市の鳥、消防、旧市町村名の蓋——「これは撮っておくか」と思った理由があるなら、それで十分です。
          位置情報つきの写真なら、設置場所は自動で入ります。</p>
        </span>
        <span class="lp-promo-arrow" aria-hidden="true">→</span>
      </a>
      <p class="lp-promo-sub"><a href="https://pokefuta.com/design-manholes" target="_blank" rel="noopener noreferrer">みんなの投稿を見る →</a></p>
    </section>
{latest_section_html}

    <!-- ── FAQ ── -->
    <section class="lp-section" aria-labelledby="lp-faq-heading">
      <h2 id="lp-faq-heading"><span aria-hidden="true">FAQ</span>よくある質問</h2>
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
