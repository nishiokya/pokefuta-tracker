#!/usr/bin/env python3
"""図鑑トップ（index.html）の、データで変わる部分を生成時に静的HTMLへ焼き込む。

以前のトップは件数・都道府県一覧・写真を実行時の fetch で差し込んでいたため、
クロールされるHTMLには「—」や「読み込み中…」しか無く、meta description も
「47都道府県」のまま実データ（設置は42都道府県）と食い違っていた。
ここでは次のブロックを `<!-- home:NAME:start -->` 〜 `<!-- home:NAME:end -->` の間へ描画する。

- head      … description / og / twitter の説明文と JSON-LD（WebSite・CollectionPage・ItemList・BreadcrumbList）
- hero      … H1・導入文・件数・3つの主導線。デスクトップは都道府県ピンつきの大地図（ピンは JSON で埋め込み）、
              スマホは投稿写真モザイク（6枚。<picture> でデスクトップでは写真を取得しない）
- ways      … 地図・都道府県・ポケモン・テーマの4つの探し方
- newrelease… 直近30日の新作と特集（/features/）への入口。highlight_until 中の特集は帯で目立たせ、
              特集一覧へのリンクは特集が1本でもあれば常に出す（新作も特集も無ければセクションごと出さない）
- photos    … 新着・注目の写真（地域が偏らないよう地方ごとに順番に選ぶ）
- events    … 開催中イベント（上位3件＋残りは折りたたみ。イベント名のポケモンの写真を1枚添える）
- pref      … 設置のある都道府県を地方別に、未設置の県は短い注記に分ける
- trips     … ポケふた旅（目的から探す。枚数・かかる時間の多いエリアをカードで。続きは /trip/）
- tripsmore / themesmore … 目的から探すの見出し横の一覧リンク（「1日で回るルート一覧 9ルート」など）
- pokemon   … 設置の多いポケモン（写真つきカード。/pokemon/ と同じ突き合わせ規則。写真は
              dataset/pokemon_representatives.json の代表を優先し、無ければ新しい投稿）

写真はローカルミラー `dataset/manhole/image/{id}_latest.jpeg`（720×720）が
存在する投稿だけを使い、外部画像は埋め込まない。件数はすべて同じ生成時データから出す。
テーマチップ（tag-chips マーカー）は generate_top_tag_chips.py の担当なので触らない。

Usage:
  python3 apps/scraper/generate_top_page.py            # apps/web/index.html を更新
  python3 apps/scraper/generate_top_page.py dist/index.html
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from html import escape
from pathlib import Path
from urllib.parse import quote

sys.path.insert(0, str(Path(__file__).parent))

try:
    from apps.scraper.display_names import compose_display_name
    from apps.scraper.features import DEFAULT_FEATURES_DIR, feature_path, highlighted, load_features
    from apps.scraper.generate_pokemon_index_page import load_representatives
    from apps.scraper.generate_pokemon_pages import build_pokemon_index, load_pokemon_metadata
    from apps.scraper.generate_tag_pages import load_records
    from apps.scraper.generate_trip_pages import area_records, area_route
    from apps.scraper.manhole_tile_image import tile_image_url
    from apps.scraper.visit_durations import (
        MODE_LABELS, duration_range, find_entry, load_durations, load_trip_areas, travel_mode, trip_path,
    )
    from apps.scraper.photo_caption import JST, format_photo_date, to_jst_date
    from apps.scraper.prefectures import PREFECTURE_ORDER, PREFECTURE_SLUGS, REGIONS
    from apps.scraper.tag_meta import count_tags, load_tag_meta
except ModuleNotFoundError as exc:
    if exc.name != "apps":
        raise
    from display_names import compose_display_name
    from features import DEFAULT_FEATURES_DIR, feature_path, highlighted, load_features
    from generate_pokemon_index_page import load_representatives
    from generate_pokemon_pages import build_pokemon_index, load_pokemon_metadata
    from generate_tag_pages import load_records
    from generate_trip_pages import area_records, area_route
    from manhole_tile_image import tile_image_url
    from visit_durations import (
        MODE_LABELS, duration_range, find_entry, load_durations, load_trip_areas, travel_mode, trip_path,
    )
    from photo_caption import JST, format_photo_date, to_jst_date
    from prefectures import PREFECTURE_ORDER, PREFECTURE_SLUGS, REGIONS
    from tag_meta import count_tags, load_tag_meta

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_TARGET = ROOT / "apps" / "web" / "index.html"
DEFAULT_MANHOLES = ROOT / "docs" / "pokefuta.ndjson"
DEFAULT_PHOTOS = ROOT / "docs" / "latest-manhole-photos.json"
DEFAULT_STATS = ROOT / "docs" / "api" / "site-stats.json"
DEFAULT_EVENTS = ROOT / "dataset" / "prefecture_events.json"
DEFAULT_IMAGE_DIR = ROOT / "dataset" / "manhole" / "image"

BASE_URL = "https://data.pokefuta.com/"
SITE_NAME = "ポケふた図鑑"
PAGE_TITLE = "ポケふた図鑑｜全国のポケモンマンホール一覧・地図"
UPLOAD_URL = "https://pokefuta.com/upload?from=data"

HERO_PHOTO_LIMIT = 6
GALLERY_PHOTO_LIMIT = 9  # スマホ・タブレットは3列×3行、PC は先頭6枚（CSS）
EVENT_VISIBLE_LIMIT = 3
TRIP_LIMIT = 4  # 「目的から探す」に出すポケふた旅のエリア数
TRIP_THUMB_LIMIT = 4  # カードに並べる蓋の画像の数。残りは「+n」（カードの大きさをそろえる）
NEW_RELEASE_DAYS = 30
PHOTO_SIZE = 720  # ローカルミラーは 720×720
LID_SIZE = 360  # 蓋の枠に合わせた切り出し {id}_lid.jpeg
EXCLUDED_POKEMON_PATTERN = "ローカルActs"

REGION_OF = {pref: name for name, prefs in REGIONS for pref in prefs}

# ヒーロー地図の県ピンの位置（旧トップの PREF_COORDS と同じ）
PREF_COORDS: dict[str, tuple[float, float]] = {
    "北海道": (43.2, 142.8), "青森県": (40.8, 140.7), "岩手県": (39.7, 141.2), "宮城県": (38.4, 140.8),
    "秋田県": (39.7, 140.1), "山形県": (38.5, 140.3), "福島県": (37.4, 140.5), "茨城県": (36.3, 140.3),
    "栃木県": (36.5, 139.9), "群馬県": (36.4, 138.9), "埼玉県": (36.0, 139.4), "千葉県": (35.6, 140.1),
    "東京都": (35.7, 139.7), "神奈川県": (35.5, 139.5), "新潟県": (37.6, 139.0), "富山県": (36.7, 137.2),
    "石川県": (36.6, 136.6), "福井県": (36.1, 136.2), "山梨県": (35.7, 138.6), "長野県": (36.2, 138.0),
    "岐阜県": (35.8, 137.0), "静岡県": (34.9, 138.4), "愛知県": (35.1, 137.0), "三重県": (34.7, 136.5),
    "滋賀県": (35.1, 136.2), "京都府": (35.2, 135.8), "大阪府": (34.7, 135.5), "兵庫県": (34.9, 135.2),
    "奈良県": (34.4, 135.8), "和歌山県": (33.9, 135.2), "鳥取県": (35.5, 134.3), "島根県": (35.1, 133.1),
    "岡山県": (34.7, 133.9), "広島県": (34.5, 132.5), "山口県": (34.2, 131.5), "徳島県": (34.0, 134.5),
    "香川県": (34.3, 134.0), "愛媛県": (33.9, 132.8), "高知県": (33.6, 133.5), "福岡県": (33.6, 130.4),
    "佐賀県": (33.3, 130.2), "長崎県": (32.8, 129.9), "熊本県": (32.8, 130.7), "大分県": (33.2, 131.6),
    "宮崎県": (31.9, 131.4), "鹿児島県": (31.6, 130.6), "沖縄県": (26.2, 127.7),
}

DEFAULT_POKEMON_METADATA = ROOT / "docs" / "pokemon_metadata.json"
DEFAULT_REPRESENTATIVES = ROOT / "dataset" / "pokemon_representatives.json"
DEFAULT_TRIP_AREAS = ROOT / "dataset" / "trip_areas.json"
DEFAULT_DURATIONS = ROOT / "dataset" / "visit_durations.json"
POPULAR_POKEMON_LIMIT = 5
FORM_PREFIX = {"alola": "アローラ", "galar": "ガラル", "hisui": "ヒスイ", "paldea": "パルデア"}

MARKER_RE = re.compile(
    r"(?P<indent>[ \t]*)<!-- home:(?P<name>[a-z]+):start -->.*?<!-- home:(?P=name):end -->",
    re.DOTALL,
)


# ── データ ────────────────────────────────────────────────────────────────


@dataclass
class Photo:
    manhole_id: str
    created_at: str
    prefecture: str
    pokemons: list[str]
    place: str
    has_lid: bool = False  # 蓋の枠に合わせて切り出した {id}_lid.jpeg（360×360）がある

    @property
    def src(self) -> str:
        return f"manhole/image/{quote(self.manhole_id, safe='')}_latest.jpeg"

    @property
    def thumb_src(self) -> tuple[str, int]:
        """小さく出すときの画像と一辺の画素数。蓋の切り出しがあればそれ（軽く、絵が大きく見える）。"""
        if self.has_lid:
            return f"manhole/image/{quote(self.manhole_id, safe='')}_lid.jpeg", LID_SIZE
        return self.src, PHOTO_SIZE

    @property
    def href(self) -> str:
        return f"manholes/{quote(self.manhole_id, safe='')}/"

    @property
    def title(self) -> str:
        return "・".join(self.pokemons[:2]) or "ポケふた"

    @property
    def alt(self) -> str:
        names = "・".join(self.pokemons[:2])
        subject = f"{self.prefecture}{self.place}のポケふた"
        return f"{subject}（{names}）の投稿写真" if names else f"{subject}の投稿写真"


@dataclass
class PokemonEntry:
    name: str
    slug: str
    manhole_ids: list[str]
    representative_id: str = ""  # 人が選んだ代表のマンホール（無ければ空）

    @property
    def href(self) -> str:
        return f"pokemon/{quote(self.slug, safe='')}/"


def build_pokemon_entries(
    records: list[dict],
    metadata_path: Path | None,
    representatives_path: Path | None = DEFAULT_REPRESENTATIVES,
) -> list[PokemonEntry]:
    """設置枚数の多い順のポケモン。枚数と行き先は /pokemon/<slug>/ と同じ突き合わせ規則で出す。"""
    if not metadata_path or not metadata_path.exists():
        return []
    metadata = load_pokemon_metadata(metadata_path)
    index = build_pokemon_index(records, metadata)
    reps = load_representatives(representatives_path, metadata) if representatives_path else {}
    entries = []
    for slug, (meta, manholes) in index.items():
        name = FORM_PREFIX.get(meta.get("form") or "", "") + str((meta.get("names") or {}).get("ja", ""))
        entries.append(PokemonEntry(name, slug, [str(m.get("id")) for m in manholes], reps.get(slug, "")))
    entries.sort(key=lambda e: (-len(e.manhole_ids), e.slug))
    return entries


def build_popular_pokemon(
    records: list[dict],
    metadata_path: Path | None,
    limit: int = POPULAR_POKEMON_LIMIT,
    representatives_path: Path | None = DEFAULT_REPRESENTATIVES,
) -> list[PokemonEntry]:
    return build_pokemon_entries(records, metadata_path, representatives_path)[:limit]


@dataclass
class TopData:
    records: list[dict]
    photos: list[Photo]
    events: list[dict]
    stats: dict
    today: date
    tag_meta: object = None
    tag_counts: dict = field(default_factory=dict)
    popular_pokemon: list[PokemonEntry] = field(default_factory=list)
    all_pokemon: list[PokemonEntry] = field(default_factory=list)
    trips: list[dict] = field(default_factory=list)
    trip_total: int = 0  # /trip/ に載っているエリアの数
    features: list[dict] = field(default_factory=list)  # 公開中の特集（新しい順）

    @property
    def total(self) -> int:
        return len(self.records)

    @property
    def pref_counts(self) -> Counter:
        return Counter(r["prefecture"] for r in self.records if r.get("prefecture") in PREFECTURE_SLUGS)

    @property
    def pokemon_counts(self) -> Counter:
        return Counter(p for r in self.records for p in pokemons_of(r))

    @property
    def installed_prefectures(self) -> list[str]:
        counts = self.pref_counts
        return [p for p in PREFECTURE_ORDER if counts.get(p)]

    @property
    def empty_prefectures(self) -> list[str]:
        counts = self.pref_counts
        return [p for p in PREFECTURE_ORDER if not counts.get(p)]


def pokemons_of(record: dict) -> list[str]:
    return [p for p in record.get("pokemons") or [] if p and EXCLUDED_POKEMON_PATTERN not in p]


def is_installed(record: dict) -> bool:
    """設置前（installed: false）は数えない。都道府県ページ・写真掲載率と同じ規則。"""
    return record.get("installed") is not False


def place_label(record: dict) -> str:
    """「指宿市」のような自治体名。表示名が「宮崎県/五ヶ瀬町」形式のときは県名を落とす。"""
    name = compose_display_name(record)
    prefecture = str(record.get("prefecture", ""))
    if prefecture and name.startswith(f"{prefecture}/"):
        name = name[len(prefecture) + 1:]
    return name.split(" ")[0] or str(record.get("city", ""))


def _load_json(path: Path | None) -> object:
    if not path or not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None


def build_photos(photos_json: object, records: list[dict], image_dir: Path) -> list[Photo]:
    """ローカルミラーのある投稿写真を新しい順に返す（1地点1枚）。"""
    by_id = {str(r.get("id")): r for r in records}
    raw = (photos_json or {}).get("photos") if isinstance(photos_json, dict) else None
    photos: list[Photo] = []
    for item in (raw or {}).values():
        if not isinstance(item, dict):
            continue
        mid = str(item.get("manhole_id", ""))
        record = by_id.get(mid)
        if not record or not (image_dir / f"{mid}_latest.jpeg").exists():
            continue
        place = place_label(record)
        photos.append(Photo(
            manhole_id=mid,
            created_at=str(item.get("created_at") or ""),
            prefecture=str(record.get("prefecture", "")),
            pokemons=pokemons_of(record),
            place=place,
            has_lid=(image_dir / f"{mid}_lid.jpeg").exists(),
        ))
    photos.sort(key=lambda p: (p.created_at, p.manhole_id), reverse=True)
    return photos


def load_events(path: Path | None, today: date) -> list[dict]:
    """終了していないイベントを、開催中（終了が近い順）→まもなく開催（開始が近い順）で返す。"""
    events = []
    for item in _load_json(path) or []:
        if not isinstance(item, dict) or item.get("prefecture") not in PREFECTURE_SLUGS:
            continue
        try:
            start = date.fromisoformat(str(item["start_date"]))
            end = date.fromisoformat(str(item["end_date"]))
        except (KeyError, ValueError):
            continue
        title = str(item.get("title") or "").strip()
        # 新しいポケふたの発表（kind: news）は県ページ向け。トップの枠はイベント・スタンプラリーだけ
        if not title or end < today or item.get("kind") == "news":
            continue
        events.append({"prefecture": item["prefecture"], "title": title, "start": start, "end": end})
    ongoing = sorted((e for e in events if e["start"] <= today), key=lambda e: (e["end"], e["title"]))
    upcoming = sorted((e for e in events if e["start"] > today), key=lambda e: (e["start"], e["title"]))
    return ongoing + upcoming


def trip_thumbs_html(route: list[dict], image_dir: Path, limit: int = TRIP_THUMB_LIMIT) -> str:
    """蓋の丸い小さい画像を回る順に limit 枚まで。残りは「+n」（画像の無い蓋も n に数える）。"""
    urls = [u for u in (tile_image_url(str(r["id"]), image_dir) for r in route) if u]
    if not urls:
        return ""
    shown = urls[:limit]
    rest = len(route) - len(shown)
    imgs = "".join(
        f'<img src="{escape(u)}" alt="" width="34" height="34" loading="lazy" decoding="async">' for u in shown
    )
    more = f'<span class="stop-thumb-more">+{rest}</span>' if rest > 0 else ""
    return f'<span class="stop-thumbs">{imgs}{more}</span>'


def build_trips(
    records: list[dict], areas_path: Path | None, durations_path: Path | None, image_dir: Path,
    limit: int = TRIP_LIMIT,
) -> tuple[list[dict], int]:
    """(カードに出すエリア, /trip/ のエリア数)。

    カードは、かかる時間の目安があるエリアを枚数が多い順・同数なら時間が長い順に。/trip/ の一覧と同じ数え方。
    """
    if not areas_path or not durations_path:
        return [], 0
    durations = load_durations(durations_path, areas_path)
    by_id = {str(r.get("id", "")): r for r in records}
    trips = []
    total = 0
    for area in load_trip_areas(areas_path):
        rs = area_records(area, by_id)
        if rs is None:
            continue
        total += 1
        entry = find_entry(rs, durations)
        if not entry:
            continue
        trips.append({
            "slug": area["slug"],
            "name": area["name"],
            "prefecture": area["prefecture"],
            "path": trip_path(area).lstrip("/"),
            "count": len(rs),
            "minutes": entry.get("median_minutes") or 0,
            "time": duration_range(entry["p25_minutes"], entry["p75_minutes"]),
            "mode": MODE_LABELS[travel_mode(rs)],
            "thumbs": trip_thumbs_html(area_route(rs, entry)[0], image_dir),
        })
    trips.sort(key=lambda t: (-t["count"], -t["minutes"], t["slug"]))
    return trips[:limit], total


def load_data(
    manholes: Path = DEFAULT_MANHOLES,
    photos: Path | None = DEFAULT_PHOTOS,
    stats: Path | None = DEFAULT_STATS,
    events: Path | None = DEFAULT_EVENTS,
    image_dir: Path = DEFAULT_IMAGE_DIR,
    today: date | None = None,
    pokemon_metadata: Path | None = DEFAULT_POKEMON_METADATA,
    representatives: Path | None = DEFAULT_REPRESENTATIVES,
    trip_areas: Path | None = DEFAULT_TRIP_AREAS,
    durations: Path | None = DEFAULT_DURATIONS,
    features_dir: Path = DEFAULT_FEATURES_DIR,
) -> TopData:
    today = today or datetime.now(JST).date()
    all_records = load_records(manholes)
    records = [r for r in all_records if is_installed(r)]
    stats_json = _load_json(stats)
    pokemon = build_pokemon_entries(records, pokemon_metadata, representatives_path=representatives)
    trips, trip_total = build_trips(all_records, trip_areas, durations, image_dir)
    # 新作の特集は設置前の蓋を載せるので、設置済みに絞る前のレコードで引く
    features = load_features({str(r.get("id", "")): r for r in all_records}, features_dir, today=today)
    return TopData(
        records=records,
        photos=build_photos(_load_json(photos), records, image_dir),
        events=load_events(events, today),
        stats=stats_json if isinstance(stats_json, dict) else {},
        today=today,
        tag_meta=load_tag_meta(),
        tag_counts=count_tags(records),
        popular_pokemon=pokemon[:POPULAR_POKEMON_LIMIT],
        all_pokemon=pokemon,
        trips=trips,
        trip_total=trip_total,
        features=features,
    )


# ── 写真の選び方 ──────────────────────────────────────────────────────────


def select_hero_photos(photos: list[Photo], limit: int = HERO_PHOTO_LIMIT) -> list[Photo]:
    """最新の投稿から、同じ都道府県が続かないように選ぶ。"""
    chosen: list[Photo] = []
    seen: set[str] = set()
    for photo in photos:
        if photo.prefecture in seen:
            continue
        chosen.append(photo)
        seen.add(photo.prefecture)
        if len(chosen) == limit:
            return chosen
    # 都道府県が足りないときは重複を許して埋める
    for photo in photos:
        if len(chosen) == limit:
            break
        if photo not in chosen:
            chosen.append(photo)
    return chosen


def select_gallery_photos(
    photos: list[Photo], exclude: list[Photo], limit: int = GALLERY_PHOTO_LIMIT
) -> list[Photo]:
    """地方ごとに新しい順のキューを作り、北から順に1枚ずつ取る（地域の偏りを抑える）。"""
    used = {p.manhole_id for p in exclude}
    queues: dict[str, list[Photo]] = {name: [] for name, _ in REGIONS}
    for photo in photos:
        region = REGION_OF.get(photo.prefecture)
        if region and photo.manhole_id not in used:
            queues[region].append(photo)
    chosen: list[Photo] = []
    while len(chosen) < limit and any(queues.values()):
        for name, _ in REGIONS:
            if queues[name] and len(chosen) < limit:
                chosen.append(queues[name].pop(0))
    return chosen


# ── 描画 ──────────────────────────────────────────────────────────────────


def _js(value: str) -> str:
    """onclick 内の JS 文字列リテラル用（HTML属性としても安全にする）。"""
    return escape(json.dumps(str(value), ensure_ascii=False)[1:-1].replace("'", "\\'"), quote=True)


def _track(event: str, **params: object) -> str:
    body = ",".join(
        f"{key}:{value}" if isinstance(value, int) else f"{key}:'{_js(str(value))}'"
        for key, value in params.items()
    )
    return f"trackEvent('{event}',{{{body}}})"


def _jst_iso(value: str) -> str:
    """表示（format_photo_date は JST）と datetime 属性の日付を揃える。"""
    day = to_jst_date(value)
    return day.isoformat() if day else ""


def _img(photo: Photo, *, eager: bool = False, priority: bool = False) -> str:
    loading = 'loading="eager"' if eager else 'loading="lazy"'
    fetch = ' fetchpriority="high"' if priority else ""
    return (
        f'<img src="{escape(photo.src)}" alt="{escape(photo.alt)}" '
        f'width="{PHOTO_SIZE}" height="{PHOTO_SIZE}" {loading} decoding="async"{fetch}>'
    )


def description(data: TopData) -> str:
    return (
        f"全国{len(data.installed_prefectures)}都道府県・{data.total}枚のポケふた（ポケモンマンホール）を、"
        "投稿写真・地図・都道府県・ポケモン・テーマから探せる図鑑です。設置場所や周辺のポケふたも確認できます。"
    )


def short_description(data: TopData) -> str:
    return (
        f"全国{len(data.installed_prefectures)}都道府県・{data.total}枚のポケふた（ポケモンマンホール）を"
        "写真と地図から探せます。"
    )


def json_ld(data: TopData) -> dict:
    counts = data.pref_counts
    return {
        "@context": "https://schema.org",
        "@graph": [
            {
                "@type": "WebSite",
                "@id": f"{BASE_URL}#website",
                "url": BASE_URL,
                "name": SITE_NAME,
                "alternateName": "ポケふたデータベース",
                "inLanguage": "ja",
            },
            {
                "@type": "CollectionPage",
                "@id": f"{BASE_URL}#webpage",
                "url": BASE_URL,
                "name": PAGE_TITLE,
                "description": description(data),
                "inLanguage": "ja",
                "isPartOf": {"@id": f"{BASE_URL}#website"},
                "breadcrumb": {"@id": f"{BASE_URL}#breadcrumb"},
                "mainEntity": {"@id": f"{BASE_URL}#prefectures"},
                "hasPart": [
                    {"@type": "WebPage", "name": "ポケふたマップ", "url": f"{BASE_URL}map.html"},
                    {"@type": "CollectionPage", "name": "都道府県別ポケふた一覧", "url": f"{BASE_URL}prefectures/"},
                    {"@type": "CollectionPage", "name": "ポケモン別ポケふた一覧", "url": f"{BASE_URL}pokemon/"},
                    {"@type": "CollectionPage", "name": "キャラクターマンホール", "url": f"{BASE_URL}character_manholes.html"},
                ],
            },
            {
                "@type": "ItemList",
                "@id": f"{BASE_URL}#prefectures",
                "name": "ポケふたが設置されている都道府県",
                "numberOfItems": len(data.installed_prefectures),
                "itemListElement": [
                    {
                        "@type": "ListItem",
                        "position": i,
                        "name": f"{pref}のポケふた（{counts[pref]}枚）",
                        "url": f"{BASE_URL}prefectures/{PREFECTURE_SLUGS[pref]}/",
                    }
                    for i, pref in enumerate(data.installed_prefectures, start=1)
                ],
            },
            {
                "@type": "BreadcrumbList",
                "@id": f"{BASE_URL}#breadcrumb",
                "itemListElement": [
                    {"@type": "ListItem", "position": 1, "name": SITE_NAME, "item": BASE_URL},
                ],
            },
        ],
    }


def render_head(data: TopData, indent: str) -> str:
    desc = escape(description(data), quote=True)
    short = escape(short_description(data), quote=True)
    ld = json.dumps(json_ld(data), ensure_ascii=False, indent=1).replace("<", "\\u003c")
    lines = [
        f'<meta name="description" content="{desc}">',
        f'<meta property="og:description" content="{short}">',
        f'<meta name="twitter:description" content="{short}">',
        '<script type="application/ld+json">',
        ld,
        "</script>",
    ]
    return "\n".join(indent + line if line else line for line in lines)


def map_pins(data: TopData, label=None, title=None) -> list[dict]:
    """ヒーロー地図の都道府県ピン。件数は同じ生成時データから出す（ブラウザで ndjson を読まない）。"""
    counts = data.pref_counts
    label = label or (lambda pref: pref if pref == "北海道" else pref[:-1])
    title = title or (lambda pref, count: f"{pref} {count}枚：地図で見る")
    return [
        {
            "prefecture": pref,
            "label": label(pref),
            "title": title(pref, counts[pref]),
            "count": counts[pref],
            "lat": PREF_COORDS[pref][0],
            "lng": PREF_COORDS[pref][1],
        }
        for pref in data.installed_prefectures
        if pref in PREF_COORDS
    ]


def map_block(data: TopData, *, pins: list[dict], aria: str, cta: str, cta_href: str) -> str:
    """デスクトップの大地図。Leaflet はページ側の JS が幅を判定してから読み込む（スマホでは通信しない）。"""
    payload = json.dumps({"pins": pins}, ensure_ascii=False, separators=(",", ":")).replace("<", "\\u003c")
    return (
        '<div class="home-map" id="home-map-wrap">'
        f'<div class="home-map__canvas" id="home-map" role="region" aria-label="{escape(aria)}"></div>'
        f'<a class="home-map__cta" href="{cta_href}" '
        f'onclick="{_track("click_map_gateway", surface="top_map_hero")}">{escape(cta)}</a>'
        '<span class="home-map__attr">© OpenStreetMap contributors</span>'
        f'<script type="application/json" id="home-map-data">{payload}</script>'
        "</div>"
    )


# デスクトップではモザイクを出さないので、<picture> で写真そのものを取りに行かせない
DESKTOP_BLANK_SOURCE = (
    '<source media="(min-width: 960px)" '
    'srcset="data:image/gif;base64,R0lGODlhAQABAIAAAAAAAP///yH5BAEAAAAALAAAAAABAAEAAAIBRAA7">'
)


def mobile_only(img: str) -> str:
    return f"<picture>{DESKTOP_BLANK_SOURCE}{img}</picture>"


def render_hero(data: TopData) -> str:
    photos = select_hero_photos(data.photos)
    top_pokemon = [e.name for e in data.popular_pokemon[:3]] or [n for n, _ in data.pokemon_counts.most_common(3)]
    posts = data.stats.get("public_posts") if isinstance(data.stats.get("public_posts"), int) else None
    stats = [
        (f"{data.total:,}", "枚のポケふた"),
        (str(len(data.installed_prefectures)), "都道府県に設置"),
        (f"{len(data.pokemon_counts):,}", "種類のポケモン"),
    ]
    if posts:
        stats.append((f"{posts:,}", "枚の投稿写真"))
    stats_html = "".join(
        f'<div class="home-stat"><dt>{escape(label)}</dt><dd>{escape(num)}</dd></div>' for num, label in stats
    )
    # destination は GA4 に登録済みのディメンション（way は未登録で集計に出ない）。
    # 同じページ内へ飛ぶ都道府県は home_pref_section として、ページ移動と区別する
    quick = [
        ("map", "map", "map.html", "地図で探す", "home-quick__link--primary home-quick__link--map"),
        ("prefecture", "home_pref_section", "#home-pref", "都道府県から探す", ""),
        ("pokemon", "pokemon_index", "pokemon/", "ポケモンから探す", ""),
        # PC だけ。上の2つと行き先が重ならない導線（近くから探す＝nearby.html は廃止して地図の現在地検索へ統合）
        ("theme", "map_theme_directory", "map.html?view=theme", "テーマから探す", "home-quick__link--desktop"),
    ]
    if data.trip_total:  # PC は地図ボタンを隠すので、ルートを足して 2×2 を埋める
        quick.append(("trip", "trip_index", "trip/", "ルートから探す", "home-quick__link--desktop"))
    quick_html = "".join(
        f'<a class="home-quick__link {cls}" href="{href}" '
        f'onclick="{_track("click_search_way", surface="top_hero_quick", way=way, destination=dest)}">{escape(label)}</a>'
        for way, dest, href, label, cls in quick
    )
    # 新作特集の告知。スマホの最初の画面に入るよう、ボタンの直下に1行で。
    # highlight_until 中の新作が2県以上あるときは「沖縄・高知・群馬に新しいポケふた」とまとめて特集一覧の新作欄へ
    current = highlighted(data.features, data.today)
    prefs = list(dict.fromkeys(_short_pref(f["prefecture"]) for f in reversed(current) if f.get("prefecture")))
    if len(prefs) >= 2:
        feature_html = (
            '<a class="home-hero-feature" href="features/#new" '
            f'onclick="{_track("click_feature", surface="top_hero", feature="new_list", position=0)}">'
            '<span class="home-feature__kicker">新作</span>'
            f'<b>{escape("・".join(prefs))}に新しいポケふた</b></a>'
        )
    else:
        feature_html = "".join(
            f'<a class="home-hero-feature" href="{escape(feature_path(f).lstrip("/"))}" '
            f'onclick="{_track("click_feature", surface="top_hero", feature=f["slug"], position=0)}">'
            f'<span class="home-feature__kicker">{escape(f.get("kicker") or "特集")}</span>'
            f'<b>{escape(f["title"])}</b></a>'
            for f in current[:1]
        )
    names = "・".join(top_pokemon)
    lead = (
        f"ポケふた（ポケモンマンホール）は、全国{len(data.installed_prefectures)}都道府県に"
        f"{data.total:,}枚設置されています。北海道から沖縄まで、設置場所とポケモン、"
        "みんなが撮った写真をまとめた図鑑です。"
        + (f"<b>{escape(names)}</b>など{len(data.pokemon_counts):,}種類のポケモンから、" if names else "")
        + "旅先や近所の一枚を見つけられます。"
    )
    mosaic = ""
    if photos:
        items = "".join(
            f'<li class="home-mosaic__item"><a href="{p.href}" '
            f'onclick="{_track("click_hero_photo", surface="top_hero_photo", manhole=p.manhole_id, position=i)}">'
            f"{mobile_only(_img(p, eager=True, priority=(i == 0)))}"
            f'<span class="home-mosaic__cap"><b>{escape(p.title)}</b>{escape(p.prefecture)} {escape(p.place)}</span>'
            "</a></li>"
            for i, p in enumerate(photos)
        )
        mosaic = (
            '<figure class="home-mosaic">'
            f'<ul class="home-mosaic__grid">{items}</ul>'
            f'<figcaption class="home-mosaic__note">みんなが投稿した最新の写真（{data.today.month}月{data.today.day}日更新）</figcaption>'
            "</figure>"
        )
    cls = "home-hero" if photos else "home-hero home-hero--no-photos"
    map_html = map_block(
        data,
        pins=map_pins(data),
        aria="都道府県別のポケふた設置数の地図",
        cta="🗺 地図を全画面で開く",
        cta_href="map.html",
    )
    return (
        f'<section class="{cls}" id="home-hero" aria-labelledby="home-h1">'
        '<div class="home-hero__copy">'
        '<p class="home-eyebrow">ポケふた図鑑</p>'
        f'<h1 class="home-h1" id="home-h1">全国{data.total:,}枚のポケふたを、<wbr>地図と一覧から探す</h1>'
        f'<p class="home-lead">{lead}</p>'
        f'<nav class="home-quick" aria-label="主な探し方">{quick_html}</nav>'
        f"{feature_html}"
        f'<dl class="home-stats">{stats_html}</dl>'
        "</div>"
        f"{map_html}"
        f"{mosaic}"
        "</section>"
    )


def _short_pref(name: str) -> str:
    """「群馬県」→「群馬」。北海道はそのまま。"""
    return name[:-1] if name != "北海道" and name[-1:] in ("都", "府", "県") else name


def render_ways(data: TopData) -> str:
    pref_counts = data.pref_counts
    top_prefs = sorted(data.installed_prefectures, key=lambda p: (-pref_counts[p], PREFECTURE_ORDER.index(p)))[:3]
    poke_counts = data.pokemon_counts

    def sub(links: list[tuple[str, str]], way: str) -> str:
        return "".join(
            f'<li><a href="{href}" onclick="{_track("click_search_way", surface="top_search_ways", way=way)}">{label}</a></li>'
            for href, label in links
        )

    cards = [
        ("map", "map.html", "assets/icon-map.svg", "地図・現在地から",
         "日本地図で設置場所を確かめ、今いる場所の近くにあるポケふたを探せます。",
         [("map.html?view=theme", "テーマで絞り込む")]),
        # ヒーローの「都道府県から探す」と同じく、ページ内の都道府県の欄へ飛ばす
        ("prefecture", "#home-pref", "assets/icon-pin.svg", "都道府県から",
         f"設置のある{len(data.installed_prefectures)}都道府県を、地域ごとの一覧で確認できます。",
         [(f"prefectures/{PREFECTURE_SLUGS[p]}/", f"{escape(p)} {pref_counts[p]}枚") for p in top_prefs]),
        ("pokemon", "pokemon/", "assets/pokefuta-marker.svg", "ポケモンから",
         f"{len(poke_counts):,}種類のポケモンから、好きなポケモンのポケふたを探せます。",
         [(e.href, f"{escape(e.name)} {len(e.manhole_ids)}枚") for e in data.popular_pokemon[:3]]),
    ]
    if data.trip_total:
        cards.append(
            ("trip", "trip/", "assets/icon-route.svg", "1日で回るルートから",
             f"{data.trip_total}のエリアを、回る順番とかかる時間の目安つきで紹介しています。",
             [(escape(t["path"]), f'{escape(t["name"])} {t["count"]}枚') for t in data.trips[:3]]),
        )
    else:  # ポケふた旅のデータが無いときはテーマで埋める
        meta = data.tag_meta
        theme_slugs = [s for s in meta.top_chip_slugs(data.tag_counts) if meta.href(s).startswith("/tags/")][:3]
        cards.append(
            ("theme", "map.html?view=theme", "assets/icon-tag.svg", "テーマから",
             "道の駅・世界遺産・離島など、旅の目的に合わせて探せます。",
             [(meta.href(s), f"{escape(meta.label(s))} {data.tag_counts.get(s, 0)}枚") for s in theme_slugs]),
        )
    cards_html = "".join(
        '<li class="home-way">'
        f'<a class="home-way__main" href="{href}" onclick="{_track("click_search_way", surface="top_search_ways", way=way)}">'
        f'<img class="home-way__icon" src="{icon}" alt="" width="28" height="28">'
        f'<span class="home-way__title">{escape(title)}探す</span>'
        f'<span class="home-way__text">{escape(text)}</span>'
        "</a>"
        f'<ul class="home-way__links">{sub(links, way)}</ul>'
        "</li>"
        for way, href, icon, title, text, links in cards
    )
    return (
        '<section class="home-section" id="home-ways" aria-labelledby="home-ways-title">'
        '<h2 class="home-h2" id="home-ways-title">探し方を選ぶ</h2>'
        f'<ul class="home-ways">{cards_html}</ul>'
        "</section>"
    )


def render_newrelease(data: TopData) -> str:
    cutoff = datetime.combine(data.today - timedelta(days=NEW_RELEASE_DAYS), datetime.min.time(), JST)
    fresh = []
    for record in data.records:
        added = str(record.get("added_at") or "")
        try:
            added_at = datetime.fromisoformat(added.replace("Z", "+00:00"))
        except ValueError:
            continue
        if added_at >= cutoff:
            fresh.append((added_at, record))
    if not fresh and not data.features:
        return ""
    fresh.sort(key=lambda item: (item[0], str(item[1].get("id"))), reverse=True)
    cards = []
    for i, (_, record) in enumerate(fresh):
        mid = str(record.get("id"))
        names = "・".join(pokemons_of(record)) or "ポケふた"
        place = f"{record.get('prefecture', '')} {place_label(record)}"
        cards.append(
            f'<li><a class="home-newrel__card" href="manholes/{quote(mid, safe="")}/" '
            f'onclick="{_track("click_newrelease", surface="top_newrelease", manhole=mid, position=i)}">'
            f'<b>{escape(names)}</b><span>{escape(place)}</span></a></li>'
        )
    banners = "".join(
        f'<a class="home-feature" href="{escape(feature_path(f).lstrip("/"))}" '
        f'onclick="{_track("click_feature", surface="top_newrelease", feature=f["slug"], position=i)}">'
        f'<span class="home-feature__kicker">{escape(f.get("kicker") or "特集")}</span>'
        f'<b>{escape(f["title"])}</b></a>'
        for i, f in enumerate(highlighted(data.features, data.today))
    )
    more = (
        f'<a class="home-purpose__more" href="features/" '
        f'onclick="{_track("click_hub_feature_all", surface="top_newrelease")}">'
        f"特集一覧 {len(data.features)}本</a>"
        if data.features else ""
    )
    title = (
        f'新作ポケふた <small>直近{NEW_RELEASE_DAYS}日で{len(fresh)}枚</small>' if fresh else "ポケふた特集"
    )
    # 新作はちょうど特集にしている時期なので、特集の帯をカードより先に出す
    return (
        '<section class="home-section" id="home-newrelease" aria-labelledby="home-newrelease-title">'
        '<div class="home-purpose__head">'
        f'<h2 class="home-h2" id="home-newrelease-title">{title}</h2>{more}</div>'
        f'{banners}'
        + (f'<ul class="home-newrel">{"".join(cards)}</ul>' if cards else "")
        + "</section>"
    )


def render_photos(data: TopData) -> str:
    hero = select_hero_photos(data.photos)
    photos = select_gallery_photos(data.photos, hero)
    upload = (
        f'<a class="home-cta" href="{UPLOAD_URL}" '
        f'onclick="{_track("click_photo_post_cta", surface="top_photo_gallery")}">ポケふた写真館で写真を投稿する</a>'
    )
    if not photos:
        return (
            '<section class="home-section" id="home-photos" aria-labelledby="home-photos-title">'
            '<h2 class="home-h2" id="home-photos-title">新着・注目の写真</h2>'
            f'<p class="home-text">まだ写真がありません。最初の一枚を投稿してみませんか。</p>{upload}'
            "</section>"
        )
    items = "".join(
        f'<li class="home-gallery__item"><a href="{p.href}" '
        f'onclick="{_track("click_top_photo", surface="top_photo_gallery", manhole=p.manhole_id, position=i)}">'
        f"{_img(p)}"
        f'<span class="home-gallery__cap"><b>{escape(p.title)}</b>'
        f'<span>{escape(p.prefecture)} {escape(p.place)}</span>'
        f'<time datetime="{escape(_jst_iso(p.created_at))}">{escape(format_photo_date(p.created_at))}</time></span>'
        "</a></li>"
        for i, p in enumerate(photos)
    )
    total_photos = data.stats.get("manholes_with_photos")
    coverage = (
        f"これまでに{total_photos:,}か所のポケふたに写真が届いています。"
        if isinstance(total_photos, int) and total_photos else ""
    )
    return (
        '<section class="home-section" id="home-photos" aria-labelledby="home-photos-title">'
        '<h2 class="home-h2" id="home-photos-title">新着・注目の写真</h2>'
        f'<p class="home-text">最近の投稿から、地域が偏らないように北から順に選んでいます。{coverage}</p>'
        f'<ul class="home-gallery">{items}</ul>'
        f"{upload}"
        "</section>"
    )


def event_pokemon_photo(event: dict, data: TopData) -> tuple[str, Photo] | None:
    """イベントの顔にするポケモンと写真。

    イベント名に入っている県内のポケモン（「三重県×ミジュマル」ならミジュマル）を探し、
    人が選んだ代表のマンホールがその県にあればそれ、無ければ県内の新しい投稿を使う。
    名前の短いポケモンが長い名前の一部に当たらないよう、長い名前から先に見る。
    """
    pref = event["prefecture"]
    in_pref = {str(r.get("id")) for r in data.records if r.get("prefecture") == pref}
    photos = [p for p in data.photos if p.manhole_id in in_pref]
    for entry in sorted(data.all_pokemon, key=lambda e: -len(e.name)):
        if not entry.name or entry.name not in event["title"]:
            continue
        ids = set(entry.manhole_ids) & in_pref
        candidates = [p for p in photos if p.manhole_id in ids]
        if not candidates:
            continue
        rep = next((p for p in candidates if p.manhole_id == entry.representative_id), None)
        return entry.name, rep or candidates[0]
    return None


def _event_card(event: dict, data: TopData, extra: bool = False) -> str:
    today = data.today
    pref = event["prefecture"]
    ongoing = event["start"] <= today
    status = "開催中" if ongoing else "まもなく開催"
    period = f'{event["start"]:%Y/%m/%d} - {event["end"]:%Y/%m/%d}'
    picked = event_pokemon_photo(event, data)
    media = ""
    if picked:
        name, photo = picked
        src, size = photo.thumb_src
        media = (
            f'<img class="home-event__img" src="{escape(src)}" '
            f'alt="{escape(name)}のポケふた（{escape(photo.prefecture)}{escape(photo.place)}）" '
            f'width="{size}" height="{size}" loading="lazy" decoding="async">'
        )
    return (
        f'<li class="home-event{" has-img" if media else ""}{" is-extra" if extra else ""}" data-end="{event["end"].isoformat()}">'
        f'<a href="prefectures/{PREFECTURE_SLUGS[pref]}/" '
        f'onclick="{_track("click_event_notice", surface="top_event_notice", prefecture=pref, destination="prefecture_page")}">'
        f"{media}"
        f'<span class="home-event__badge{"" if ongoing else " is-upcoming"}">{status}</span>'
        f'<span class="home-event__copy"><b>{escape(event["title"])}</b>'
        f'<small>{escape(pref)} · {period}</small></span>'
        "</a></li>"
    )


def render_events(data: TopData) -> str:
    if not data.events:
        return ""
    # PC は全件を並べる。スマホは先頭3件だけ出し、4件目以降は「すべて見る」で開く（CSS で出し分け）
    cards = "".join(
        _event_card(e, data, extra=i >= EVENT_VISIBLE_LIMIT) for i, e in enumerate(data.events)
    )
    more = ""
    if len(data.events) > EVENT_VISIBLE_LIMIT:
        more = (
            '<button type="button" class="home-events__toggle" '
            # 計測が読み込めなくても開くよう、先に開いてから送る
            "onclick=\"this.parentNode.classList.add('is-open');"
            f'if (window.trackEvent) {_track("click_event_show_all", surface="top_event_notice", count=len(data.events))}">'
            f"すべて見る（全{len(data.events)}件）</button>"
        )
    return (
        '<section class="home-section" id="home-events" aria-labelledby="home-events-title">'
        '<h2 class="home-h2" id="home-events-title">開催中のイベント・スタンプラリー</h2>'
        f'<ul class="home-events">{cards}</ul>'
        f"{more}"
        "</section>"
    )


def render_pref(data: TopData) -> str:
    counts = data.pref_counts
    regions = []
    for name, prefs in REGIONS:
        installed = [p for p in prefs if counts.get(p)]
        if not installed:
            continue
        links = "".join(
            f'<li><a href="prefectures/{PREFECTURE_SLUGS[p]}/" '
            f'onclick="{_track("click_pref_link", surface="top_prefecture_list", prefecture=p)}">'
            f'<span class="home-pref__name">{escape(p)}</span><span class="home-pref__count">{counts[p]}枚</span></a></li>'
            for p in installed
        )
        region_total = sum(counts[p] for p in installed)
        regions.append(
            '<div class="home-region">'
            f'<h3 class="home-region__title">{escape(name)} <small>{region_total}枚</small></h3>'
            f'<ul class="home-pref">{links}</ul>'
            "</div>"
        )
    empty = data.empty_prefectures
    note = ""
    if empty:
        empty_links = "・".join(
            f'<a href="prefectures/{PREFECTURE_SLUGS[p]}/">{escape(p)}</a>' for p in empty
        )
        note = (
            f'<p class="home-pref-note">{empty_links}の{len(empty)}県には、'
            f"{data.today.year}年{data.today.month}月時点でポケふたは設置されていません。"
            "各県のページでは近くの県のポケふたを案内しています。</p>"
        )
    return (
        '<section class="home-section" id="home-pref" aria-labelledby="home-pref-title">'
        '<div class="home-section__head"><h2 class="home-h2" id="home-pref-title">都道府県から探す</h2>'
        f'<a class="home-purpose__more" href="prefectures/" onclick="{_track("click_pref_link", surface="top_prefecture_list", prefecture="all")}">'
        "都道府県一覧 47都道府県</a></div>"
        f'<p class="home-text">ポケふたは47都道府県のうち{len(data.installed_prefectures)}都道府県に'
        f"設置されています。地域ごとに北から並べ、県名の横に設置枚数を載せています。</p>"
        f'<div class="home-regions">{"".join(regions)}</div>'
        f"{note}"
        "</section>"
    )


def pick_pokemon_photo(entry: PokemonEntry, photos: list[Photo], used: set[str]) -> Photo | None:
    """ポケモンのカードに出す1枚。人が選んだ代表があればそれ、無ければ新しい順。

    photos は今公開されている投稿（latest-manhole-photos.json）のうち画像がある分だけなので、
    代表の写真が非公開・削除になったら自動で新しい順に戻る。
    同じマンホールに複数のポケモンがいても、カードごとに別の写真を使う（代表は人が選んだので優先）。
    """
    ids = set(entry.manhole_ids)
    candidates = [p for p in photos if p.manhole_id in ids]
    rep = next((p for p in candidates if p.manhole_id == entry.representative_id), None)
    photo = rep or next((p for p in candidates if p.manhole_id not in used), candidates[0] if candidates else None)
    if photo:
        used.add(photo.manhole_id)
    return photo


def render_pokemon(data: TopData) -> str:
    counts = data.pokemon_counts
    cards = []
    used: set[str] = set()
    for entry in data.popular_pokemon:
        photo = pick_pokemon_photo(entry, data.photos, used)
        src, size = photo.thumb_src if photo else ("", 0)
        media = (
            f'<img src="{escape(src)}" alt="{escape(entry.name)}のポケふた（{escape(photo.prefecture)}{escape(photo.place)}）" '
            f'width="{size}" height="{size}" loading="lazy" decoding="async">'
            if photo else '<span class="home-poke__placeholder" aria-hidden="true"></span>'
        )
        cards.append(
            f'<li class="home-poke"><a href="{entry.href}" '
            f'onclick="{_track("click_hub_pokemon", surface="top_hub_pokemon", pokemon=entry.name)}">'
            f'{media}<span class="home-poke__name">{escape(entry.name)}</span>'
            f'<span class="home-poke__count">{len(entry.manhole_ids)}枚</span></a></li>'
        )
    cards.append(
        '<li class="home-poke home-poke--all"><a href="pokemon/" '
        f'onclick="{_track("click_hub_pokemon_all", surface="top_hub_pokemon")}">'
        f'<span class="home-poke__name">すべてのポケモン</span><span class="home-poke__count">{len(counts):,}種類</span></a></li>'
    )
    return f'<ul class="home-pokes">{"".join(cards)}</ul>'


def render_trips(data: TopData) -> str:
    """ポケふた旅のカード（/trip/ のヒーローと同じ中身：県・エリアと枚数・蓋の丸い画像・かかる時間）。"""
    if not data.trips:
        return ""
    cards = "".join(
        f'<a class="home-trip" href="{escape(t["path"])}" '
        f'onclick="{_track("click_hub_trip", surface="top_hub_trip", destination=t["slug"])}">'
        f'<span class="home-trip__pref">{escape(t["prefecture"])}</span>'
        f'<b class="home-trip__name">{escape(t["name"])} {t["count"]}枚</b>'
        f'{t["thumbs"]}'
        f'<strong class="home-trip__time">{escape(t["time"])}</strong>'
        f'<small class="home-trip__mode">移動の目安：{escape(t["mode"])}</small></a>'
        for t in data.trips
    )
    return f'<div class="home-trips">{cards}</div>'


def render_tripsmore(data: TopData) -> str:
    if not data.trip_total:
        return ""
    return (
        f'<a class="home-purpose__more" href="trip/" '
        f'onclick="{_track("click_hub_trip_all", surface="top_hub_trip")}">'
        f"1日で回るルート一覧 {data.trip_total}ルート</a>"
    )


def render_themesmore(data: TopData) -> str:
    """地図のテーマ一覧（/tags/ の一覧ページは無い）。数は地図のテーマ一覧と同じ規則で数える。"""
    total = len(data.tag_meta.visible_slugs(data.tag_counts)) if data.tag_meta else 0
    if not total:
        return ""
    return (
        f'<a class="home-purpose__more" href="map.html?view=theme" '
        f'onclick="{_track("click_hub_tag_all", surface="top_hub_tag")}">'
        f"テーマ一覧 {total}テーマ</a>"
    )


RENDERERS = {
    "hero": render_hero,
    "ways": render_ways,
    "newrelease": render_newrelease,
    "photos": render_photos,
    "events": render_events,
    "pref": render_pref,
    "pokemon": render_pokemon,
    "trips": render_trips,
    "tripsmore": render_tripsmore,
    "themesmore": render_themesmore,
}


def apply_blocks(html: str, data: TopData) -> str:
    """マーカー間を描画し直す。未知のブロック名はそのまま残す。"""

    def replace(match: re.Match) -> str:
        name, indent = match.group("name"), match.group("indent")
        if name == "head":
            body = render_head(data, indent)
        elif name in RENDERERS:
            content = RENDERERS[name](data)
            body = f"{indent}{content}" if content else ""
        else:
            return match.group(0)
        start, end = f"<!-- home:{name}:start -->", f"<!-- home:{name}:end -->"
        return f"{indent}{start}\n{body}\n{indent}{end}" if body else f"{indent}{start}\n{indent}{end}"

    return MARKER_RE.sub(replace, html)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("target", type=Path, nargs="?", default=DEFAULT_TARGET)
    parser.add_argument("--manholes", type=Path, default=DEFAULT_MANHOLES)
    parser.add_argument("--photos", type=Path, default=DEFAULT_PHOTOS)
    parser.add_argument("--stats", type=Path, default=DEFAULT_STATS)
    parser.add_argument("--events", type=Path, default=DEFAULT_EVENTS)
    parser.add_argument("--image-dir", type=Path, default=DEFAULT_IMAGE_DIR)
    parser.add_argument("--pokemon-metadata", type=Path, default=DEFAULT_POKEMON_METADATA)
    args = parser.parse_args(argv)

    data = load_data(
        args.manholes, args.photos, args.stats, args.events, args.image_dir,
        pokemon_metadata=args.pokemon_metadata,
    )
    html = args.target.read_text(encoding="utf-8")
    updated = apply_blocks(html, data)
    missing = [name for name in ["head", *RENDERERS] if f"<!-- home:{name}:start -->" not in html]
    if missing:
        print(f"[top-page] markers missing in {args.target}: {', '.join(missing)}", file=sys.stderr)
        return 1
    args.target.write_text(updated, encoding="utf-8")
    print(
        f"[top-page] wrote {args.target}: {data.total} manholes, "
        f"{len(data.installed_prefectures)} prefectures, {len(data.photos)} photos, {len(data.events)} events"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
