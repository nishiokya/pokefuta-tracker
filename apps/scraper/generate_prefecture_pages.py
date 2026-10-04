#!/usr/bin/env python3
"""Generate static Japanese landing pages for all 47 prefectures."""

from __future__ import annotations

import argparse
import json
import math
from collections import Counter
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import quote, urlparse
from xml.sax.saxutils import escape

try:
    from apps.scraper.photo_caption import poster_profile_url
except ModuleNotFoundError as exc:
    if exc.name != "apps":
        raise
    from photo_caption import poster_profile_url

try:
    from apps.scraper.display_names import compose_display_name, municipality_label
except ModuleNotFoundError as exc:
    if exc.name != "apps":
        raise
    from display_names import compose_display_name, municipality_label

try:
    from apps.scraper.prefecture_completion import build_completion, verify_known_empty
except ModuleNotFoundError as exc:
    if exc.name != "apps":
        raise
    from prefecture_completion import build_completion, verify_known_empty

try:
    from apps.scraper.municipalities import page_paths as municipality_page_paths
except ModuleNotFoundError as exc:
    if exc.name != "apps":
        raise
    from municipalities import page_paths as municipality_page_paths

try:
    from apps.scraper.prefectures import (
        PREFECTURES,
        PREFECTURE_ORDER,
        PREFECTURE_SLUGS,
        select_full_coverage_pokemon,
    )
except ModuleNotFoundError as exc:
    if exc.name != "apps":
        raise
    from prefectures import (
        PREFECTURES,
        PREFECTURE_ORDER,
        PREFECTURE_SLUGS,
        select_full_coverage_pokemon,
    )

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_MANHOLES = ROOT / "docs" / "pokefuta.ndjson"
DEFAULT_POKEMON = ROOT / "docs" / "pokemon_metadata.json"
DEFAULT_PHOTOS = ROOT / "docs" / "latest-manhole-photos.json"
DEFAULT_TRIVIA = ROOT / "dataset" / "prefecture_trivia.json"
DEFAULT_EVENTS = ROOT / "dataset" / "prefecture_events.json"
DEFAULT_GUIDES = ROOT / "dataset" / "prefecture_visit_guides.json"
JST = timezone(timedelta(hours=9))
# 現地写真の欄に並べる上限（4列×2段）。4枚だと写真が5〜8枚ある県で掲載率 100% なのに
# 1枚も2枚も欠けて見えた。全件はすぐ下の一覧にあるので、それ以上は重ねて出さない。
PHOTO_SHOWCASE_LIMIT = 8
DEFAULT_OUTPUT = ROOT / "dist" / "prefectures"
BASE_URL = "https://data.pokefuta.com"
OG_IMAGE = f"{BASE_URL}/assets/ogp/pokefuta_summary_ogp.png"
RELIABLE_FIRST_SEEN_START = datetime.fromisoformat("2025-11-01T00:00:00+00:00")

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

PREFECTURE_SEO: dict[str, dict[str, str]] = {
    "千葉県": {
        "search_name": "千葉",
        "title": "千葉のポケふた{count}枚はどこ？香取市・佐原の場所一覧と地図",
        "h1": "千葉（千葉県）のポケふた{count}枚",
        "description": (
            "千葉県のポケふた{count}枚を一覧と地図で紹介。香取市・佐原の設置場所、"
            "現地写真、佐原駅から徒歩で巡る際の起点や車での回り方を確認できます。"
        ),
    },
    "北海道": {
        "search_name": "北海道",
        "title": "北海道のポケふた最新{count}枚｜設置場所一覧・マップ",
        "h1": "北海道のポケふた最新{count}枚",
        "description": (
            "北海道にあるポケふた最新{count}枚を、市町村別の設置場所一覧と地図で紹介します。"
            "登場ポケモン、現地写真、各マンホールへの行き方も確認できます。"
        ),
    },
    "京都府": {
        "search_name": "京都",
        "title": "京都のポケふた{count}枚はどこ？京都市・宇治市の場所一覧・地図",
        "h1": "京都（京都府）のポケふた{count}枚",
        "description": (
            "京都府にあるポケふた{count}枚はどこ？京都市・宇治市の設置場所を、"
            "市別の一覧と地図、現地写真、登場ポケモンとあわせて紹介します。"
        ),
    },
    "山形県": {
        "search_name": "山形",
        "title": "山形のポケふた{count}枚｜山形市・寒河江・鶴岡などの場所一覧・地図",
        "h1": "山形（山形県）のポケふた{count}枚",
        "description": (
            "山形県のポケふた{count}枚を一覧と地図で紹介。山形駅前・寒河江・大蔵村・小国町・"
            "鶴岡市の設置場所を村山・最上・置賜・庄内の地域別に、現地写真とあわせて確認できます。"
        ),
    },
    "長崎県": {
        "search_name": "長崎",
        "title": "長崎のポケふた{count}枚｜デンリュウの設置場所一覧・地図",
        "h1": "長崎（長崎県）のポケふた{count}枚",
        "description": (
            "長崎県のデンリュウのポケふた{count}枚を一覧と地図で紹介。本土の長崎市周辺・県央・"
            "島原半島・県北と、壱岐・対馬・五島・新上五島の離島に分けて設置場所を確認できます。"
        ),
    },
    "大阪府": {
        "search_name": "大阪",
        "title": "大阪のポケふた{count}枚はどこ？東大阪市の場所一覧・地図",
        "h1": "大阪（大阪府）のポケふた{count}枚",
        "description": (
            "大阪府にあるポケふた{count}枚はどこ？東大阪市の設置場所を、"
            "一覧と地図、現地写真、登場ポケモンとあわせて紹介します。"
        ),
    },
}

# Search Console（2026-09-02〜09-29）で表示1,500回以上・CTR約1%以下、または
# 平均順位9位以下だった県。県別の文面を書く代わりに、設置市町村とポケモンを
# データから入れたタイトル・説明と、市町村別の案内を出す。京都・大阪は
# 9月22日に個別設定へ変えて測定中なので含めない。
MUNICIPALITY_SEO_PREFECTURES = frozenset({
    "青森県", "秋田県", "栃木県", "神奈川県", "新潟県", "富山県", "岐阜県",
    "兵庫県", "山口県", "徳島県", "愛媛県", "福岡県", "鹿児島県",
})

# ポケふたが無い県から近いポケふたを測る起点（県庁所在地の県庁）。
# 距離は直線で、移動距離ではない。
EMPTY_PREFECTURE_ORIGINS: dict[str, tuple[str, float, float]] = {
    "群馬県": ("群馬県庁", 36.3911, 139.0608),
    "山梨県": ("山梨県庁", 35.6639, 138.5684),
    "広島県": ("広島県庁", 34.3966, 132.4596),
    "熊本県": ("熊本県庁", 32.7898, 130.7416),
    "大分県": ("大分県庁", 33.2382, 131.6126),
}
NEAREST_POKEFUTA_LIMIT = 8


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


def load_photos(path: Path) -> dict[str, dict]:
    if not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}
    raw_photos = payload.get("photos", {}) if isinstance(payload, dict) else {}
    if not isinstance(raw_photos, dict):
        return {}
    return {
        str(manhole_id): photo
        for manhole_id, photo in raw_photos.items()
        if isinstance(photo, dict)
    }


def load_visit_guides(path: Path) -> dict[str, dict]:
    """Load curated travel advice; fail the build on malformed editorial data."""
    return json.loads(path.read_text(encoding="utf-8"))


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


def load_events(path: Path) -> dict[str, list[dict]]:
    if not path.exists():
        return {}
    try:
        entries = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    events: dict[str, list[dict]] = {}
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        prefecture = entry.get("prefecture")
        url = str(entry.get("url", "")).strip()
        if not prefecture or not entry.get("title") or not url.startswith("https://"):
            continue
        try:
            entry = {
                **entry,
                "start": date.fromisoformat(entry["start_date"]),
                "end": date.fromisoformat(entry["end_date"]),
            }
        except (KeyError, TypeError, ValueError):
            continue
        events.setdefault(prefecture, []).append(entry)
    return events


def _format_date(value: date) -> str:
    return f"{value.year}年{value.month}月{value.day}日"


def _escape_attr(value: object) -> str:
    return escape(str(value), {'"': "&quot;", "'": "&#x27;"})


def _active_events(events: list[dict] | None, today: date) -> list[dict]:
    return [e for e in events or [] if e["end"] >= today]


def _event_status(event: dict, today: date) -> str:
    return "開催中" if event["start"] <= today else "まもなく開催"


def _events_html(events: list[dict] | None, today: date | None = None) -> str:
    today = today or datetime.now(JST).date()
    active = _active_events(events, today)
    if not active:
        return ""
    items = []
    for event in active:
        status = _event_status(event, today)
        description = str(event.get("description", "")).strip()
        items.append(
            '<div class="event-item">'
            f'<span class="event-status">{escape(status)}</span>'
            f'<strong><a href="{_escape_attr(event["url"])}" target="_blank" '
            'rel="noopener noreferrer" data-track="prefecture_event_click" '
            f'data-destination="event">{escape(event["title"])}</a></strong>'
            + (f"<p>{escape(description)}</p>" if description else "")
            + '<p class="event-period">期間: '
            f'{_format_date(event["start"])}〜{_format_date(event["end"])}</p>'
            "</div>"
        )
    return (
        '<section class="event-card" aria-labelledby="event-heading">\n'
        '      <h2 id="event-heading">開催中のイベント・スタンプラリー</h2>\n'
        f'      {"".join(items)}\n'
        "    </section>\n\n    "
    )


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


def _manhole_name(record: dict) -> str:
    # 正本のマンホール名。city は公式の生の値（「町田」「台東区上野」）で、
    # 同じ自治体の蓋を区別できないので名前には使わない。
    return compose_display_name(record) or municipality_label(record) or "所在地不明"


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
                f'<a href="{_escape_attr(source_url)}" target="_blank" '
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
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            continue
        # 呼び出し側は RELIABLE_FIRST_SEEN_START や JST 基準の cutoff など
        # tz-aware な値と比較するので、タイムゾーン無しの文字列が紛れ込んでも
        # 比較で例外にならないよう UTC を補う。
        return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
    return None


def _format_year_month(date: datetime) -> str:
    return f"{date.year}年{date.month}月"


def _first_reliable_month(records: list[dict]) -> str:
    first_dates = [date for record in records if (date := _record_date(record))]
    if not first_dates:
        return ""
    first_date = min(first_dates)
    if first_date < RELIABLE_FIRST_SEEN_START:
        return ""
    return _format_year_month(first_date)


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
    first_month = _first_reliable_month(records)
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
            f'data-destination="{_escape_attr(slug)}">{content}</a>'
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


def _campaign_params(slug: str) -> str:
    """写真館（pokefuta.com）へのリンクに付ける流入元パラメータ。

    `from=data` だけだと写真館側で「図鑑から来た」ことしか分からず、
    どの都道府県ページが投稿・訪問登録に繋がったかを GA4 で追えない。
    `pref` を足して流入元の県を渡す（GA4 への送信は写真館側で別途対応）。

    内部導線を外部キャンペーンとして扱わないよう utm_* は使わず、
    クロスドメインリンカーと独自の流入元パラメータを使う。
    """
    if not slug:
        return "from=data"
    return f"from=data&pref={quote(slug)}"


def _upload_url(manhole_id: str, slug: str) -> str:
    return (
        "https://pokefuta.com/upload?"
        f"manhole_id={quote(manhole_id)}&{_campaign_params(slug)}"
    )


def _visits_url(slug: str) -> str:
    return f"https://pokefuta.com/visits?{_campaign_params(slug)}"


def _nearby_url(slug: str) -> str:
    return f"https://pokefuta.com/nearby?{_campaign_params(slug)}"


def _google_maps_url(record: dict) -> str:
    lat = record.get("lat")
    lng = record.get("lng")
    if not isinstance(lat, (int, float)) or not isinstance(lng, (int, float)):
        return ""
    return f"https://www.google.com/maps?q={lat},{lng}"


def _photo_asset_url(record: dict, photo: dict) -> str:
    manhole_id = str(record.get("id", "")).strip()
    local_image = ROOT / "dataset" / "manhole" / "image" / f"{manhole_id}_latest.jpeg"
    if manhole_id and local_image.exists():
        return f"/manhole/image/{quote(manhole_id)}_latest.jpeg"
    # The snapshot's original URL is an unsigned R2 S3 endpoint, not a public
    # delivery URL. A missing local download must degrade to "no photo".
    return ""


def _photo_entries(
    records: list[dict], photos: dict[str, dict]
) -> list[tuple[dict, dict]]:
    entries = []
    for record in records:
        photo = photos.get(str(record.get("id", "")))
        if photo and _photo_asset_url(record, photo):
            entries.append((record, photo))
    return sorted(
        entries,
        key=lambda item: str(item[1].get("created_at", "")),
        reverse=True,
    )


def _split_photographed(
    records: list[dict], photos: dict[str, dict]
) -> tuple[list[tuple[dict, dict]], list[dict]]:
    """(photo_entries, unphotographed_records) — the same "id は撮影済み
    集合に無い" 差分判定を、詳細ページの写真セクションと /prefectures/
    一覧のギャラリーの両方で使う。"""
    entries = _photo_entries(records, photos)
    photo_ids = {str(record.get("id", "")) for record, _ in entries}
    unphotographed = [
        record for record in records
        if str(record.get("id", "")) not in photo_ids
    ]
    return entries, unphotographed


def _photo_section(
    prefecture: str,
    slug: str,
    records: list[dict],
    photos: dict[str, dict],
) -> str:
    installed_records = [
        record for record in records if record.get("installed") is not False
    ]
    total = len(installed_records)
    entries, unphotographed_records = _split_photographed(installed_records, photos)
    with_photo = len(entries)
    missing = max(total - with_photo, 0)
    coverage = round(with_photo / total * 100) if total else 0

    if total == 0:
        return (
            '<div class="photo-empty-state">'
            f'<strong>{escape(prefecture)}の設置情報を追跡中です</strong>'
            '<p>設置を確認でき次第、地図・詳細・写真投稿先をこのページへ追加します。</p>'
            '<a class="inline-link" href="/summary/" '
            'data-track="prefecture_summary_click" data-destination="summary">'
            '全国のポケふたを見る</a></div>'
        )

    if coverage >= 65:
        lead = "現地写真から、次に訪れたいポケふたを選べます。"
    elif with_photo:
        lead = "現地写真が集まり始めています。旅の記録を次の人の目印にしてください。"
    else:
        lead = "設置場所は地図と一覧で確認できます。現地で撮った最初の1枚を募集中です。"

    gallery_cards = []
    for position, (record, photo) in enumerate(entries[:PHOTO_SHOWCASE_LIMIT], start=1):
        mid = str(record.get("id", "")).strip()
        name = _manhole_name(record)
        pokemons = "・".join(_clean_pokemons(record)) or "ポケモン"
        poster = str(photo.get("display_name", "") or "").strip()
        profile_url = poster_profile_url(photo.get("public_user_id"))
        if profile_url:
            profile_url = f"{profile_url}?{_campaign_params(slug)}"
        poster_html = ""
        if poster:
            if profile_url:
                poster_html = (
                    f'<small class="photo-card-poster"><a href="{_escape_attr(profile_url)}" '
                    f'target="_blank" rel="noopener noreferrer" '
                    f'aria-label="{_escape_attr(poster)}さんの公開スタンプ帳を開く">'
                    f'{escape(poster)}さんの投稿</a></small>'
                )
            else:
                poster_html = f'<small class="photo-card-poster">{escape(poster)}さんの投稿</small>'
        gallery_cards.append(
            f'<article class="photo-card">'
            f'<a class="photo-card-image" href="/manholes/{quote(mid)}/" '
            f'data-track="prefecture_photo_click" data-position="{position}" '
            f'data-destination="{_escape_attr(mid)}" data-surface="photo_gallery">'
            f'<img src="{_escape_attr(_photo_asset_url(record, photo))}" '
            f'alt="{_escape_attr(name)}のポケふた投稿写真" '
            f'loading="lazy" decoding="async" width="640" height="480">'
            f'<span><strong>{escape(name)}</strong><small>{escape(pokemons)}</small>'
            f'</span></a>{poster_html}'
            f'<a class="photo-card-upload" href="{_escape_attr(_upload_url(mid, slug))}" '
            f'data-track="prefecture_photo_upload_start" data-position="{position}" '
            f'data-destination="upload" data-content-id="{_escape_attr(mid)}" '
            f'data-surface="photo_gallery" '
            f'data-photo-state="has_photo">このポケふたに写真を追加</a>'
            f'</article>'
        )
    gallery_html = (
        f'<div class="photo-showcase-grid">{"".join(gallery_cards)}</div>'
        if gallery_cards else ""
    )

    missing_records = unphotographed_records[:3]
    contribution_cards = []
    for position, record in enumerate(missing_records, start=1):
        mid = str(record.get("id", "")).strip()
        name = _manhole_name(record)
        pokemons = "・".join(_clean_pokemons(record)) or "ポケモン"
        contribution_cards.append(
            f'<a class="contribution-card" href="{_escape_attr(_upload_url(mid, slug))}" '
            f'data-track="prefecture_photo_upload_start" data-position="{position}" '
            f'data-destination="upload" data-content-id="{_escape_attr(mid)}" '
            f'data-surface="photo_contribution" '
            f'data-photo-state="missing">'
            f'<span>写真募集中</span><strong>{escape(name)}</strong>'
            f'<small>{escape(pokemons)}</small><b>最初の写真を投稿 →</b></a>'
        )
    contribution_html = (
        '<div class="contribution-panel">'
        f'<div><strong>写真未掲載のポケふたは{missing}地点</strong>'
        '<p>対象を選んだ後にログインします。投稿写真は詳細ページとこの県ページに掲載されます。</p></div>'
        f'<div class="contribution-grid">{"".join(contribution_cards)}</div></div>'
        if missing_records
        # 全点に写真が付いた県で出していた「すべてのポケふたに現地写真が
        # あります」の帯は出さない。すぐ上の掲載率バーが 100% を出していて
        # 情報が重複するうえ、帯の CTA はヒーローの「投稿するポケふたを選ぶ」
        # と同じ #manhole-list 行きで、導線としても増えていなかった。
        else ""
    )
    return (
        '<div class="photo-inventory">'
        f'<div><strong>{with_photo}<span> / {total}地点</span></strong>'
        f'<p>{escape(lead)}</p></div>'
        '<div class="coverage-meter" role="meter" aria-label="現地写真の掲載率" '
        f'aria-valuemin="0" aria-valuemax="100" aria-valuenow="{coverage}">'
        f'<span style="width:{coverage}%"></span></div><b>{coverage}%</b></div>'
        f'{gallery_html}{contribution_html}'
    )


def _manhole_cards(
    records: list[dict], photos: dict[str, dict] | None = None, slug: str = ""
) -> str:
    photos = photos or {}
    if not records:
        return '<p class="empty-state">現在、この都道府県のポケふたは未設置です。</p>'
    cards = []
    for position, record in enumerate(
        sorted(records, key=lambda item: (item.get("city", ""), str(item.get("id", "")))),
        start=1,
    ):
        mid = str(record.get("id", "")).strip()
        display_name = _manhole_name(record)
        pokemons = "・".join(_clean_pokemons(record)) or "ポケモン"
        image_path = ROOT / "dataset" / "manhole" / "image" / f"{mid}_latest.jpeg"
        image_html = (
            f'<img src="/manhole/image/{quote(mid)}_latest.jpeg" '
            f'alt="{_escape_attr(display_name)}のポケふた" loading="lazy" decoding="async" '
            f'width="720" height="720">'
            if image_path.exists()
            # 写真館（マイ旅・探す）の写真無しタイルと同じストライプ。
            else '<span class="manhole-placeholder" aria-hidden="true"></span>'
        )
        preinstall_badge_html = (
            '<span class="manhole-preinstall-badge">🚧 設置前</span>'
            if record.get("installed") is False
            else ""
        )
        is_preinstall = record.get("installed") is False
        has_photo = (
            not is_preinstall
            and mid in photos
            and bool(_photo_asset_url(record, photos[mid]))
        )
        photo_label = (
            "設置後に投稿可能"
            if is_preinstall
            else ("投稿写真あり" if has_photo else "写真募集中")
        )
        photo_class = (
            " photo-pending"
            if is_preinstall
            else (" photo-ready" if has_photo else " photo-needed")
        )
        upload_label = "写真を追加" if has_photo else "写真を投稿"
        maps_url = _google_maps_url(record)
        # 蓋の写真そのものが詳細への導線になったので、カード内に「詳細」
        # ボタンは置かない（写真館が /nearby のタイルから「経路を見る」を外し、
        # タイル全体を詳細リンクにしたのと同じ整理）。
        maps_html = (
            f'<a href="{_escape_attr(maps_url)}" target="_blank" rel="noopener noreferrer" '
            f'data-track="prefecture_google_maps_click" data-position="{position}" '
            f'data-destination="google_maps" data-content-id="{_escape_attr(mid)}" '
            f'data-surface="manhole_actions">地図で開く</a>'
            if maps_url else ""
        )
        upload_html = (
            f'<a class="upload" href="{_escape_attr(_upload_url(mid, slug))}" '
            f'data-track="prefecture_photo_upload_start" data-position="{position}" '
            f'data-destination="upload" data-content-id="{_escape_attr(mid)}" '
            f'data-surface="manhole_actions" '
            f'data-photo-state="{"has_photo" if has_photo else "missing"}">{upload_label}</a>'
            if not is_preinstall else ""
        )
        actions_class = "manhole-actions preinstall-actions" if is_preinstall else "manhole-actions"
        actions_html = (
            f'<div class="{actions_class}">{maps_html}{upload_html}</div>'
            if maps_html or upload_html else ""
        )
        cards.append(
            f'<article class="manhole-card" data-manhole-id="{_escape_attr(mid)}" '
            f'id="manhole-{_escape_attr(mid)}">'
            f'<a class="manhole-detail" href="/manholes/{quote(mid)}/" '
            f'data-track="prefecture_manhole_click" data-position="{position}" '
            f'data-destination="{_escape_attr(mid)}" data-content-id="{_escape_attr(mid)}" '
            f'data-surface="manhole_card">'
            f'{image_html}<span class="manhole-shade" aria-hidden="true"></span>'
            f'<span class="manhole-badges">{preinstall_badge_html}'
            f'<b class="photo-status{photo_class}">{photo_label}</b></span>'
            f'<span class="manhole-copy"><strong>{escape(display_name)}</strong>'
            f'<small>{escape(pokemons)}</small></span></a>'
            f'{actions_html}</article>'
        )
    return "".join(cards)


def _related_prefectures(
    prefecture: str, empty_prefectures: set[str] | None = None
) -> str:
    """同じ地方の都道府県への導線。

    `empty_prefectures` を渡すと、ポケふたが1枚も無い県をリンクから外す。
    大分→熊本のように、行き止まりから行き止まりへ送るのを防ぐため
    （どちらも0枚で、実測の engagementRate は 0.28 と 0.30）。
    渡さないときは従来どおり地方の全県を並べる。
    """
    empty_prefectures = empty_prefectures or set()
    region_name = ""
    region_prefs: list[str] = []
    for name, prefectures in REGIONS:
        if prefecture in prefectures:
            region_name = name
            region_prefs = prefectures
            break
    links = "".join(
        f'<a href="/prefectures/{PREFECTURE_SLUGS[name]}/" '
        f'data-track="prefecture_related_click" '
        f'data-destination="{PREFECTURE_SLUGS[name]}">{escape(name)}</a>'
        for name in region_prefs
        if name != prefecture and name not in empty_prefectures
    )
    if not links:
        return ""
    return (
        f'<p class="related-label">{escape(region_name)}のポケふた</p>'
        f'<div class="related-links">{links}</div>'
    )


def _index_card_trivia_html(trivia_entry: dict | None) -> str:
    """都道府県トリビア（/summary/ の _build_prefecture_info_section と同じ
    データ源・同じ内容、同じ pokemon_coverage 選定ロジックを
    select_full_coverage_pokemon() として共有）。トリビアが無い都道府県は
    静かに何も足さない — summary 側の記録件数ベースの代替文言まで複製すると
    2箇所の言い回しがズレていく元になるので、ここでは「データがある分だけ
    載せる」に留める。

    ポケモンバッジ（pokemon_html）は trivia の有無と無関係に判定する。
    summary 側の _build_prefecture_info_section も同様に、facts が無くても
    バッジだけは出す作りなので、ここで trivia_list が空だからと一緒に
    握りつぶすと2ページの内容がズレる。
    """
    top_coverage = select_full_coverage_pokemon(
        (trivia_entry or {}).get("pokemon_coverage", [])
    )
    top_coverage_label = (top_coverage or {}).get("label")
    pokemon_html = (
        f'<p class="prefecture-card-trivia-pokemon">'
        f'<span class="prefecture-card-trivia-label">都道府県トリビア</span>'
        f'{escape(top_coverage_label)}</p>'
        if top_coverage_label else ""
    )
    trivia_list = (trivia_entry or {}).get("trivia", [])
    facts_html = "".join(
        f"<li>{escape(entry['text'])}</li>"
        for entry in trivia_list[:3]
        if entry.get("text")
    )
    if not pokemon_html and not facts_html:
        return ""
    facts_block = (
        f'<ul class="prefecture-card-trivia-facts">{facts_html}</ul>'
        if facts_html else ""
    )
    return (
        '<div class="prefecture-card-trivia">'
        f"{pokemon_html}"
        f"{facts_block}"
        "</div>"
    )


def _index_card_campaign_html(
    events_list: list[dict] | None, today: date | None = None
) -> str:
    """開催中スタンプラリー等の告知を、詳細ページの _events_html() と同じ
    データ源（dataset/prefecture_events.json）・同じ判定ロジック
    （_active_events()/_event_status()）から1行の告知バッジとして出す。
    詳細（期間・説明文）は引き続き詳細ページ側だけの役割。"""
    today = today or datetime.now(JST).date()
    active = _active_events(events_list, today)
    if not active:
        return ""
    event = active[0]
    status = _event_status(event, today)
    return (
        f'<a class="prefecture-card-campaign" href="{_escape_attr(event["url"])}" '
        'target="_blank" rel="noopener noreferrer" '
        'data-track="prefectures_index_campaign_click">'
        f'🎫 {status}: {escape(event["title"])}</a>'
    )


def build_index_page(
    records_by_pref: dict[str, list[dict]],
    photos: dict[str, dict] | None = None,
    trivia: dict[str, dict] | None = None,
    events: dict[str, list[dict]] | None = None,
) -> str:
    """Generate /prefectures/index.html — the real destination for every
    "都道府県から探す" link site-wide (top page quicklink/stat tile, shared
    header nav, SP tab bar). Those all used to point at the top page's
    #sec-pref anchor because this page didn't exist yet.

    Cards started as a close mirror of map.html's own prefecture picker
    panel (code badge, NEW badge, count badge), and real-device feedback
    then asked for more than that panel shows: every real photo (not
    capped at 8 like map.html's row), a visible city/municipality name per
    photo, an explicit "detail page" link (the whole card was already a
    link, but that wasn't obvious enough on a phone), and any active
    campaign/event for the prefecture. The gallery is now a small photo
    grid with captions rather than map.html's circular icon row, since a
    caption doesn't read well on a 54px circle. The card's main action
    still differs from map.html's version on purpose: there it filters
    the in-app map; here, on a static page with no map state to filter,
    the whole card (plus the explicit link at the bottom) links straight
    to the prefecture's detail page.

    Also carries the same 都道府県トリビア content /summary/'s prefecture
    cards show (dataset/prefecture_trivia.json via load_trivia()) — same
    source, same text, deliberately not re-derived or reworded — and the
    same active-campaign data prefecture detail pages show
    (dataset/prefecture_events.json via load_events()), as a compact
    one-line badge instead of the detail page's full description+dates.
    """
    photos = photos or {}
    trivia = trivia or {}
    events = events or {}
    total = sum(len(records) for records in records_by_pref.values())
    # マンホールが1枚も無い都道府県はこのページに出さない（region_section()
    # 側の実際のフィルタと二重管理にならないよう、ここでは案内文の数字だけ
    # 同じ条件で数える）。
    listed_count = sum(1 for records in records_by_pref.values() if records)
    # 県単位のコンプリート状況。残り枚数（全国で十数枚）は動きが遅くて
    # 進捗として読めないが、残っているのは少数の県に固まっているので
    # 「残りN県」なら1県埋まるたびに数字が動く。
    completion = build_completion(
        records_by_pref,
        {str(manhole_id) for manhole_id in photos},
        order=PREFECTURE_ORDER,
    )
    canonical = f"{BASE_URL}/prefectures/"
    title = "都道府県から探す｜全国のポケふた一覧"
    description = (
        f"ポケふたの情報がある{listed_count}都道府県、計{total}枚（ポケモンマンホール）を都道府県別に探せます。"
        f"現地写真がそろっているのは{completion.complete_count}都道府県。"
        "地方ごとにまとめた一覧から、行き先の設置数と詳細ページを確認できます。"
    )
    recent_cutoff = datetime.now(JST) - timedelta(days=30)

    def prefecture_card(name: str) -> str:
        records = records_by_pref.get(name, [])
        count = len(records)
        code = f"{PREFECTURE_ORDER.index(name) + 1:02d}"
        slug = PREFECTURE_SLUGS[name]
        # installed:false（設置予定・未設置）は "実際にそこにある1枚" の証拠として
        # 数えない。_manhole_cards / map_points と同じ規約（このファイル内で
        # 繰り返し使われている `installed is not False` フィルタ）に合わせる。
        installed_records = [r for r in records if r.get("installed") is not False]
        recent_count = sum(
            1 for record in installed_records
            if (added := _record_date(record)) and added >= recent_cutoff
        )
        # region_section() が count==0 の都道府県を呼び出し元で除外しているので
        # ここに来る時点で count は常に1以上。
        new_badge_html = (
            '<span class="prefecture-new-badge">'
            '<img src="/assets/icon-fire.svg" alt="" aria-hidden="true">NEW</span>'
            if recent_count else ""
        )
        # 「あと何枚でこの県が終わるか」をカードの時点で見せる。ギャラリーに
        # 「写真募集中」タイルは並ぶが、それを数えないと残りが分からなかった。
        entry = completion.by_prefecture(name)
        if entry is None:
            completion_badge_html = ""
        elif entry.is_complete:
            completion_badge_html = (
                '<span class="prefecture-complete-badge">写真コンプリート</span>'
            )
        else:
            completion_badge_html = (
                f'<span class="prefecture-remaining-badge">あと{entry.missing}枚</span>'
            )
        # 実機フィードバック: 8枚に絞らず実在する写真は全部出す。キャプションは
        # 正本のマンホール名 compose_display_name()（地図の見出しと同じ。
        # 同一自治体で重複するものは place_label で区別済み、曖昧なものはポケモン名付き）。
        # 施設名の無い一意な蓋は title の「宮城県/加美町」になり、都道府県ごとの
        # カードでも県名が付くが、名前はどの画面でも同じにする方針なので削らない。
        def _caption(record: dict) -> str:
            # title も無いレコードだけ、住所から復元した自治体名（「指宿」→「指宿市」）に落とす
            return compose_display_name(record) or municipality_label(record) or name

        photographed, unphotographed_records = _split_photographed(installed_records, photos)
        unphotographed = sorted(
            unphotographed_records,
            key=lambda r: (r.get("city", ""), str(r.get("id", ""))),
        )
        gallery_items = [
            f'<a class="prefecture-card-photo" href="/manholes/{quote(str(record.get("id", "")))}/" '
            f'aria-label="{_escape_attr(_caption(record))}のポケふたの詳細を開く">'
            f'<img src="{_escape_attr(_photo_asset_url(record, photo))}" alt="" loading="lazy" decoding="async">'
            f'<span class="prefecture-card-photo-city" aria-hidden="true">'
            f'{escape(_caption(record))}</span></a>'
            for record, photo in photographed
        ]
        gallery_items += [
            f'<a class="prefecture-card-photo prefecture-card-photo-needed" '
            f'href="/manholes/{quote(str(record.get("id", "")))}/" '
            f'aria-label="{_escape_attr(_caption(record))}のポケふた（写真募集中）の詳細を開く">'
            '<span class="prefecture-card-photo-placeholder" aria-hidden="true">写真募集中</span>'
            f'<span class="prefecture-card-photo-city" aria-hidden="true">'
            f'{escape(_caption(record))}</span></a>'
            for record in unphotographed
        ]
        gallery_html = "".join(gallery_items) or '<p class="prefecture-card-photo-empty">まだ投稿写真がありません</p>'
        trivia_html = _index_card_trivia_html(trivia.get(name))
        campaign_html = _index_card_campaign_html(events.get(name))
        detail_link_html = (
            f'<a class="prefecture-card-detail-link" href="/prefectures/{slug}/" '
            f'data-track="prefectures_index_detail_click" data-destination="{slug}">'
            f'{escape(name)}の詳細を見る →</a>'
        )
        return f"""<article class="prefecture-card" data-track="prefectures_index_click" data-destination="{slug}">
      <a class="prefecture-card-main" href="/prefectures/{slug}/">
        <span class="prefecture-code">{code}</span>
        <span class="prefecture-card-name">{escape(name)}</span>
        <span class="prefecture-card-meta">{completion_badge_html}{new_badge_html}</span>
        <span class="count-badge">{count}枚</span>
      </a>
      {campaign_html}
      {trivia_html}
      <div class="prefecture-card-gallery" aria-label="{_escape_attr(name)}のマンホール写真">{gallery_html}</div>
      {detail_link_html}
    </article>"""

    def region_section(region_name: str, prefectures: list[str]) -> str:
        # マンホールが1枚もない都道府県はこの一覧では非表示にする（詳細
        # ページ自体は今後の設置に備えて引き続き生成する）。ここでの
        # 条件は「レコードが1件でもある」で、installed:false（設置予定）
        # だけの都道府県も対象に含む — "installed" という名前は誤解を招く
        # ので listed とする。
        listed = [name for name in prefectures if records_by_pref.get(name)]
        if not listed:
            return ""
        cards = "".join(prefecture_card(name) for name in listed)
        anchor_id = f"region-{PREFECTURE_SLUGS[listed[0]]}"
        return (
            f'<section aria-labelledby="{anchor_id}">'
            f'<h2 id="{anchor_id}" class="region-heading">{escape(region_name)}</h2>'
            f'<div class="prefecture-card-list">{cards}</div>'
            "</section>"
        )

    regions_html = "".join(region_section(name, prefs) for name, prefs in REGIONS)

    # 実機フィードバック: SPだと写真が多い都道府県のカードがかなり長く、
    # 目的の地方まで延々スクロールすることになる。ページ上部に地方への
    # ジャンプリンクを置く（region_section() と同じ「都道府県が1つも
    # 残らない地方は出さない」条件に揃える）。
    region_nav_items = "".join(
        f'<a href="#region-{PREFECTURE_SLUGS[listed[0]]}">{escape(region_name)}</a>'
        for region_name, prefectures in REGIONS
        if (listed := [name for name in prefectures if records_by_pref.get(name)])
    )
    region_nav_html = (
        f'<nav class="region-jump-nav" aria-label="地方から探す">{region_nav_items}</nav>'
        if region_nav_items else ""
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
    .index-hero {{ margin: 14px 0 28px; }}
    .index-hero h1 {{ margin: 0 0 10px; font-size: 1.6rem; }}
    .index-hero p {{ margin: 0; color: #75685c; }}
    .region-jump-nav {{
      display: flex; gap: 6px; overflow-x: auto; padding: 10px 0 4px;
      -webkit-overflow-scrolling: touch; scrollbar-width: none;
    }}
    .region-jump-nav::-webkit-scrollbar {{ display: none; }}
    .region-jump-nav a {{
      flex: 0 0 auto; padding: 6px 12px; border-radius: 999px;
      background: #fff; border: 1px solid rgba(93,67,35,.15);
      color: #57408f; font-size: .78rem; font-weight: 850; text-decoration: none;
      white-space: nowrap;
    }}
    .region-heading {{
      margin: 28px 0 12px; font-size: 1.05rem; font-weight: 850;
      color: #14544f;
    }}
    /* 以下、map.html の都道府県パネル（pokefuta-map.css の
       .pokefuta-map-page .prefecture-card* / .count-badge*）と
       見た目を揃えるためのカードスタイル。あちらはSPAの絞り込みUIで
       このページには地図の状態が無いため、カード全体を詳細ページへの
       リンクにしている点だけ差分。 */
    .prefecture-card-list {{ display: grid; gap: 10px; }}
    .prefecture-card {{
      min-height: 72px; border: 1px solid rgba(116,82,38,.17); border-radius: 12px;
      background: rgba(255,250,239,.94); box-shadow: 0 7px 18px rgba(80,54,20,.08);
      overflow: hidden;
    }}
    .prefecture-card-main {{
      display: grid; grid-template-columns: 42px minmax(0,1fr) minmax(96px,auto) auto;
      align-items: center; gap: 10px; width: 100%; min-height: 56px;
      padding: 12px 12px 8px; text-decoration: none; color: inherit;
    }}
    .prefecture-card-meta {{
      display: inline-flex; align-items: center; justify-content: flex-end;
      min-width: 0; gap: 7px; color: #75685c; font-size: .72rem; font-weight: 850;
      white-space: nowrap;
    }}
    .prefecture-new-badge {{
      display: inline-flex; align-items: center; gap: 3px; min-height: 24px; padding: 0 8px;
      border: 1px solid rgba(243,109,54,.34); border-radius: 999px;
      background: rgba(243,109,54,.1); color: #d65526; font-size: .68rem; font-weight: 950;
    }}
    .prefecture-new-badge img {{ width: 14px; height: 14px; }}
    /* /summary/ の .prefecture-info-* と同じ都道府県トリビア（出典は
       dataset/prefecture_trivia.json、内容は完全に同じ）。クラス名だけ
       このページのカード体系（.prefecture-card-*）に合わせている。 */
    .prefecture-card-trivia {{ padding: 0 12px 10px; }}
    .prefecture-card-trivia-pokemon {{ margin: 0 0 4px; color: #574b41; font-size: .78rem; font-weight: 800; }}
    .prefecture-card-trivia-label {{
      display: inline-flex; width: fit-content; margin-right: 5px; padding: 1px 6px;
      border-radius: 999px; background: #eee7fb; color: #57408f; font-size: .62rem;
      font-weight: 900; vertical-align: 1px;
    }}
    .prefecture-card-trivia-facts {{ margin: 0; padding-left: 1.1rem; color: #716154; font-size: .72rem; line-height: 1.4; }}
    .prefecture-card-trivia-facts li + li {{ margin-top: .3rem; }}
    /* 実機フィードバックで「写真は全部・市町村名も出したい」と分かった
       ので、地図パネル風の丸アイコン列（.prefecture-card-thumb）から
       キャプション付きの小さな写真グリッドに変更した。 */
    .prefecture-card-gallery {{
      display: grid; grid-template-columns: repeat(auto-fill, minmax(72px, 1fr));
      gap: 8px; padding: 4px 12px 12px;
    }}
    .prefecture-card-photo {{
      display: flex; flex-direction: column; align-items: center; gap: 3px;
      text-decoration: none; color: #574b41; min-width: 0;
    }}
    .prefecture-card-photo img {{
      width: 100%; aspect-ratio: 1; object-fit: cover; border-radius: 10px;
      border: 2px solid rgba(255,255,255,.95); box-shadow: 0 4px 10px rgba(67,38,111,.16);
    }}
    .prefecture-card-photo:hover img, .prefecture-card-photo:focus-visible img {{
      box-shadow: 0 6px 14px rgba(67,38,111,.24), 0 0 0 3px rgba(118,84,170,.18);
      outline: 0;
    }}
    .prefecture-card-photo-city {{
      max-width: 100%; font-size: .66rem; font-weight: 800; text-align: center;
      overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
    }}
    .prefecture-card-photo-placeholder {{
      display: flex; align-items: center; justify-content: center; width: 100%;
      aspect-ratio: 1; border-radius: 10px; border: 2px dashed rgba(126,107,169,.3);
      background: rgba(126,107,169,.06); color: #8a7fa8; font-size: .62rem;
      font-weight: 800; text-align: center; padding: 4px;
    }}
    .prefecture-card-photo-empty {{ margin: 0; padding: 0 12px 12px; color: #75685c; font-size: .78rem; }}
    .prefecture-card-campaign {{
      display: block; margin: 0 12px 8px; padding: 6px 10px; border-radius: 10px;
      background: rgba(243,109,54,.1); color: #b8481f; font-size: .74rem; font-weight: 850;
      text-decoration: none;
    }}
    .prefecture-card-detail-link {{
      display: block; margin: 4px 12px 12px; padding: 8px 10px; border-radius: 10px;
      background: rgba(126,107,169,.1); color: #57408f; font-size: .8rem; font-weight: 900;
      text-align: center; text-decoration: none;
    }}
    .prefecture-code {{
      display: inline-grid; min-width: 34px; min-height: 30px; place-items: center;
      border-radius: 8px; background: linear-gradient(135deg, #7e6ba9, #6d55a3); color: #fff;
      box-shadow: inset 0 -2px 0 rgba(0,0,0,.12); font-size: .78rem; font-weight: 900;
    }}
    .prefecture-card-name {{ min-width: 0; color: #191613; font-size: 1rem; font-weight: 900; }}
    .prefecture-complete-badge {{
      display: inline-flex; align-items: center; padding: 2px 8px; border-radius: 999px;
      font-size: .68rem; font-weight: 900; background: rgba(58,148,106,.14); color: #2f7a57;
      white-space: nowrap;
    }}
    .prefecture-remaining-badge {{
      display: inline-flex; align-items: center; padding: 2px 8px; border-radius: 999px;
      font-size: .68rem; font-weight: 900; background: rgba(243,109,54,.14); color: #b8481f;
      white-space: nowrap;
    }}
    .count-badge {{
      display: inline-flex; align-items: center; justify-content: center; min-width: 56px;
      min-height: 30px; padding: 0 10px; border-radius: 999px; font-size: .88rem; font-weight: 900;
      background: rgba(126,107,169,.14); color: #654aa0;
    }}
    footer {{ margin-top: 24px; color: #75685c; font-size: .8rem; text-align: center; }}
  </style>
</head>
<body>
  <main class="page">
    <nav class="breadcrumb" aria-label="パンくず">
      <a href="/">全国マップ</a><span>›</span>
      <span>都道府県から探す</span>
    </nav>
    <header class="index-hero">
      <h1>都道府県から探す</h1>
      <p>ポケふたの情報がある{listed_count}都道府県、計{total}枚を地方別にまとめました。行き先を選んで詳細ページへ。<a href="/municipalities/">市区町村別のランキング</a>もあります。</p>
    </header>
    {region_nav_html}

    <!-- adsense:prefecture -->

    {regions_html}
    <footer><a href="/summary/">全国のポケふた一覧へ戻る</a></footer>
  </main>
  <script src="/assets/analytics.js?v=20260929a"></script>
  <script>
    window.PokefutaAnalytics.init({{
      page_path: '/prefectures/',
      site_type: 'map',
      page_type: 'prefecture_index'
    }});
    window.PokefutaAnalytics.bindClickTracking({{
      event_category: 'prefecture_growth',
      surface: 'prefectures_index'
    }});
  </script>
</body>
</html>
"""


def _prefecture_official_url(records: list[dict]) -> str:
    for record in records:
        candidate = str(record.get("prefecture_site_url", "") or "").strip()
        if not candidate:
            continue
        try:
            parsed = urlparse(candidate)
        except ValueError:
            continue
        if parsed.scheme == "https" and parsed.netloc == "local.pokemon.jp":
            return candidate
    return ""


def _municipality_counts(records: list[dict]) -> list[tuple[str, int]]:
    counts: Counter[str] = Counter()
    for record in records:
        label = municipality_label(record) or str(record.get("city", "")).strip()
        if label:
            counts[label] += 1
    return sorted(counts.items(), key=lambda item: (-item[1], item[0]))


def _short_prefecture_name(prefecture: str) -> str:
    if prefecture == "北海道":
        return prefecture
    return prefecture.removesuffix("県").removesuffix("府").removesuffix("都")


def _seo_config(prefecture: str, records: list[dict]) -> dict[str, str] | None:
    """個別設定、または対象県なら設置データから作るタイトル・説明。"""
    config = PREFECTURE_SEO.get(prefecture)
    if config or prefecture not in MUNICIPALITY_SEO_PREFECTURES:
        return config
    municipalities = [name for name, _ in _municipality_counts(records)]
    if not municipalities:
        return None
    short = _short_prefecture_name(prefecture)
    title_places = "・".join(municipalities[:3]) + ("など" if len(municipalities) > 3 else "")
    pokemons = list(dict.fromkeys(
        name for record in records for name in _clean_pokemons(record)
    ))
    pokemon_text = (
        "、" + "・".join(pokemons[:3]) + ("など" if len(pokemons) > 3 else "")
        + "の描かれたデザイン"
        if pokemons else ""
    )
    # str.format に渡すので、データ由来の波括弧はエスケープする。
    def literal(text: str) -> str:
        return text.replace("{", "{{").replace("}", "}}")
    return {
        "search_name": short,
        "title": f"{literal(short)}のポケふた{{count}}枚はどこ？{literal(title_places)}の場所一覧・地図",
        "h1": f"{literal(short)}（{literal(prefecture)}）のポケふた{{count}}枚",
        "description": (
            f"{literal(prefecture)}のポケふた{{count}}枚を一覧と地図で紹介。"
            f"{literal('・'.join(municipalities))}の設置場所と住所"
            f"{literal(pokemon_text)}を確認できます。"
        ),
    }


def _distance_km(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    dlat = math.radians(lat2 - lat1)
    dlng = math.radians(lng2 - lng1)
    a = (
        math.sin(dlat / 2) ** 2
        + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlng / 2) ** 2
    )
    return 6371.0 * 2 * math.asin(math.sqrt(a))


def _nearest_pokefuta(
    prefecture: str, all_records: list[dict] | None
) -> list[tuple[float, dict]]:
    """ポケふたが無い県の県庁から、直線距離が近い設置済みのポケふた。"""
    origin = EMPTY_PREFECTURE_ORIGINS.get(prefecture)
    if not origin or not all_records:
        return []
    _, lat, lng = origin
    candidates = [
        (_distance_km(lat, lng, record["lat"], record["lng"]), record)
        for record in all_records
        if record.get("installed") is not False
        and record.get("prefecture") != prefecture
        and isinstance(record.get("lat"), (int, float))
        and isinstance(record.get("lng"), (int, float))
    ]
    candidates.sort(key=lambda item: (item[0], str(item[1].get("id", ""))))
    return candidates[:NEAREST_POKEFUTA_LIMIT]


def _nearest_prefectures(nearest: list[tuple[float, dict]]) -> list[str]:
    return list(dict.fromkeys(str(record.get("prefecture", "")) for _, record in nearest))


def _prefecture_seo(
    prefecture: str,
    count: int,
    records: list[dict] | None = None,
    nearest: list[tuple[float, dict]] | None = None,
) -> tuple[str, str, str]:
    config = _seo_config(prefecture, records or [])
    if config and count:
        values = {key: value.format(count=count) for key, value in config.items()}
        return values["title"], values["description"], values["h1"]

    if not count and nearest:
        short = _short_prefecture_name(prefecture)
        near_prefectures = _nearest_prefectures(nearest)
        near = "・".join(_short_prefecture_name(name) for name in near_prefectures[:3])
        # 8枚が4県以上にまたがるとき（広島→島根・愛媛・香川・高知）、3県だけ挙げて
        # 「その県のポケふた8枚」と読める書き方にしない。
        if len(near_prefectures) > 3:
            near += "など"
        office = EMPTY_PREFECTURE_ORIGINS[prefecture][0]
        return (
            f"{short}のポケふたは？県内は未設置｜近くの{near}の場所一覧",
            (
                f"{prefecture}には現在ポケふたが設置されていません。"
                f"{office}から直線距離が近い順に、{near}のポケふた"
                f"{len(nearest)}枚の場所とポケモンを紹介します。"
            ),
            f"{prefecture}のポケふた",
        )

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
    return title, description, f"{prefecture}のポケふた"


def _municipality_link_item(name: str, count: int, path: str | None) -> str:
    label = (
        f'<a href="{_escape_attr(path)}" data-track="prefecture_municipality_click" '
        f'data-surface="municipality_guide" data-destination="{_escape_attr(path)}">'
        f'<strong>{escape(name)}</strong></a>'
        if path else f'<strong>{escape(name)}</strong>'
    )
    return f'<li>{label}<span>{count}枚</span></li>'


def _municipality_guide(
    prefecture: str, records: list[dict], municipality_paths: dict[str, str] | None = None
) -> str:
    config = _seo_config(prefecture, records)
    municipalities = _municipality_counts(records)
    if not config or not municipalities:
        return ""

    search_name = config["search_name"]
    items = "".join(
        _municipality_link_item(name, count, (municipality_paths or {}).get(name))
        for name, count in municipalities
    )
    if len(municipalities) == 1:
        lead = f"{search_name}のポケふたは{municipalities[0][0]}に設置されています。"
    else:
        names = "・".join(name for name, _ in municipalities[:3])
        lead = f"{search_name}のポケふたは{names}など、{len(municipalities)}自治体にあります。"
    return (
        '<section class="municipality-guide" aria-labelledby="municipality-heading">'
        f'<h2 id="municipality-heading">{escape(search_name)}のポケふたはどこ？市町村別の設置枚数</h2>'
        f'<p>{escape(lead)}各地点の住所と行き方は、下の一覧と地図から確認できます。</p>'
        f'<ul>{items}</ul>'
        '<div class="municipality-actions">'
        '<a class="inline-link" href="#manhole-list">場所一覧を見る</a>'
        '<a class="inline-link" href="#prefecture-map">地図を見る</a>'
        '</div></section>'
    )


def _municipality_pages_html(
    prefecture: str, records: list[dict], municipality_paths: dict[str, str] | None
) -> str:
    """市区町村ページがある自治体への入口。ページは県の一部を占める自治体にだけある（municipalities.py）。"""
    if not municipality_paths:
        return ""
    items = "".join(
        _municipality_link_item(name, count, municipality_paths[name])
        for name, count in _municipality_counts(records)
        if name in municipality_paths
    )
    if not items:
        return ""
    return (
        '<section class="municipality-guide" aria-labelledby="municipality-pages-heading">'
        f'<h2 id="municipality-pages-heading">{escape(prefecture)}の市区町村から探す</h2>'
        '<p>ポケふたが集まっている市区町村は、地図・一覧・巡る順番を1ページにまとめています。</p>'
        f'<ul>{items}</ul></section>'
    )


def _nearest_pokefuta_html(prefecture: str, nearest: list[tuple[float, dict]]) -> str:
    if not nearest:
        return ""
    office = EMPTY_PREFECTURE_ORIGINS[prefecture][0]
    short = _short_prefecture_name(prefecture)
    first_distance, first = nearest[0]
    stops = "".join(
        f'<li><a href="/manholes/{quote(str(record.get("id", "")))}/" '
        'data-track="prefecture_manhole_click" data-surface="nearest_pokefuta" '
        f'data-position="{position}" '
        f'data-destination="{_escape_attr(record.get("id", ""))}" '
        f'data-content-id="{_escape_attr(record.get("id", ""))}">'
        f'{escape(_guide_stop_name(record))}</a>'
        f'<span>{escape(str(record.get("address") or ""))}・直線約{distance:.0f}km</span>'
        f'<span>{escape("・".join(_clean_pokemons(record)))}</span></li>'
        for position, (distance, record) in enumerate(nearest, start=1)
    )
    return (
        '<section class="visit-guide" aria-labelledby="nearest-heading">'
        f'<h2 id="nearest-heading">{escape(short)}から近いポケふた{len(nearest)}枚</h2>'
        f'<p>{escape(prefecture)}には現在ポケふたがありません。'
        f'{escape(office)}からいちばん近いのは{escape(str(first.get("prefecture", "")))}の'
        f'{escape(_guide_stop_name(first))}で、直線で約{first_distance:.0f}kmです。'
        '距離は直線のため、移動距離や所要時間は地図アプリで確認してください。</p>'
        f'<ul class="visit-guide-stops">{stops}</ul>'
        '</section>'
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


def _guide_stop_name(record: dict) -> str:
    # 施設名のない蓋は「長崎県/長崎市」になる。県ページ内の案内では県名が重複するので省く。
    return _manhole_name(record).removeprefix(f'{record.get("prefecture", "")}/')


def _visit_guide_html(records: list[dict], guide: dict | None) -> str:
    if not guide:
        return ""
    active_by_id = {
        str(record.get("id", "")): record for record in records
        if record.get("status", "active") == "active"
    }
    by_id = {
        mid: record for mid, record in active_by_id.items()
        if record.get("installed") is not False
    }
    route_groups = guide.get("routes") or [{
        "heading": "",
        "intro": "",
        "manhole_ids": guide.get("manhole_ids", []),
    }]
    stop_ids = [mid for route in route_groups for mid in route.get("manhole_ids", [])]
    allowed_ids = active_by_id if guide.get("allow_preinstallation") else by_id
    # Hide stale or incomplete editorial routes. A guide may opt into known
    # pre-installation stops so they appear automatically after installation.
    if (
        not stop_ids
        or len(stop_ids) != len(set(stop_ids))
        or any(mid not in allowed_ids for mid in stop_ids)
        or (guide.get("require_all_installed") and not set(by_id).issubset(stop_ids))
    ):
        return ""

    def stop_list(route_stop_ids: list[str]) -> str:
        stops = "".join(
            f'<li><a href="#manhole-{_escape_attr(mid)}" '
            'data-track="prefecture_photo_candidate_click" data-surface="visit_guide" '
            f'data-destination="manhole_list" data-content-id="{_escape_attr(mid)}">'
            f'{escape(_guide_stop_name(by_id[mid]))}</a>'
            f'<span>{escape(str(by_id[mid].get("address") or ""))}</span></li>'
            for mid in route_stop_ids if mid in by_id
        )
        return f'<ul class="visit-guide-stops">{stops}</ul>'

    if guide.get("routes"):
        stops_html = '<div class="visit-guide-routes">' + "".join(
            '<details class="visit-guide-route">'
            f'<summary>{escape(route["heading"])}'
            f'（{sum(mid in by_id for mid in route["manhole_ids"])}地点）</summary>'
            f'<p>{escape(route["intro"])}</p>'
            f'{stop_list(route["manhole_ids"])}</details>'
            for route in route_groups
        ) + "</div>"
    else:
        stops_html = stop_list(stop_ids)
    advice = "".join(
        f'<div><h3>{escape(section["heading"])}</h3><p>{escape(section["text"])}</p></div>'
        for section in guide["sections"]
    )
    sources = "・".join(
        f'<a href="{_escape_attr(source["url"])}" target="_blank" '
        'rel="noopener noreferrer" data-track="prefecture_official_click" '
        'data-surface="visit_guide" data-destination="travel_source">'
        f'{escape(source["label"])}</a>'
        for source in guide["sources"]
        if urlparse(source["url"]).scheme == "https"
        and urlparse(source["url"]).netloc
    )
    return (
        '<section class="visit-guide" aria-labelledby="visit-guide-heading">'
        f'<h2 id="visit-guide-heading">{escape(guide["heading"])}</h2>'
        f'<p>{escape(guide["intro"])}</p>'
        f'{stops_html}'
        '<div class="municipality-actions">'
        '<a class="inline-link" href="#prefecture-map" data-track="prefecture_map_click" '
        'data-surface="visit_guide" data-destination="prefecture_map">設置場所を地図で見る</a>'
        '<a class="inline-link" href="#visit-advice">回り方を見る</a></div>'
        '<details id="visit-advice" class="visit-advice" open>'
        f'<summary>{escape(guide.get("advice_label", "駅・車での回り方"))}</summary>'
        f'{advice}</details>'
        f'<p class="visit-guide-sources">出典：{sources}'
        f'（確認日：<time datetime="{_escape_attr(guide["checked_on"])}">'
        f'{escape(guide["checked_on"])}</time>）</p></section>'
    )


# 都道府県ページと市区町村ページ（generate_municipality_pages.py）で共有する見た目。
# build_page の f-string から外に出したので、波括弧は1つで書く。
PAGE_CSS = """    :root { color-scheme: light; }
    * { box-sizing: border-box; }
    body {
      margin: 0; background: #f7f0df; color: #201b16;
      font-family: system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
      line-height: 1.65;
    }
    a { color: #176f68; }
    .page { max-width: 1040px; margin: 0 auto; padding: 20px 16px 56px; }
    .breadcrumb { display: flex; gap: 8px; font-size: .82rem; font-weight: 800; }
    .breadcrumb a { text-decoration: none; }
    .hero {
      position: relative; overflow: hidden; margin-top: 14px; padding: 28px;
      display: grid; grid-template-columns: minmax(0, 1fr) 280px; gap: 22px;
      align-items: center;
      border: 1px solid rgba(93,67,35,.15); border-radius: 24px;
      background: linear-gradient(135deg, #fffaf0, #f0e9fb);
      box-shadow: 0 14px 32px rgba(77,56,30,.08);
    }
    .hero::after {
      content: ""; position: absolute; width: 230px; height: 230px;
      right: -70px; top: -90px; border: 42px solid rgba(126,107,169,.1);
      border-radius: 50%;
    }
    .municipality-guide {
      margin-top: 18px; padding: 22px; border: 1px solid rgba(93,67,35,.15);
      border-radius: 18px; background: #fffaf0;
    }
    .municipality-guide h2 { margin: 0 0 6px; font-size: 1.25rem; }
    .municipality-guide p { margin: 0; color: #62564a; }
    .municipality-guide ul {
      display: flex; flex-wrap: wrap; gap: 8px; margin: 14px 0 0; padding: 0;
      list-style: none;
    }
    .municipality-guide li {
      display: inline-flex; align-items: center; gap: 7px; padding: 7px 10px;
      border-radius: 999px; background: #f0e9fb;
    }
    .municipality-guide li span { color: #62564a; font-size: .82rem; font-weight: 800; }
    .municipality-actions { display: flex; flex-wrap: wrap; gap: 14px; margin-top: 14px; }
    .visit-guide > p { color: #62564a; }
    .visit-guide-stops {
      display: grid; grid-template-columns: repeat(auto-fit, minmax(min(100%, 240px), 1fr));
      gap: 10px; list-style: none; padding: 0; margin: 14px 0;
    }
    .visit-guide-stops li { min-width: 0; padding: 12px; border-radius: 12px; background: #f0e9fb; }
    .visit-guide-stops a { display: block; min-height: 44px; font-weight: 850; }
    .visit-guide-stops span { display: block; color: #62564a; font-size: .82rem; overflow-wrap: anywhere; }
    .visit-guide-routes { display: grid; gap: 10px; margin: 16px 0; }
    .visit-guide-route { padding: 14px; border: 1px solid rgba(93,67,35,.15); border-radius: 14px; }
    .visit-guide-route summary { cursor: pointer; font-weight: 850; color: #14544f; }
    .visit-guide-route > p { margin: 10px 0 0; color: #62564a; }
    .visit-advice { margin-top: 18px; }
    .visit-advice summary { cursor: pointer; font-weight: 850; color: #14544f; }
    .visit-advice h3 { margin: 14px 0 6px; font-size: 1rem; }
    .visit-advice p { margin: 0; }
    .visit-guide-sources { font-size: .78rem; overflow-wrap: anywhere; }
    .visit-advice, .manhole-card { scroll-margin-top: 100px; }
    .hero-kicker { margin: 0; color: #6b4aa2; font-size: .8rem; font-weight: 900; }
    h1 { margin: 4px 0 8px; font-size: clamp(2rem, 7vw, 3.5rem); line-height: 1.15; }
    .hero-main > p:last-of-type { max-width: 720px; margin: 0; color: #574b41; font-weight: 650; }
    .hero-summary {
      position: relative; z-index: 1; padding: 16px 18px; border-radius: 17px;
      background: rgba(255,255,255,.74); color: #3a3128;
      box-shadow: inset 0 0 0 1px rgba(93,67,35,.11);
    }
    .hero-summary span {
      display: block; margin-bottom: 6px; color: #6b4aa2;
      font-size: .76rem; font-weight: 900;
    }
    .hero-summary p { margin: 0; font-size: .96rem; font-weight: 800; }
    .stats { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 10px; margin-top: 18px; }
    .stat { padding: 14px; border-radius: 15px; background: rgba(255,255,255,.72); }
    .stat span { display: block; color: #75685c; font-size: .76rem; font-weight: 850; }
    .stat strong { display: block; color: #57408f; font-size: 1.55rem; line-height: 1.3; }
    .hero-actions { display: flex; flex-wrap: wrap; gap: 10px; margin-top: 18px; }
    .button {
      display: inline-flex; align-items: center; min-height: 44px; padding: 0 16px;
      border-radius: 999px; background: #176f68; color: white; font-weight: 900;
      text-decoration: none;
    }
    .button.primary { background: #b5483c; }
    .button.secondary { background: #6b4aa2; }
    .button.tertiary {
      background: white; color: #176f68; box-shadow: inset 0 0 0 1px #9fc7c2;
    }
    .button.official { background: #8a5a20; }
    .hero-note { margin: 10px 0 0; color: #75685c; font-size: .78rem; font-weight: 750; }
    .hero-utility { margin-top: 10px; }
    .hero-utility:empty { display: none; }
    section {
      margin-top: 22px; padding: 20px; border: 1px solid rgba(93,67,35,.14);
      border-radius: 19px; background: #fffaf0;
      box-shadow: 0 8px 20px rgba(77,56,30,.05);
    }
    h2 { margin: 0 0 12px; font-size: 1.35rem; line-height: 1.35; }
    .section-heading-row {
      display: flex; justify-content: space-between; align-items: flex-start; gap: 16px;
      margin-bottom: 12px;
    }
    .section-heading-row h2, .section-heading-row p { margin: 0; }
    .section-heading-row p { max-width: 520px; color: #75685c; font-size: .86rem; }
    .map-toolbar {
      display: flex; flex-wrap: wrap; justify-content: space-between; gap: 10px;
      align-items: center; margin-bottom: 10px;
    }
    .map-legend { display: flex; flex-wrap: wrap; gap: 10px; color: #62564a; font-size: .78rem; font-weight: 800; }
    .map-legend span { display: inline-flex; align-items: center; gap: 5px; }
    .legend-dot { width: 12px; height: 12px; border: 3px solid white; border-radius: 50%; box-shadow: 0 0 0 1px rgba(32,27,22,.2); }
    .legend-dot.has-photo { background: #2d846c; }
    .legend-dot.needs-photo { background: #d78548; }
    .legend-dot.preinstall { background: #8b8f94; }
    .nearby-link, .inline-link {
      display: inline-flex; align-items: center; min-height: 44px; padding: 0 14px;
      border-radius: 999px; background: #e6f2ef; color: #176f68;
      font-size: .84rem; font-weight: 900; text-decoration: none;
    }
    #prefecture-map { height: 430px; border-radius: 14px; background: #e9e3d6; }
    #prefecture-map.map-empty { display: grid; place-items: center; color: #75685c; font-weight: 850; }
    .map-note { margin: 10px 0 0; color: #75685c; font-size: .8rem; }
    .prefecture-marker {
      width: 28px; height: 28px; border: 4px solid white; border-radius: 50% 50% 50% 8px;
      transform: rotate(-45deg); box-shadow: 0 3px 8px rgba(32,27,22,.35);
    }
    .prefecture-marker.has-photo { background: #2d846c; }
    .prefecture-marker.needs-photo { background: #d78548; }
    .prefecture-marker.preinstall { background: #8b8f94; }
    .map-popup { min-width: 210px; }
    .map-popup img {
      display: block; width: 100%; height: 120px; margin: 8px 0; border-radius: 10px;
      object-fit: cover;
    }
    .map-popup-photo-missing {
      margin: 8px 0; padding: 8px; border-radius: 9px; background: #fff0e5;
      color: #8d4a22; font-size: .78rem; font-weight: 850;
    }
    .map-popup-preinstall {
      margin: 8px 0; padding: 8px; border-radius: 9px; background: #f0ede7;
      color: #625b53; font-size: .78rem; font-weight: 850;
    }
    .map-popup-actions { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 5px; margin-top: 9px; }
    .map-popup-actions.preinstall-actions { grid-template-columns: repeat(2, minmax(0, 1fr)); }
    .map-popup-actions a {
      display: grid; place-items: center; min-height: 38px; padding: 5px;
      border-radius: 8px; background: #ece7f7; color: #4f3a79;
      font-size: .72rem; text-align: center; text-decoration: none;
    }
    .map-popup-actions a.upload { background: #b5483c; color: white; }
    .photo-inventory {
      display: grid; grid-template-columns: minmax(0, 1fr) 180px auto; gap: 14px;
      align-items: center; margin-bottom: 16px;
    }
    .photo-inventory strong { color: #57408f; font-size: 1.8rem; line-height: 1; }
    .photo-inventory strong span { color: #75685c; font-size: .9rem; }
    .photo-inventory p { margin: 5px 0 0; color: #62564a; }
    .photo-inventory > b { color: #57408f; }
    .coverage-meter { height: 10px; overflow: hidden; border-radius: 999px; background: #e5ddd0; }
    .coverage-meter span { display: block; height: 100%; border-radius: inherit; background: #6b4aa2; }
    .photo-showcase-grid {
      display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 10px;
      margin-bottom: 14px;
    }
    .photo-card { overflow: hidden; border: 1px solid rgba(93,67,35,.13); border-radius: 14px; background: white; }
    .photo-card-image { display: block; color: inherit; text-decoration: none; }
    .photo-card-image img {
      display: block; width: 100%; aspect-ratio: 4 / 3; height: auto; object-fit: cover;
      background: #e9e3d6;
    }
    .photo-card-image > span { display: grid; padding: 9px 10px; }
    .photo-card-image small { overflow: hidden; color: #75685c; font-size: .72rem; text-overflow: ellipsis; white-space: nowrap; }
    .photo-card-poster { display: block; padding: 0 10px 9px; overflow: hidden; color: #75685c; font-size: .72rem; text-overflow: ellipsis; white-space: nowrap; }
    .photo-card-poster a { color: #176f68; font-weight: 800; text-decoration: underline; text-underline-offset: 2px; }
    .photo-card-upload {
      display: grid; place-items: center; min-height: 44px; padding: 6px 9px;
      border-top: 1px solid #ece4d7; color: #176f68; font-size: .75rem;
      font-weight: 900; text-align: center; text-decoration: none;
    }
    .contribution-panel {
      display: grid; grid-template-columns: minmax(220px, .8fr) minmax(0, 1.2fr);
      gap: 14px; align-items: center; padding: 14px; border-radius: 14px;
      background: #fff0e5;
    }
    .contribution-panel p { margin: 4px 0 0; color: #75685c; font-size: .82rem; }
    .contribution-grid { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 8px; }
    .contribution-card {
      display: grid; min-width: 0; padding: 10px; border-radius: 11px; background: white;
      color: inherit; text-decoration: none;
    }
    .contribution-card span { color: #b5483c; font-size: .68rem; font-weight: 950; }
    .contribution-card small { overflow: hidden; color: #75685c; font-size: .72rem; text-overflow: ellipsis; white-space: nowrap; }
    .contribution-card b { margin-top: 6px; color: #176f68; font-size: .75rem; }
    .photo-empty-state { padding: 18px; border-radius: 14px; background: #f3efe7; }
    .photo-empty-state p { margin: 4px 0 12px; color: #75685c; }
    .pokemon-grid { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 8px; }
    .pokemon-card {
      display: grid; gap: 2px; padding: 12px; border: 1px solid rgba(93,67,35,.13);
      border-radius: 13px; background: white; color: inherit; text-decoration: none;
    }
    .pokemon-card strong { color: #3d2b72; }
    .pokemon-card span { color: #75685c; font-size: .75rem; font-weight: 750; }
    .pokemon-more { grid-column: 1 / -1; }
    .pokemon-more summary {
      width: fit-content; margin: 12px auto 0; padding: 8px 14px;
      border-radius: 999px; background: #eee7fb; color: #57408f;
      cursor: pointer; font-size: .82rem; font-weight: 900;
    }
    .pokemon-more-grid {
      display: grid; grid-template-columns: repeat(3, minmax(0, 1fr));
      gap: 8px; margin-top: 12px;
    }
    .manhole-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(230px, 1fr)); gap: 10px; }
    .manhole-card {
      overflow: hidden; border: 1px solid #e9dfc7;
      border-radius: 14px; background: #fffdf7;
      box-shadow: 0 1px 2px rgba(72,55,20,.05), 0 3px 8px rgba(72,55,20,.05);
    }
    .manhole-detail {
      position: relative; display: block; color: inherit; text-decoration: none;
    }
    .manhole-card img, .manhole-placeholder {
      display: block; width: 100%; aspect-ratio: 1 / 1; height: auto; object-fit: cover;
      background: #e9e3d6;
    }
    .manhole-placeholder {
      background: repeating-linear-gradient(45deg, #cdbf9f 0 10px, #c2b390 10px 20px);
    }
    .manhole-shade {
      position: absolute; inset: 0;
      background: linear-gradient(to top, rgba(30,22,10,.62) 0%, rgba(30,22,10,0) 46%);
    }
    .manhole-badges {
      position: absolute; top: 8px; right: 8px; display: grid; gap: 4px; justify-items: end;
    }
    .manhole-copy {
      position: absolute; right: 12px; bottom: 10px; left: 12px;
      min-width: 0; color: white; text-shadow: 0 1px 3px rgba(0,0,0,.45);
    }
    .manhole-copy strong, .manhole-copy small { display: block; }
    .manhole-copy small {
      overflow: hidden; font-size: .75rem; opacity: .92;
      text-overflow: ellipsis; white-space: nowrap;
    }
    .photo-status {
      display: inline-flex; width: fit-content; padding: 2px 7px;
      border-radius: 999px; font-size: .68rem; font-weight: 800;
      box-shadow: 0 1px 3px rgba(30,22,10,.25);
    }
    .photo-ready { background: #e4f2ee; color: #176f68; }
    .photo-needed { background: #fff0e5; color: #9b4b20; }
    .photo-pending { background: #f0ede7; color: #6f6254; }
    .manhole-actions {
      display: grid; grid-auto-flow: column; grid-auto-columns: minmax(0, 1fr);
      border-top: 1px solid #ece4d7;
    }
    .manhole-actions a {
      display: grid; place-items: center; min-height: 44px; padding: 5px;
      color: #57408f; font-size: .76rem; font-weight: 900; text-align: center;
      text-decoration: none;
    }
    .manhole-actions a + a { border-left: 1px solid #ece4d7; }
    /* 写真館のタイルは色面のボタンを持たないので、ここも塗り潰しをやめて
       写真館の淡いタグ色（#fdeae2 / #bf5640）に寄せる。赤ベタのボタンが
       全カードに並ぶと、写真より先にボタンの列が目に入っていた。 */
    .manhole-actions a.upload { background: #fdeae2; color: #bf5640; }
    .journey-loop { background: linear-gradient(135deg, #f1f8f6, #f5effc); }
    .journey-steps {
      display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 8px;
      margin: 14px 0;
    }
    .journey-step { padding: 12px; border-radius: 12px; background: white; font-size: .82rem; font-weight: 850; }
    .journey-step span { display: block; color: #6b4aa2; font-size: .7rem; }
    .journey-actions { display: flex; flex-wrap: wrap; gap: 8px; }
    .manhole-preinstall-badge {
      display: inline-block; padding: 2px 8px;
      border-radius: 999px; background: #f1ede4; color: #6b5d44;
      font-size: .74rem; font-weight: 700; white-space: nowrap;
      box-shadow: 0 1px 3px rgba(30,22,10,.25);
    }
    .trivia-card {
      border-left: 5px solid #7e6ba9;
      background: linear-gradient(135deg, #fffaf0, #f4effd);
    }
    .trivia-kicker {
      display: inline-flex; margin: 0 0 6px; padding: 3px 9px;
      border-radius: 999px; background: #6b4aa2; color: white;
      font-size: .72rem; font-weight: 900;
    }
    .trivia-card p { margin: 0; font-size: 1.05rem; font-weight: 750; }
    .trivia-source { margin-top: 8px; font-size: .78rem; }
    .event-card {
      border-left: 5px solid #176f68;
      background: linear-gradient(135deg, #fffaf0, #edf8f2);
    }
    .event-item + .event-item { margin-top: 14px; }
    .event-status {
      display: inline-flex; margin: 0 0 6px; padding: 3px 9px;
      border-radius: 999px; background: #176f68; color: white;
      font-size: .72rem; font-weight: 900;
    }
    .event-item strong { display: block; }
    .event-item strong a { color: #14544f; }
    .event-item p { margin: 6px 0 0; font-size: .92rem; }
    .event-period { color: #75685c; font-size: .78rem; }
    .empty-state { margin: 0; color: #75685c; }
    .related-label { margin: 0 0 8px; color: #75685c; font-size: .8rem; font-weight: 850; }
    .related-links { display: flex; flex-wrap: wrap; gap: 8px; }
    .related-links a {
      padding: 6px 10px; border-radius: 999px; background: #eee7fb;
      color: #57408f; font-size: .82rem; font-weight: 850; text-decoration: none;
    }
    footer { margin-top: 24px; color: #75685c; font-size: .8rem; text-align: center; }
    .leaflet-popup-content a { font-weight: 850; }
    @media (max-width: 700px) {
      .hero { display: block; padding: 22px 18px; }
      .hero-summary { display: none; }
      .hero-actions { display: grid; grid-template-columns: 1fr 1fr; }
      .hero-actions .button { justify-content: center; padding: 0 12px; text-align: center; }
      .hero-actions .button.primary { grid-column: 1 / -1; }
      .section-heading-row { display: block; }
      .section-heading-row p { margin-top: 4px; }
      .photo-inventory { grid-template-columns: minmax(0, 1fr) auto; }
      .coverage-meter { grid-column: 1 / -1; grid-row: 2; }
      .photo-showcase-grid { grid-template-columns: repeat(2, minmax(0, 1fr)); }
      .contribution-panel { grid-template-columns: 1fr; }
      .contribution-grid { grid-template-columns: 1fr; }
      .journey-steps { grid-template-columns: repeat(2, minmax(0, 1fr)); }
      .pokemon-grid, .pokemon-more-grid { grid-template-columns: 1fr; }
      .manhole-grid { grid-template-columns: repeat(2, minmax(0, 1fr)); }
      #prefecture-map { height: 360px; }
      section { padding: 16px; }
    }
    /* iPhone SE(第1世代) 級の幅では2列タイル内に操作を横並びで置けず、
       「地図で開 / く」と折り返していたので、ここだけ縦に積む。 */
    @media (max-width: 360px) {
      .manhole-actions { grid-auto-flow: row; }
      .manhole-actions a + a { border-top: 1px solid #ece4d7; border-left: 0; }
    }
"""


def _map_script(
    map_points: list[dict],
    campaign_params: str,
    event_prefix: str = "prefecture",
    track_fn: str = "trackPrefectureEvent",
) -> str:
    """設置マップ（Leaflet）の初期化。地図要素の id は `prefecture-map` で共通。

    市区町村ページも同じ地図を出すので、イベント名の接頭辞と送信関数の名前だけを差し替えられる。
    """
    return f"""  <script>
    const points = {_json_for_script(map_points)};
    const campaignParams = {_json_for_script(campaign_params)};
    const mapElement = document.getElementById('prefecture-map');
    if (!mapElement) {{
      /* ポケふたが無い県では地図セクション自体を出していない */
    }} else if (!points.length) {{
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
        const markerClass = point.is_preinstall
          ? 'preinstall'
          : (point.photo_url ? 'has-photo' : 'needs-photo');
        const photoState = point.is_preinstall
          ? 'preinstall'
          : (point.photo_url ? 'has_photo' : 'missing');
        const googleMapsUrl = 'https://www.google.com/maps?q=' + point.lat + ',' + point.lng;
        const uploadUrl = 'https://pokefuta.com/upload?manhole_id=' +
          encodeURIComponent(point.id) + '&' + campaignParams;
        const photoHtml = point.is_preinstall
          ? '<div class="map-popup-preinstall">設置予定のポケふたです。設置後に写真を投稿できます。</div>'
          : (point.photo_url
            ? '<img src="' + escapeHtml(point.photo_url) + '" alt="' +
              escapeHtml(point.name) + 'のポケふた投稿写真" ' +
              'loading="lazy" decoding="async" width="320" height="240">'
            : '<div class="map-popup-photo-missing">このポケふたは写真募集中です</div>');
        const uploadHtml = point.is_preinstall
          ? ''
          : '<a class="upload" href="' + escapeHtml(uploadUrl) +
            '" data-track="{event_prefix}_photo_upload_start" data-destination="upload" ' +
            'data-content-id="' + escapeHtml(point.id) +
            '" data-surface="map_popup" data-photo-state="' + photoState + '">写真投稿</a>';
        const popupHtml = '<div class="map-popup"><strong>' +
          escapeHtml(point.name) + '</strong><br>' +
          escapeHtml(pokemon) + photoHtml + '<div class="map-popup-actions' +
          (point.is_preinstall ? ' preinstall-actions' : '') + '">' +
          '<a href="' + detailUrl + '" data-track="{event_prefix}_manhole_click" ' +
          'data-destination="' + escapeHtml(point.id) + '" data-content-id="' + escapeHtml(point.id) +
          '" data-surface="map_popup">詳細</a>' +
          '<a href="' + escapeHtml(googleMapsUrl) +
          '" target="_blank" rel="noopener noreferrer" ' +
          'data-track="{event_prefix}_google_maps_click" data-destination="google_maps" ' +
          'data-content-id="' + escapeHtml(point.id) + '" data-surface="map_popup">行き方</a>' +
          uploadHtml + '</div></div>';
        const marker = L.marker(latlng, {{
          title: point.name + 'のポケふた',
          alt: point.name + 'のポケふた・' +
            (point.is_preinstall
              ? '設置予定'
              : (point.photo_url ? '投稿写真あり' : '写真募集中')),
          icon: L.divIcon({{
            className: '',
            html: '<div class="prefecture-marker ' + markerClass + '"></div>',
            iconSize: [28, 34],
            iconAnchor: [14, 31],
            popupAnchor: [0, -30]
          }})
        }}).addTo(map).bindPopup(popupHtml, {{ maxWidth: 300 }});
        marker.on('click', function() {{
          {track_fn}('{event_prefix}_map_pin_click', {{
            surface: '{event_prefix}_map',
            content_id: point.id,
            photo_state: photoState
          }});
        }});
      }});
      if (bounds.length === 1) map.setView(bounds[0], 13);
      else map.fitBounds(bounds, {{ padding: [28, 28], maxZoom: 13 }});
      let mapInteractionSent = false;
      function reportMapInteraction(interaction) {{
        if (mapInteractionSent) return;
        mapInteractionSent = true;
        {track_fn}('{event_prefix}_map_interaction', {{ surface: '{event_prefix}_map', interaction: interaction }});
      }}
      mapElement.addEventListener('pointerdown', function() {{ reportMapInteraction('pointer'); }}, {{ once: true }});
      mapElement.addEventListener('keydown', function() {{ reportMapInteraction('keyboard'); }}, {{ once: true }});
    }}
    function escapeHtml(value) {{
      return String(value).replace(/[&<>"']/g, function(char) {{
        return {{'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}}[char];
      }});
    }}
  </script>"""


def build_page(
    prefecture: str,
    slug: str,
    records: list[dict],
    rank: int | None,
    pokemon_slugs: dict[str, str],
    trivia_entry: dict | None,
    events: list[dict] | None = None,
    photos: dict[str, dict] | None = None,
    empty_prefectures: set[str] | None = None,
    visit_guide: dict | None = None,
    all_records: list[dict] | None = None,
    municipality_paths: dict[str, str] | None = None,
) -> str:
    photos = photos or {}
    count = len(records)
    installed_records = [
        record for record in records if record.get("installed") is not False
    ]
    installed_count = len(installed_records)
    canonical = f"{BASE_URL}/prefectures/{slug}/"
    nearest = [] if count else _nearest_pokefuta(prefecture, all_records)
    title, description, h1 = _prefecture_seo(prefecture, count, records, nearest)
    rank_label = f"全国{rank}位" if rank else "現在未設置"
    hero_intro = _hero_intro(prefecture, count, trivia_entry)
    hero_summary = _hero_summary(prefecture, count, records, trivia_entry)
    official_url = _prefecture_official_url(records)
    official_cta = (
        f'<a class="inline-link official-link" href="{_escape_attr(official_url)}" target="_blank" '
        f'rel="noopener noreferrer" data-track="prefecture_official_click" '
        f'data-destination="prefecture_official">{escape(prefecture)}公式を見る</a>'
        if official_url else ""
    )
    map_points = [
        {
            "id": str(record.get("id", "")),
            "lat": record.get("lat"),
            "lng": record.get("lng"),
            "name": _manhole_name(record),
            "pokemons": _clean_pokemons(record),
            "is_preinstall": record.get("installed") is False,
            "photo_url": (
                _photo_asset_url(
                    record, photos.get(str(record.get("id", "")), {})
                )
                if record.get("installed") is not False
                and str(record.get("id", "")) in photos
                else ""
            ),
        }
        for record in records
        if isinstance(record.get("lat"), (int, float))
        and isinstance(record.get("lng"), (int, float))
    ]
    pokemon_html = _pokemon_cards(records, pokemon_slugs)
    manhole_html = _manhole_cards(records, photos, slug)
    photo_html = _photo_section(prefecture, slug, records, photos)
    trivia_html = _trivia_html(prefecture, trivia_entry, count)
    events_html = _events_html(events)
    related_html = _related_prefectures(prefecture, empty_prefectures)
    municipality_guide_html = (
        _visit_guide_html(records, visit_guide)
        or _municipality_guide(prefecture, records, municipality_paths)
    )
    # 市区町村ページへのリンクが上の案内に入っていなければ、入口を別に置く
    if municipality_paths and "/municipalities/" not in municipality_guide_html:
        municipality_guide_html += _municipality_pages_html(prefecture, records, municipality_paths)
    visits_url = _visits_url(slug)
    nearby_url = _nearby_url(slug)
    if installed_count:
        hero_actions_html = (
            '<a class="button primary" href="#manhole-list" '
            'data-track="prefecture_photo_candidate_click" '
            'data-legacy-track="prefecture_photo_cta_click" '
            'data-surface="hero" '
            'data-destination="manhole_list">投稿するポケふたを選ぶ</a>'
            '<a class="button secondary" href="#prefecture-map" '
            'data-track="prefecture_map_click" '
            'data-destination="prefecture_map">地図で探す</a>'
            f'<a class="button tertiary" href="{_escape_attr(visits_url)}" '
            'data-track="prefecture_visit_cta_click" '
            'data-destination="pokefuta_visits">訪問記録を開く</a>'
        )
        hero_note = "対象を選ぶまではログイン不要です。写真投稿時にログインへ進みます。"
        journey_html = f"""
    <section class="journey-loop" aria-labelledby="journey-heading">
      <h2 id="journey-heading">記録して、次のポケふたへ</h2>
      <div class="journey-steps" aria-label="継続して楽しむ流れ">
        <div class="journey-step"><span>STEP 1</span>地図で見つける</div>
        <div class="journey-step"><span>STEP 2</span>現地を訪れる</div>
        <div class="journey-step"><span>STEP 3</span>写真で記録する</div>
        <div class="journey-step"><span>STEP 4</span>未訪問を探す</div>
      </div>
      <div class="journey-actions">
        <a class="button primary" href="{_escape_attr(visits_url)}"
          data-track="prefecture_visit_cta_click" data-destination="pokefuta_visits">スタンプ帳で進捗を見る</a>
        <a class="button tertiary" href="{_escape_attr(nearby_url)}"
          data-track="prefecture_nearby_click" data-destination="pokefuta_nearby">近くの未訪問を探す</a>
      </div>
    </section>"""
    elif count:
        hero_actions_html = (
            '<a class="button primary" href="#prefecture-map" '
            'data-track="prefecture_map_click" '
            'data-destination="prefecture_map">設置予定地を地図で見る</a>'
            '<a class="button tertiary" href="/summary/" '
            'data-track="prefecture_summary_click" '
            'data-destination="summary">全国のポケふたを見る</a>'
        )
        hero_note = "設置後に写真投稿を受け付けます。予定地と設置時期は詳細ページで確認できます。"
        journey_html = f"""
    <section class="journey-loop" aria-labelledby="journey-heading">
      <h2 id="journey-heading">設置予定を確認して、次の行き先を探す</h2>
      <p>設置予定地は地図で確認できます。設置を待つ間は、全国一覧や現在地周辺からポケふた巡りを始められます。</p>
      <div class="journey-actions">
        <a class="button primary" href="#prefecture-map"
          data-track="prefecture_map_click" data-destination="prefecture_map">設置予定地を見る</a>
        <a class="button tertiary" href="{_escape_attr(nearby_url)}"
          data-track="prefecture_nearby_click" data-destination="pokefuta_nearby">現在地の近くから探す</a>
      </div>
    </section>"""
    else:
        hero_actions_html = (
            '<a class="button primary" href="/summary/" '
            'data-track="prefecture_summary_click" '
            'data-destination="summary">全国のポケふたを見る</a>'
            f'<a class="button tertiary" href="{_escape_attr(nearby_url)}" '
            'data-track="prefecture_nearby_click" '
            'data-destination="pokefuta_nearby">現在地の近くから探す</a>'
        )
        hero_note = "新しい設置情報が入り次第、地図・写真・投稿先をこのページへ追加します。"
        journey_html = f"""
    <section class="journey-loop" aria-labelledby="journey-heading">
      <h2 id="journey-heading">全国のポケふたから次の行き先を探す</h2>
      <p>この都道府県の設置情報を待つ間も、全国一覧や現在地周辺からポケふた巡りを始められます。</p>
      <div class="journey-actions">
        <a class="button primary" href="/summary/"
          data-track="prefecture_summary_click" data-destination="summary">全国のポケふた一覧</a>
        <a class="button tertiary" href="{_escape_attr(nearby_url)}"
          data-track="prefecture_nearby_click" data-destination="pokefuta_nearby">現在地の近くから探す</a>
      </div>
    </section>"""
    map_empty_class = " map-empty" if not map_points else ""

    # ポケふたが1枚も無い県のページは、8セクション中7つが「未設置」の言い換えに
    # なっていた（地図は空、写真は空、一覧は空、ポケモンは空、トリビアも未設置文）。
    # 実測ではこの5県（群馬・山梨・広島・熊本・大分）が engagementRate ワースト5で、
    # 0.28〜0.41（/prefectures 全体は 0.753）、滞在 13〜45秒。
    # 検索から来た人を空セクションで埋めず、実際に行ける場所（近隣県・全国・現在地）
    # だけを上に出す。設置予定レコードがある県は地図が意味を持つので対象外。
    related_section_html = (
        f"""    <section aria-labelledby="related-heading">
      <h2 id="related-heading">近くの都道府県から探す</h2>
      {related_html}
    </section>"""
        if related_html
        else ""
    )

    if records:
        main_sections_html = f"""    {municipality_guide_html}

    <section aria-labelledby="map-heading">
      <div class="section-heading-row">
        <h2 id="map-heading">{escape(prefecture)}の設置マップ</h2>
        <p>ピンから詳細・行き方へ。設置済みのポケふたは写真投稿にも進めます。</p>
      </div>
      <div class="map-toolbar">
        <div class="map-legend" aria-label="地図の凡例">
          <span><i class="legend-dot has-photo"></i>投稿写真あり</span>
          <span><i class="legend-dot needs-photo"></i>写真募集中</span>
          <span><i class="legend-dot preinstall"></i>設置予定</span>
        </div>
        <a class="nearby-link" href="{_escape_attr(nearby_url)}"
          data-track="prefecture_nearby_click" data-destination="pokefuta_nearby">現在地の近くから探す</a>
      </div>
      <div id="prefecture-map" class="{map_empty_class.strip()}"></div>
      <p class="map-note">地図はドラッグとピンチ操作に対応。スクロール中の誤操作を防ぐため、マウスホイール拡大は無効です。</p>
    </section>

    <!-- adsense:prefecture -->

    <section id="prefecture-photos" aria-labelledby="photo-heading">
      <div class="section-heading-row">
        <h2 id="photo-heading">{escape(prefecture)}の現地写真</h2>
        <p>写真は場所選びの参考に。クリックするとマンホール詳細を確認できます。</p>
      </div>
      {photo_html}
    </section>

    {events_html}<section class="trivia-card" aria-labelledby="trivia-heading">
      <span class="trivia-kicker">まず知りたい</span>
      <h2 id="trivia-heading">{escape(prefecture)}のポケふたトリビア</h2>
      {trivia_html}
    </section>

    <section id="manhole-list" aria-labelledby="manhole-heading">
      <div class="section-heading-row">
        <h2 id="manhole-heading">{escape(prefecture)}のマンホール一覧</h2>
        <p>訪れたポケふたを選び、写真を記録できます。</p>
      </div>
      <div class="manhole-grid">{manhole_html}</div>
    </section>

    {journey_html}

    <section aria-labelledby="pokemon-heading">
      <h2 id="pokemon-heading">{escape(prefecture)}で会えるポケモン</h2>
      <div class="pokemon-grid">{pokemon_html}</div>
    </section>

{related_section_html}"""
    else:
        main_sections_html = f"""    {_nearest_pokefuta_html(prefecture, nearest)}

    <!-- adsense:prefecture -->

{events_html}{related_section_html}

    {journey_html}"""
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
  <link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css"
    integrity="sha256-p4NxAoJBhIIN+hmNHrzRCf9tD/miZyoHS5obTRR9BMY=" crossorigin="">
  <script type="application/ld+json">{_json_for_script(json_ld)}</script>
  <style>
{PAGE_CSS}  </style>
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
        <h1>{escape(h1)}</h1>
        <p>{escape(hero_intro)}</p>
        <div class="stats" aria-label="{_escape_attr(prefecture)}の集計">
          <div class="stat"><span>設置枚数</span><strong>{count}枚</strong></div>
          <div class="stat"><span>全国順位</span><strong>{escape(rank_label)}</strong></div>
        </div>
        <div class="hero-actions">
          {hero_actions_html}
        </div>
        <p class="hero-note">{escape(hero_note)}</p>
        <div class="hero-utility">{official_cta}</div>
      </div>
      <div class="hero-summary" aria-label="{_escape_attr(prefecture)}のサマリー">
        <span>サマリー</span>
        <p>{escape(hero_summary)}</p>
      </div>
    </header>

{main_sections_html}
    <footer><a href="/summary/">全国のポケふた一覧へ戻る</a></footer>
  </main>
  <script src="/assets/analytics.js?v=20260929a"></script>
  <script>
    window.PokefutaAnalytics.init({{
      'page_path': '/prefectures/' + {_json_for_script(slug)} + '/',
      site_type: 'map',
      page_type: 'prefecture',
      prefecture: {_json_for_script(slug)}
    }});
    const prefectureEventDefaults = {{
      event_category: 'prefecture_growth',
      surface: 'prefecture_page',
      prefecture: {_json_for_script(slug)},
      prefecture_name: {_json_for_script(prefecture)}
    }};
    function trackPrefectureEvent(name, params) {{
      window.PokefutaAnalytics.trackEvent(name, Object.assign({{}}, prefectureEventDefaults, params || {{}}));
    }}
    window.PokefutaAnalytics.bindClickTracking(prefectureEventDefaults, {{ detail: true }});
    const sentScrollDepths = new Set();
    function reportScrollDepth() {{
      const scrollable = document.documentElement.scrollHeight - window.innerHeight;
      if (scrollable <= 0) return;
      const depth = Math.round(window.scrollY / scrollable * 100);
      [50, 90].forEach(function(threshold) {{
        if (depth >= threshold && !sentScrollDepths.has(threshold)) {{
          sentScrollDepths.add(threshold);
          trackPrefectureEvent('prefecture_scroll_depth', {{ percent_scrolled: threshold }});
        }}
      }});
      if (sentScrollDepths.size === 2) {{
        window.removeEventListener('scroll', reportScrollDepth);
      }}
    }}
    window.addEventListener('scroll', reportScrollDepth, {{ passive: true }});
  </script>
  <script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"
    integrity="sha256-20nQCchB9co0qIjJZRGuk2/Z9VM+kNiyxNV1lvTlZBo=" crossorigin=""></script>
{_map_script(map_points, _campaign_params(slug))}
</body>
</html>
"""


def generate_all(
    records: list[dict],
    pokemon_slugs: dict[str, str],
    trivia: dict[str, dict],
    output_dir: Path,
    events: dict[str, list[dict]] | None = None,
    photos: dict[str, dict] | None = None,
    visit_guides: dict[str, dict] | None = None,
) -> int:
    photos = photos or {}
    records_by_pref = {pref: [] for pref in PREFECTURE_ORDER}
    for record in records:
        prefecture = record.get("prefecture", "")
        if prefecture in records_by_pref:
            records_by_pref[prefecture].append(record)
    rankings = build_rankings(records)
    empty_prefectures = {
        pref for pref, items in records_by_pref.items() if not items
    }
    paths_by_pref: dict[str, dict[str, str]] = {}
    for (prefecture, name), path in municipality_page_paths(records).items():
        paths_by_pref.setdefault(prefecture, {})[name] = path
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
            (events or {}).get(prefecture),
            photos,
            empty_prefectures,
            (visit_guides or {}).get(prefecture),
            records,
            paths_by_pref.get(prefecture),
        )
        (out_dir / "index.html").write_text(html, encoding="utf-8")
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "index.html").write_text(
        build_index_page(records_by_pref, photos, trivia, events), encoding="utf-8"
    )
    return len(PREFECTURES)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--manholes", type=Path, default=DEFAULT_MANHOLES)
    parser.add_argument("--pokemon", type=Path, default=DEFAULT_POKEMON)
    parser.add_argument("--photos", type=Path, default=DEFAULT_PHOTOS)
    parser.add_argument("--trivia", type=Path, default=DEFAULT_TRIVIA)
    parser.add_argument("--events", type=Path, default=DEFAULT_EVENTS)
    parser.add_argument("--guides", type=Path, default=DEFAULT_GUIDES)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    records = load_records(args.manholes)
    # 公開する母数（42県）の前提を、ページを作る前に確かめる。ある県が
    # まるごと取りこぼされると、黙って母数から外れてコンプリート率が
    # 上がったように見えるので、気づけるようにここで止める。generate_all()
    # ではなく main() に置くのは、合成データで generate_all() を呼ぶ
    # デプロイ契約テストを巻き込まないため。
    records_by_pref: dict[str, list[dict]] = {}
    for record in records:
        if record.get("status", "active") == "active":
            records_by_pref.setdefault(record.get("prefecture", ""), []).append(record)
    verify_known_empty(records_by_pref, PREFECTURE_ORDER)
    pokemon_slugs = load_pokemon_slugs(args.pokemon)
    photos = load_photos(args.photos)
    trivia = load_trivia(args.trivia)
    events = load_events(args.events)
    visit_guides = load_visit_guides(args.guides)
    count = generate_all(records, pokemon_slugs, trivia, args.output, events, photos, visit_guides)
    print(
        f"[generate_prefecture_pages] wrote {count} pages to "
        f"{args.output.relative_to(ROOT) if args.output.is_relative_to(ROOT) else args.output}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
