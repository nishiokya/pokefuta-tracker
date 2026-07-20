#!/usr/bin/env python3
"""Generate static Japanese landing pages for all 47 prefectures."""

from __future__ import annotations

import argparse
import json
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
    from apps.scraper.prefectures import (
        PREFECTURES,
        PREFECTURE_ORDER,
        PREFECTURE_SLUGS,
    )
except ModuleNotFoundError as exc:
    if exc.name != "apps":
        raise
    from prefectures import PREFECTURES, PREFECTURE_ORDER, PREFECTURE_SLUGS

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_MANHOLES = ROOT / "docs" / "pokefuta.ndjson"
DEFAULT_POKEMON = ROOT / "docs" / "pokemon_metadata.json"
DEFAULT_PHOTOS = ROOT / "docs" / "latest-manhole-photos.json"
DEFAULT_TRIVIA = ROOT / "dataset" / "prefecture_trivia.json"
DEFAULT_EVENTS = ROOT / "dataset" / "prefecture_events.json"
JST = timezone(timedelta(hours=9))
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


def _events_html(events: list[dict] | None, today: date | None = None) -> str:
    today = today or datetime.now(JST).date()
    active = [e for e in events or [] if e["end"] >= today]
    if not active:
        return ""
    items = []
    for event in active:
        status = "開催中" if event["start"] <= today else "まもなく開催"
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
            return datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            continue
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
    return (
        "from=data&utm_source=data.pokefuta.com&utm_medium=referral"
        f"&utm_campaign=prefecture_page&utm_content={quote(slug)}"
    )


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
    entries = _photo_entries(installed_records, photos)
    photo_ids = {str(record.get("id", "")) for record, _ in entries}
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
    for position, (record, photo) in enumerate(entries[:4], start=1):
        mid = str(record.get("id", "")).strip()
        city = str(record.get("city", "") or "所在地不明")
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
            f'alt="{_escape_attr(prefecture)}{_escape_attr(city)}のポケふた投稿写真" '
            f'loading="lazy" decoding="async" width="640" height="480">'
            f'<span><strong>{escape(city)}</strong><small>{escape(pokemons)}</small>'
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

    missing_records = [
        record for record in installed_records
        if str(record.get("id", "")) not in photo_ids
    ][:3]
    contribution_cards = []
    for position, record in enumerate(missing_records, start=1):
        mid = str(record.get("id", "")).strip()
        city = str(record.get("city", "") or "所在地不明")
        pokemons = "・".join(_clean_pokemons(record)) or "ポケモン"
        contribution_cards.append(
            f'<a class="contribution-card" href="{_escape_attr(_upload_url(mid, slug))}" '
            f'data-track="prefecture_photo_upload_start" data-position="{position}" '
            f'data-destination="upload" data-content-id="{_escape_attr(mid)}" '
            f'data-surface="photo_contribution" '
            f'data-photo-state="missing">'
            f'<span>写真募集中</span><strong>{escape(city)}</strong>'
            f'<small>{escape(pokemons)}</small><b>最初の写真を投稿 →</b></a>'
        )
    contribution_html = (
        '<div class="contribution-panel">'
        f'<div><strong>写真未掲載のポケふたは{missing}地点</strong>'
        '<p>対象を選んだ後にログインします。投稿写真は詳細ページとこの県ページに掲載されます。</p></div>'
        f'<div class="contribution-grid">{"".join(contribution_cards)}</div></div>'
        if missing_records else (
            '<div class="contribution-panel contribution-complete">'
            '<div><strong>すべてのポケふたに現地写真があります</strong>'
            '<p>季節や旅の思い出が伝わる写真も歓迎しています。</p></div>'
            '<a class="inline-link" href="#manhole-list" '
            'data-track="prefecture_photo_candidate_click" data-destination="manhole_list">'
            '投稿するポケふたを選ぶ</a></div>'
        )
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
        city = record.get("city", "") or "所在地不明"
        pokemons = "・".join(_clean_pokemons(record)) or "ポケモン"
        image_path = ROOT / "dataset" / "manhole" / "image" / f"{mid}_latest.jpeg"
        image_html = (
            f'<img src="/manhole/image/{quote(mid)}_latest.jpeg" '
            f'alt="{_escape_attr(city)}のポケふた" loading="lazy" width="128" height="128">'
            if image_path.exists()
            else '<span class="manhole-placeholder" aria-hidden="true">●</span>'
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
        cards.append(
            f'<article class="manhole-card" data-manhole-id="{_escape_attr(mid)}">'
            f'<a class="manhole-detail" href="/manholes/{quote(mid)}/" '
            f'data-track="prefecture_manhole_click" data-position="{position}" '
            f'data-destination="{_escape_attr(mid)}" data-content-id="{_escape_attr(mid)}" '
            f'data-surface="manhole_card">'
            f'{image_html}<span class="manhole-copy"><strong>{escape(city)}</strong>'
            f'<small>{escape(pokemons)}</small>{preinstall_badge_html}'
            f'<b class="photo-status{photo_class}">{photo_label}</b></span></a>'
            f'<div class="{actions_class}"><a href="/manholes/{quote(mid)}/" '
            f'data-track="prefecture_manhole_click" data-position="{position}" '
            f'data-destination="{_escape_attr(mid)}" data-content-id="{_escape_attr(mid)}" '
            f'data-surface="manhole_actions">詳細</a>'
            f'{maps_html}{upload_html}</div></article>'
        )
    return "".join(cards)


def _related_prefectures(prefecture: str) -> str:
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
        if name != prefecture
    )
    return (
        f'<p class="related-label">{escape(region_name)}のポケふた</p>'
        f'<div class="related-links">{links}</div>'
    )


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


def build_page(
    prefecture: str,
    slug: str,
    records: list[dict],
    rank: int | None,
    pokemon_slugs: dict[str, str],
    trivia_entry: dict | None,
    events: list[dict] | None = None,
    photos: dict[str, dict] | None = None,
) -> str:
    photos = photos or {}
    count = len(records)
    installed_records = [
        record for record in records if record.get("installed") is not False
    ]
    installed_count = len(installed_records)
    canonical = f"{BASE_URL}/prefectures/{slug}/"
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
            "city": record.get("city", ""),
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
    related_html = _related_prefectures(prefecture)
    visits_url = _visits_url(slug)
    nearby_url = _nearby_url(slug)
    if installed_count:
        hero_actions_html = (
            '<a class="button primary" href="#manhole-list" '
            'data-track="prefecture_photo_candidate_click" '
            'data-legacy-track="prefecture_photo_cta_click" '
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
    .hero {{
      position: relative; overflow: hidden; margin-top: 14px; padding: 28px;
      display: grid; grid-template-columns: minmax(0, 1fr) 280px; gap: 22px;
      align-items: center;
      border: 1px solid rgba(93,67,35,.15); border-radius: 24px;
      background: linear-gradient(135deg, #fffaf0, #f0e9fb);
      box-shadow: 0 14px 32px rgba(77,56,30,.08);
    }}
    .hero::after {{
      content: ""; position: absolute; width: 230px; height: 230px;
      right: -70px; top: -90px; border: 42px solid rgba(126,107,169,.1);
      border-radius: 50%;
    }}
    .hero-kicker {{ margin: 0; color: #6b4aa2; font-size: .8rem; font-weight: 900; }}
    h1 {{ margin: 4px 0 8px; font-size: clamp(2rem, 7vw, 3.5rem); line-height: 1.15; }}
    .hero-main > p:last-of-type {{ max-width: 720px; margin: 0; color: #574b41; font-weight: 650; }}
    .hero-summary {{
      position: relative; z-index: 1; padding: 16px 18px; border-radius: 17px;
      background: rgba(255,255,255,.74); color: #3a3128;
      box-shadow: inset 0 0 0 1px rgba(93,67,35,.11);
    }}
    .hero-summary span {{
      display: block; margin-bottom: 6px; color: #6b4aa2;
      font-size: .76rem; font-weight: 900;
    }}
    .hero-summary p {{ margin: 0; font-size: .96rem; font-weight: 800; }}
    .stats {{ display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 10px; margin-top: 18px; }}
    .stat {{ padding: 14px; border-radius: 15px; background: rgba(255,255,255,.72); }}
    .stat span {{ display: block; color: #75685c; font-size: .76rem; font-weight: 850; }}
    .stat strong {{ display: block; color: #57408f; font-size: 1.55rem; line-height: 1.3; }}
    .hero-actions {{ display: flex; flex-wrap: wrap; gap: 10px; margin-top: 18px; }}
    .button {{
      display: inline-flex; align-items: center; min-height: 44px; padding: 0 16px;
      border-radius: 999px; background: #176f68; color: white; font-weight: 900;
      text-decoration: none;
    }}
    .button.primary {{ background: #b5483c; }}
    .button.secondary {{ background: #6b4aa2; }}
    .button.tertiary {{
      background: white; color: #176f68; box-shadow: inset 0 0 0 1px #9fc7c2;
    }}
    .button.official {{ background: #8a5a20; }}
    .hero-note {{ margin: 10px 0 0; color: #75685c; font-size: .78rem; font-weight: 750; }}
    .hero-utility {{ margin-top: 10px; }}
    .hero-utility:empty {{ display: none; }}
    section {{
      margin-top: 22px; padding: 20px; border: 1px solid rgba(93,67,35,.14);
      border-radius: 19px; background: #fffaf0;
      box-shadow: 0 8px 20px rgba(77,56,30,.05);
    }}
    h2 {{ margin: 0 0 12px; font-size: 1.35rem; line-height: 1.35; }}
    .section-heading-row {{
      display: flex; justify-content: space-between; align-items: flex-start; gap: 16px;
      margin-bottom: 12px;
    }}
    .section-heading-row h2, .section-heading-row p {{ margin: 0; }}
    .section-heading-row p {{ max-width: 520px; color: #75685c; font-size: .86rem; }}
    .map-toolbar {{
      display: flex; flex-wrap: wrap; justify-content: space-between; gap: 10px;
      align-items: center; margin-bottom: 10px;
    }}
    .map-legend {{ display: flex; flex-wrap: wrap; gap: 10px; color: #62564a; font-size: .78rem; font-weight: 800; }}
    .map-legend span {{ display: inline-flex; align-items: center; gap: 5px; }}
    .legend-dot {{ width: 12px; height: 12px; border: 3px solid white; border-radius: 50%; box-shadow: 0 0 0 1px rgba(32,27,22,.2); }}
    .legend-dot.has-photo {{ background: #2d846c; }}
    .legend-dot.needs-photo {{ background: #d78548; }}
    .legend-dot.preinstall {{ background: #8b8f94; }}
    .nearby-link, .inline-link {{
      display: inline-flex; align-items: center; min-height: 44px; padding: 0 14px;
      border-radius: 999px; background: #e6f2ef; color: #176f68;
      font-size: .84rem; font-weight: 900; text-decoration: none;
    }}
    #prefecture-map {{ height: 430px; border-radius: 14px; background: #e9e3d6; }}
    #prefecture-map.map-empty {{ display: grid; place-items: center; color: #75685c; font-weight: 850; }}
    .map-note {{ margin: 10px 0 0; color: #75685c; font-size: .8rem; }}
    .prefecture-marker {{
      width: 28px; height: 28px; border: 4px solid white; border-radius: 50% 50% 50% 8px;
      transform: rotate(-45deg); box-shadow: 0 3px 8px rgba(32,27,22,.35);
    }}
    .prefecture-marker.has-photo {{ background: #2d846c; }}
    .prefecture-marker.needs-photo {{ background: #d78548; }}
    .prefecture-marker.preinstall {{ background: #8b8f94; }}
    .map-popup {{ min-width: 210px; }}
    .map-popup img {{
      display: block; width: 100%; height: 120px; margin: 8px 0; border-radius: 10px;
      object-fit: cover;
    }}
    .map-popup-photo-missing {{
      margin: 8px 0; padding: 8px; border-radius: 9px; background: #fff0e5;
      color: #8d4a22; font-size: .78rem; font-weight: 850;
    }}
    .map-popup-preinstall {{
      margin: 8px 0; padding: 8px; border-radius: 9px; background: #f0ede7;
      color: #625b53; font-size: .78rem; font-weight: 850;
    }}
    .map-popup-actions {{ display: grid; grid-template-columns: repeat(3, 1fr); gap: 5px; margin-top: 9px; }}
    .map-popup-actions.preinstall-actions {{ grid-template-columns: repeat(2, 1fr); }}
    .map-popup-actions a {{
      display: grid; place-items: center; min-height: 38px; padding: 5px;
      border-radius: 8px; background: #ece7f7; color: #4f3a79;
      font-size: .72rem; text-align: center; text-decoration: none;
    }}
    .map-popup-actions a.upload {{ background: #b5483c; color: white; }}
    .photo-inventory {{
      display: grid; grid-template-columns: minmax(0, 1fr) 180px auto; gap: 14px;
      align-items: center; margin-bottom: 16px;
    }}
    .photo-inventory strong {{ color: #57408f; font-size: 1.8rem; line-height: 1; }}
    .photo-inventory strong span {{ color: #75685c; font-size: .9rem; }}
    .photo-inventory p {{ margin: 5px 0 0; color: #62564a; }}
    .photo-inventory > b {{ color: #57408f; }}
    .coverage-meter {{ height: 10px; overflow: hidden; border-radius: 999px; background: #e5ddd0; }}
    .coverage-meter span {{ display: block; height: 100%; border-radius: inherit; background: #6b4aa2; }}
    .photo-showcase-grid {{
      display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 10px;
      margin-bottom: 14px;
    }}
    .photo-card {{ overflow: hidden; border: 1px solid rgba(93,67,35,.13); border-radius: 14px; background: white; }}
    .photo-card-image {{ display: block; color: inherit; text-decoration: none; }}
    .photo-card-image img {{
      display: block; width: 100%; aspect-ratio: 4 / 3; height: auto; object-fit: cover;
      background: #e9e3d6;
    }}
    .photo-card-image > span {{ display: grid; padding: 9px 10px; }}
    .photo-card-image small {{ overflow: hidden; color: #75685c; font-size: .72rem; text-overflow: ellipsis; white-space: nowrap; }}
    .photo-card-poster {{ display: block; padding: 0 10px 9px; overflow: hidden; color: #75685c; font-size: .72rem; text-overflow: ellipsis; white-space: nowrap; }}
    .photo-card-poster a {{ color: #176f68; font-weight: 800; text-decoration: underline; text-underline-offset: 2px; }}
    .photo-card-upload {{
      display: grid; place-items: center; min-height: 44px; padding: 6px 9px;
      border-top: 1px solid #ece4d7; color: #176f68; font-size: .75rem;
      font-weight: 900; text-align: center; text-decoration: none;
    }}
    .contribution-panel {{
      display: grid; grid-template-columns: minmax(220px, .8fr) minmax(0, 1.2fr);
      gap: 14px; align-items: center; padding: 14px; border-radius: 14px;
      background: #fff0e5;
    }}
    .contribution-panel p {{ margin: 4px 0 0; color: #75685c; font-size: .82rem; }}
    .contribution-grid {{ display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 8px; }}
    .contribution-card {{
      display: grid; min-width: 0; padding: 10px; border-radius: 11px; background: white;
      color: inherit; text-decoration: none;
    }}
    .contribution-card span {{ color: #b5483c; font-size: .68rem; font-weight: 950; }}
    .contribution-card small {{ overflow: hidden; color: #75685c; font-size: .72rem; text-overflow: ellipsis; white-space: nowrap; }}
    .contribution-card b {{ margin-top: 6px; color: #176f68; font-size: .75rem; }}
    .contribution-complete {{ grid-template-columns: 1fr auto; background: #edf8f2; }}
    .photo-empty-state {{ padding: 18px; border-radius: 14px; background: #f3efe7; }}
    .photo-empty-state p {{ margin: 4px 0 12px; color: #75685c; }}
    .pokemon-grid {{ display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 8px; }}
    .pokemon-card {{
      display: grid; gap: 2px; padding: 12px; border: 1px solid rgba(93,67,35,.13);
      border-radius: 13px; background: white; color: inherit; text-decoration: none;
    }}
    .pokemon-card strong {{ color: #3d2b72; }}
    .pokemon-card span {{ color: #75685c; font-size: .75rem; font-weight: 750; }}
    .pokemon-more {{ grid-column: 1 / -1; }}
    .pokemon-more summary {{
      width: fit-content; margin: 12px auto 0; padding: 8px 14px;
      border-radius: 999px; background: #eee7fb; color: #57408f;
      cursor: pointer; font-size: .82rem; font-weight: 900;
    }}
    .pokemon-more-grid {{
      display: grid; grid-template-columns: repeat(3, minmax(0, 1fr));
      gap: 8px; margin-top: 12px;
    }}
    .manhole-grid {{ display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 10px; }}
    .manhole-card {{
      overflow: hidden; border: 1px solid rgba(93,67,35,.13);
      border-radius: 14px; background: white;
    }}
    .manhole-detail {{
      display: grid; grid-template-columns: 72px minmax(0,1fr); align-items: center;
      gap: 12px; min-height: 88px; padding: 8px; color: inherit; text-decoration: none;
    }}
    .manhole-card img, .manhole-placeholder {{
      width: 72px; height: 72px; border-radius: 50%; object-fit: cover;
    }}
    .manhole-placeholder {{
      display: grid; place-items: center; background: #eee7fb; color: #7654aa; font-size: 2rem;
    }}
    .manhole-copy {{ min-width: 0; }}
    .manhole-copy strong, .manhole-copy small {{ display: block; }}
    .manhole-copy small {{ overflow: hidden; color: #75685c; text-overflow: ellipsis; white-space: nowrap; }}
    .photo-status {{
      display: inline-flex; width: fit-content; margin-top: 4px; padding: 2px 7px;
      border-radius: 999px; font-size: .68rem;
    }}
    .photo-ready {{ background: #e4f2ee; color: #176f68; }}
    .photo-needed {{ background: #fff0e5; color: #9b4b20; }}
    .photo-pending {{ background: #f0ede7; color: #6f6254; }}
    .manhole-actions {{ display: grid; grid-template-columns: repeat(3, 1fr); border-top: 1px solid #ece4d7; }}
    .manhole-actions.preinstall-actions {{ grid-template-columns: repeat(2, 1fr); }}
    .manhole-actions a {{
      display: grid; place-items: center; min-height: 44px; padding: 5px;
      color: #57408f; font-size: .76rem; font-weight: 900; text-align: center;
      text-decoration: none;
    }}
    .manhole-actions a + a {{ border-left: 1px solid #ece4d7; }}
    .manhole-actions a.upload {{ background: #b5483c; color: white; }}
    .journey-loop {{ background: linear-gradient(135deg, #f1f8f6, #f5effc); }}
    .journey-steps {{
      display: grid; grid-template-columns: repeat(4, 1fr); gap: 8px;
      margin: 14px 0;
    }}
    .journey-step {{ padding: 12px; border-radius: 12px; background: white; font-size: .82rem; font-weight: 850; }}
    .journey-step span {{ display: block; color: #6b4aa2; font-size: .7rem; }}
    .journey-actions {{ display: flex; flex-wrap: wrap; gap: 8px; }}
    .manhole-preinstall-badge {{
      display: inline-block; margin-top: 4px; padding: 2px 8px;
      border-radius: 999px; background: #f1ede4; color: #6b5d44;
      font-size: .74rem; font-weight: 700; white-space: nowrap;
    }}
    .trivia-card {{
      border-left: 5px solid #7e6ba9;
      background: linear-gradient(135deg, #fffaf0, #f4effd);
    }}
    .trivia-kicker {{
      display: inline-flex; margin: 0 0 6px; padding: 3px 9px;
      border-radius: 999px; background: #6b4aa2; color: white;
      font-size: .72rem; font-weight: 900;
    }}
    .trivia-card p {{ margin: 0; font-size: 1.05rem; font-weight: 750; }}
    .trivia-source {{ margin-top: 8px; font-size: .78rem; }}
    .event-card {{
      border-left: 5px solid #176f68;
      background: linear-gradient(135deg, #fffaf0, #edf8f2);
    }}
    .event-item + .event-item {{ margin-top: 14px; }}
    .event-status {{
      display: inline-flex; margin: 0 0 6px; padding: 3px 9px;
      border-radius: 999px; background: #176f68; color: white;
      font-size: .72rem; font-weight: 900;
    }}
    .event-item strong {{ display: block; }}
    .event-item strong a {{ color: #14544f; }}
    .event-item p {{ margin: 6px 0 0; font-size: .92rem; }}
    .event-period {{ color: #75685c; font-size: .78rem; }}
    .empty-state {{ margin: 0; color: #75685c; }}
    .related-label {{ margin: 0 0 8px; color: #75685c; font-size: .8rem; font-weight: 850; }}
    .related-links {{ display: flex; flex-wrap: wrap; gap: 8px; }}
    .related-links a {{
      padding: 6px 10px; border-radius: 999px; background: #eee7fb;
      color: #57408f; font-size: .82rem; font-weight: 850; text-decoration: none;
    }}
    footer {{ margin-top: 24px; color: #75685c; font-size: .8rem; text-align: center; }}
    .leaflet-popup-content a {{ font-weight: 850; }}
    @media (max-width: 700px) {{
      .hero {{ display: block; padding: 22px 18px; }}
      .hero-summary {{ display: none; }}
      .hero-actions {{ display: grid; grid-template-columns: 1fr 1fr; }}
      .hero-actions .button {{ justify-content: center; padding: 0 12px; text-align: center; }}
      .hero-actions .button.primary {{ grid-column: 1 / -1; }}
      .section-heading-row {{ display: block; }}
      .section-heading-row p {{ margin-top: 4px; }}
      .photo-inventory {{ grid-template-columns: minmax(0, 1fr) auto; }}
      .coverage-meter {{ grid-column: 1 / -1; grid-row: 2; }}
      .photo-showcase-grid {{ grid-template-columns: repeat(2, minmax(0, 1fr)); }}
      .contribution-panel, .contribution-complete {{ grid-template-columns: 1fr; }}
      .contribution-grid {{ grid-template-columns: 1fr; }}
      .journey-steps {{ grid-template-columns: repeat(2, 1fr); }}
      .pokemon-grid, .pokemon-more-grid, .manhole-grid {{ grid-template-columns: 1fr; }}
      #prefecture-map {{ height: 360px; }}
      section {{ padding: 16px; }}
    }}
  </style>
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
        <h1>{escape(prefecture)}のポケふた</h1>
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

    <section aria-labelledby="related-heading">
      <h2 id="related-heading">近くの都道府県から探す</h2>
      {related_html}
    </section>
    <footer><a href="/summary/">全国のポケふた一覧へ戻る</a></footer>
  </main>
  <script async src="https://www.googletagmanager.com/gtag/js?id=G-K18NR4GZG2"></script>
  <script>
    window.dataLayer = window.dataLayer || [];
    function gtag() {{ dataLayer.push(arguments); }}
    gtag('js', new Date());
    gtag('config', 'G-K18NR4GZG2', {{
      'page_path': '/prefectures/' + {_json_for_script(slug)} + '/',
      site_type: 'map',
      page_type: 'prefecture',
      prefecture: {_json_for_script(slug)}
    }});
    function trackPrefectureEvent(name, params) {{
      if (typeof window.gtag !== 'function') return;
      gtag('event', name, Object.assign({{
        event_category: 'prefecture_growth',
        prefecture: {_json_for_script(slug)},
        prefecture_name: {_json_for_script(prefecture)}
      }}, params || {{}}));
    }}
    document.addEventListener('click', function(event) {{
      const link = event.target.closest('[data-track]');
      if (!link) return;
      trackPrefectureEvent(link.dataset.track, {{
        position: Number(link.dataset.position || 0),
        destination: link.dataset.destination || '',
        content_id: link.dataset.contentId || '',
        photo_state: link.dataset.photoState || '',
        surface: link.dataset.surface || ''
      }});
      if (link.dataset.legacyTrack) {{
        trackPrefectureEvent(link.dataset.legacyTrack, {{
          destination: link.dataset.destination || '',
          surface: link.dataset.surface || 'hero'
        }});
      }}
    }});
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
  <script>
    const points = {_json_for_script(map_points)};
    const campaignParams = {_json_for_script(_campaign_params(slug))};
    const mapElement = document.getElementById('prefecture-map');
    if (!points.length) {{
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
              escapeHtml(point.city || '所在地不明') + 'のポケふた投稿写真" ' +
              'loading="lazy" decoding="async" width="320" height="240">'
            : '<div class="map-popup-photo-missing">このポケふたは写真募集中です</div>');
        const uploadHtml = point.is_preinstall
          ? ''
          : '<a class="upload" href="' + escapeHtml(uploadUrl) +
            '" data-track="prefecture_photo_upload_start" data-destination="upload" ' +
            'data-content-id="' + escapeHtml(point.id) +
            '" data-surface="map_popup" data-photo-state="' + photoState + '">写真投稿</a>';
        const popupHtml = '<div class="map-popup"><strong>' +
          escapeHtml(point.city || '所在地不明') + '</strong><br>' +
          escapeHtml(pokemon) + photoHtml + '<div class="map-popup-actions' +
          (point.is_preinstall ? ' preinstall-actions' : '') + '">' +
          '<a href="' + detailUrl + '" data-track="prefecture_manhole_click" ' +
          'data-destination="' + escapeHtml(point.id) + '" data-content-id="' + escapeHtml(point.id) +
          '" data-surface="map_popup">詳細</a>' +
          '<a href="' + escapeHtml(googleMapsUrl) +
          '" target="_blank" rel="noopener noreferrer" ' +
          'data-track="prefecture_google_maps_click" data-destination="google_maps" ' +
          'data-content-id="' + escapeHtml(point.id) + '" data-surface="map_popup">行き方</a>' +
          uploadHtml + '</div></div>';
        const marker = L.marker(latlng, {{
          title: (point.city || '所在地不明') + 'のポケふた',
          alt: (point.city || '所在地不明') + 'のポケふた・' +
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
          trackPrefectureEvent('prefecture_map_pin_click', {{
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
        trackPrefectureEvent('prefecture_map_interaction', {{ interaction: interaction }});
      }}
      mapElement.addEventListener('pointerdown', function() {{ reportMapInteraction('pointer'); }}, {{ once: true }});
      mapElement.addEventListener('keydown', function() {{ reportMapInteraction('keyboard'); }}, {{ once: true }});
    }}
    function escapeHtml(value) {{
      return String(value).replace(/[&<>"']/g, function(char) {{
        return {{'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}}[char];
      }});
    }}
  </script>
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
) -> int:
    photos = photos or {}
    records_by_pref = {pref: [] for pref in PREFECTURE_ORDER}
    for record in records:
        prefecture = record.get("prefecture", "")
        if prefecture in records_by_pref:
            records_by_pref[prefecture].append(record)
    rankings = build_rankings(records)
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
        )
        (out_dir / "index.html").write_text(html, encoding="utf-8")
    return len(PREFECTURES)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--manholes", type=Path, default=DEFAULT_MANHOLES)
    parser.add_argument("--pokemon", type=Path, default=DEFAULT_POKEMON)
    parser.add_argument("--photos", type=Path, default=DEFAULT_PHOTOS)
    parser.add_argument("--trivia", type=Path, default=DEFAULT_TRIVIA)
    parser.add_argument("--events", type=Path, default=DEFAULT_EVENTS)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    records = load_records(args.manholes)
    pokemon_slugs = load_pokemon_slugs(args.pokemon)
    photos = load_photos(args.photos)
    trivia = load_trivia(args.trivia)
    events = load_events(args.events)
    count = generate_all(records, pokemon_slugs, trivia, args.output, events, photos)
    print(
        f"[generate_prefecture_pages] wrote {count} pages to "
        f"{args.output.relative_to(ROOT) if args.output.is_relative_to(ROOT) else args.output}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
