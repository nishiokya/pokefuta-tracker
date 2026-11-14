#!/usr/bin/env python3
"""Generate the public sitemap for the Pokefuta map."""

from __future__ import annotations

import argparse
import json
import logging
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import quote
from xml.sax.saxutils import escape

try:
    from apps.scraper.character_manhole_works import WorkPage, available_pages, gundam_work_records
    from apps.scraper.generate_character_manhole_page import _is_active, load_ndjson
    from apps.scraper.prefectures import MANHOLE_PAGE_LANGS, PREFECTURE_ORDER, PREFECTURE_PAGE_LANGS, PREFECTURE_SLUGS
except ModuleNotFoundError as exc:
    if exc.name != "apps":
        raise
    from character_manhole_works import WorkPage, available_pages, gundam_work_records
    from generate_character_manhole_page import _is_active, load_ndjson
    from prefectures import MANHOLE_PAGE_LANGS, PREFECTURE_ORDER, PREFECTURE_PAGE_LANGS, PREFECTURE_SLUGS

try:
    from apps.scraper.generate_tag_pages import available_tag_slugs, load_records
    from apps.scraper.municipalities import page_paths as municipality_page_paths
    from apps.scraper.generate_trip_pages import page_paths as trip_page_paths
    from apps.scraper.visit_durations import load_trip_areas
    from apps.scraper.features import FEATURES_BASE, feature_path, load_features
except ModuleNotFoundError as exc:
    if exc.name != "apps":
        raise
    from generate_tag_pages import available_tag_slugs, load_records
    from municipalities import page_paths as municipality_page_paths
    from generate_trip_pages import page_paths as trip_page_paths
    from visit_durations import load_trip_areas
    from features import FEATURES_BASE, feature_path, load_features

# logger は以前 import されないまま warning 呼び出しだけがあり、
# pokemon_metadata.json が無いときに NameError で落ちる状態だった。
logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger(__name__)

BASE_URL = "https://data.pokefuta.com/"
I18N_LANGS = ["en", "zh-TW", "zh-CN", "ko"]
JST = timezone(timedelta(hours=9))

PREFECTURES = PREFECTURE_ORDER


def read_all_manhole_ids(path: Path) -> list[str]:
    """Read all manhole IDs from the dataset."""
    ids = []
    if not path.exists():
        return ids

    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            record = json.loads(line)
        except json.JSONDecodeError:
            continue
        manhole_id = str(record.get("id") or "").strip()
        if manhole_id:
            ids.append(manhole_id)

    return sorted(set(ids), key=lambda value: (len(value), value))


_FORM_PREFIX: dict[str, str] = {
    "alola": "アローラ",
    "galar": "ガラル",
    "hisui": "ヒスイ",
    "paldea": "パルデア",
}


def _filter_pokemons(pokemons: list) -> list[str]:
    if not isinstance(pokemons, list):
        return []
    return [
        p for p in pokemons
        if isinstance(p, str) and p.strip() and "ローカルActs" not in p
    ]


def _normalize_katakana(text: str) -> str:
    return "".join(
        chr(ord(c) + 0x60) if "ぁ" <= c <= "ゖ" else c
        for c in text
    )


def read_pokemon_slugs(ndjson_path: Path, metadata_path: Path) -> list[str]:
    """Return sorted slug list for Pokemon that appear on at least one pokefuta."""
    if not metadata_path.exists():
        logger.warning(f"Pokemon metadata not found: {metadata_path} — skipping Pokemon URLs")
        return []

    try:
        meta_list = json.loads(metadata_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as exc:
        logger.warning(f"Failed to read Pokemon metadata ({exc}) — skipping Pokemon URLs")
        return []

    ja_to_slug = build_ja_to_slug(meta_list)

    # Collect slugs from active manholes
    found_slugs: set[str] = set()
    if ndjson_path.exists():
        for line in ndjson_path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            try:
                record = json.loads(line)
            except json.JSONDecodeError:
                continue
            if record.get("status") != "active":
                continue
            for ja_name in _filter_pokemons(record.get("pokemons", [])):
                slug = ja_to_slug.get(ja_name) or ja_to_slug.get(
                    _normalize_katakana(ja_name)
                )
                if slug:
                    found_slugs.add(slug)

    return sorted(found_slugs)


def read_pokemon_meta(metadata_path: Path) -> list:
    if not metadata_path.exists():
        return []
    try:
        meta_list = json.loads(metadata_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return []
    return meta_list if isinstance(meta_list, list) else []


def build_ja_to_slug(meta_list: list) -> dict[str, str]:
    """ポケモンの日本語名（地方の姿の接頭辞つき・ひらがな混じりも）→ slug。read_pokemon_slugs と lastmod の両方で使う。"""
    # Build ja_name → slug (base form preferred over regional variants)
    ja_to_slug: dict[str, str] = {}
    for pokemon in meta_list:
        if not isinstance(pokemon, dict):
            continue
        ja_name = pokemon.get("names", {}).get("ja", "")
        slug = pokemon.get("slug", "")
        form = pokemon.get("form") or ""
        if not ja_name or not slug:
            continue
        # Prefer base form (form == None) for direct ja_name key
        if ja_name not in ja_to_slug or not form:
            ja_to_slug[ja_name] = slug
        # Regional prefix variant (e.g. "アローラロコン" → slug)
        prefix = _FORM_PREFIX.get(form, "")
        if prefix:
            combined = prefix + ja_name
            if combined not in ja_to_slug:
                ja_to_slug[combined] = slug

    # Katakana normalization for hiragana-mixed names
    for key in list(ja_to_slug.keys()):
        normalized = _normalize_katakana(key)
        if normalized != key and normalized not in ja_to_slug:
            ja_to_slug[normalized] = ja_to_slug[key]
    return ja_to_slug


def url_entry(loc: str, changefreq: str, priority: str, lastmod: str = "") -> str:
    lines = ["  <url>", f"    <loc>{escape(loc)}</loc>"]
    if lastmod:
        lines.append(f"    <lastmod>{lastmod}</lastmod>")
    lines += [
        f"    <changefreq>{changefreq}</changefreq>",
        f"    <priority>{priority}</priority>",
        "  </url>",
    ]
    return "\n".join(lines)


def _latest_date(stamps: list[str]) -> str:
    """ISO 8601 の時刻の中で最も新しいものを JST の日付（YYYY-MM-DD）で返す。読めない値は飛ばす。"""
    latest = None
    for stamp in stamps:
        text = str(stamp or "").strip()
        if not text:
            continue
        try:
            moment = datetime.fromisoformat(text.replace("Z", "+00:00"))
        except ValueError:
            continue
        if moment.tzinfo is None:
            moment = moment.replace(tzinfo=JST)
        if latest is None or moment > latest:
            latest = moment
    return latest.astimezone(JST).date().isoformat() if latest else ""


def manhole_lastmod(record: dict, photo: dict | None) -> str:
    """蓋のページの中身が最後に変わった日。蓋が図鑑に加わった日（added_at / first_seen）と、
    代表写真（ヒーロー・og:image に出る1枚）が投稿された日のうち新しい方。

    県ページの構造化データの dateModified（generate_prefecture_pages._date_modified、#719）と同じ材料にして、
    2つの信号が食い違わないようにする。使わないもの:
    - last_updated: 取り込みのたびに一括で進む
    - ギャラリー（みんなの写真）の投稿日: 2026-11 時点で 2 週間に 489 枚中 474 枚の蓋に新しい写真が
      入っていて、これを数えると全ページが「今月更新」になり lastmod が何も伝えなくなる
    """
    stamps = [record.get("added_at") or record.get("first_seen") or ""]
    if photo:
        stamps.append(photo.get("created_at") or "")
    return _latest_date(stamps)


def build_lastmods(
    records: list[dict],
    photos: dict[str, dict] | None,
    ja_to_slug: dict[str, str] | None = None,
) -> dict:
    """sitemap に書く lastmod をページ種別ごとにまとめる。

    返り値: {"all": 日付, "manhole": {id: 日付}, "prefecture": {slug: 日付}, "pokemon": {slug: 日付}}。
    日付が決まらないページは入れない（lastmod を書かない）。
    """
    photos = photos or {}
    ja_to_slug = ja_to_slug or {}
    per_manhole: dict[str, str] = {}
    per_prefecture: dict[str, list[str]] = {}
    per_pokemon: dict[str, list[str]] = {}
    for record in records:
        manhole_id = str(record.get("id") or "").strip()
        if not manhole_id:
            continue
        date = manhole_lastmod(record, photos.get(manhole_id))
        if not date:
            continue
        per_manhole[manhole_id] = date
        slug = PREFECTURE_SLUGS.get(str(record.get("prefecture") or ""))
        if slug:
            per_prefecture.setdefault(slug, []).append(date)
        for ja_name in _filter_pokemons(record.get("pokemons", [])):
            pokemon_slug = ja_to_slug.get(ja_name) or ja_to_slug.get(_normalize_katakana(ja_name))
            if pokemon_slug:
                per_pokemon.setdefault(pokemon_slug, []).append(date)
    return {
        "all": max(per_manhole.values(), default=""),
        "manhole": per_manhole,
        "prefecture": {slug: max(dates) for slug, dates in per_prefecture.items()},
        "pokemon": {slug: max(dates) for slug, dates in per_pokemon.items()},
    }


def load_photos(path: Path) -> dict[str, dict]:
    """latest-manhole-photos.json（import-manhole-photos.yml の出力）を蓋ID→写真の dict で返す。無ければ空。"""
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as exc:
        logger.warning(f"Failed to read photos ({exc}) — sitemap lastmod は蓋の追加日だけで作る")
        return {}
    photos = data.get("photos") if isinstance(data, dict) else None
    if isinstance(photos, dict):
        return {str(k): v for k, v in photos.items() if isinstance(v, dict)}
    if isinstance(photos, list):
        return {str(p.get("manhole_id")): p for p in photos if isinstance(p, dict) and p.get("manhole_id") is not None}
    return {}


def read_tag_slugs(ndjson_path: Path) -> list[str]:
    """Return theme tag slugs that have at least one active manhole."""
    if not ndjson_path.exists():
        return []
    return available_tag_slugs(load_records(ndjson_path))


def read_character_work_pages(ndjson_path: Path, gundam_path: Path | None = None) -> list[WorkPage]:
    """Return only work guides that the page generator can actually publish."""
    records = load_ndjson(ndjson_path)
    if gundam_path is not None:
        records += gundam_work_records(load_ndjson(gundam_path))
    active = [record for record in records if _is_active(record)]
    return available_pages(active)


def build_sitemap(
    manhole_ids: list[str],
    pokemon_slugs: list[str] | None = None,
    tag_slugs: list[str] | None = None,
    character_work_pages: list[WorkPage] | None = None,
    municipality_paths: list[str] | None = None,
    trip_paths: list[str] | None = None,
    feature_paths: list[str] | None = None,
    lastmods: dict | None = None,
) -> str:
    """lastmods は build_lastmods() の返り値。データ（蓋の追加・写真の投稿）から決まるページだけ
    <lastmod> を書き、日付の根拠が無いページ（旅・特集・タグなど）には書かない。"""
    lastmods = lastmods or {}
    all_date = str(lastmods.get("all") or "")
    manhole_dates: dict[str, str] = lastmods.get("manhole") or {}
    prefecture_dates: dict[str, str] = lastmods.get("prefecture") or {}
    pokemon_dates: dict[str, str] = lastmods.get("pokemon") or {}
    entries = [
        url_entry(BASE_URL, "daily", "1.0", all_date),
        # map.html は自分自身を canonical にしているので、sitemap にも載せる
        url_entry(f"{BASE_URL}map.html", "daily", "0.9", all_date),
        url_entry(f"{BASE_URL}summary/", "weekly", "0.9", all_date),
        url_entry(f"{BASE_URL}prefectures/", "weekly", "0.9", all_date),
        url_entry(f"{BASE_URL}pokemon/", "weekly", "0.9", all_date),
        url_entry(f"{BASE_URL}character_manholes.html", "weekly", "0.8"),
        url_entry(f"{BASE_URL}gmanhole_map.html", "weekly", "0.7"),
        url_entry(f"{BASE_URL}design_manhole.html", "weekly", "0.6"),
        url_entry(f"{BASE_URL}privacy.html", "monthly", "0.3"),
    ]

    # /characters/ は noindex のUIハブなので sitemap には載せない（作品ページだけ載せる）
    for page in character_work_pages or []:
        entries.append(url_entry(f"{BASE_URL}{page.path}", "weekly", "0.8"))

    for lang in I18N_LANGS:
        entries.append(url_entry(f"{BASE_URL}{lang}/", "weekly", "0.9", all_date))
        entries.append(url_entry(f"{BASE_URL}{lang}/map.html", "weekly", "0.8", all_date))

    for prefecture in PREFECTURES:
        slug = PREFECTURE_SLUGS[prefecture]
        entries.append(
            url_entry(
                f"{BASE_URL}prefectures/{slug}/",
                "weekly",
                "0.8",
                prefecture_dates.get(slug, ""),
            )
        )

    # 訳した県ページ（/<lang>/prefectures/）。日本語版と同じ扱い
    for lang in PREFECTURE_PAGE_LANGS:
        entries.append(url_entry(f"{BASE_URL}{lang}/prefectures/", "weekly", "0.8", all_date))
        for prefecture in PREFECTURES:
            slug = PREFECTURE_SLUGS[prefecture]
            entries.append(
                url_entry(f"{BASE_URL}{lang}/prefectures/{slug}/", "weekly", "0.8", prefecture_dates.get(slug, ""))
            )

    # 市区町村ページ（/municipalities/）。県ページと同列。県の一部を占める自治体だけにある
    if municipality_paths:
        entries.append(url_entry(f"{BASE_URL}municipalities/", "weekly", "0.8"))
        for path in municipality_paths:
            entries.append(url_entry(f"{BASE_URL}{path.lstrip('/')}", "weekly", "0.8"))

    # ポケふた旅（/trip/）の特集ページとエリア別ページ
    for path in trip_paths or []:
        entries.append(url_entry(f"{BASE_URL}{path.lstrip('/')}", "weekly", "0.8"))

    # 特集（/features/）の一覧と各特集。特集が1本も無いときは一覧も載せない
    if feature_paths:
        entries.append(url_entry(f"{BASE_URL}{FEATURES_BASE.lstrip('/')}", "weekly", "0.8"))
        for path in feature_paths:
            entries.append(url_entry(f"{BASE_URL}{path.lstrip('/')}", "weekly", "0.8"))

    # Theme (tag) landing pages. 県ページ(0.8)より下、ポケモンLP(0.1)より上。
    # 数が少なく内容が厚いので、量産している面と同列には置かない。
    for tag_slug in tag_slugs or []:
        entries.append(url_entry(f"{BASE_URL}tags/{quote(tag_slug)}/", "weekly", "0.7"))

    # Static manhole detail pages (primary SEO target)
    for manhole_id in manhole_ids:
        entries.append(
            url_entry(f"{BASE_URL}manholes/{quote(manhole_id)}/", "weekly", "0.8", manhole_dates.get(manhole_id, ""))
        )

    # 訳した詳細ページ（/<lang>/manholes/<id>/）。日本語版と同じ扱い
    for lang in MANHOLE_PAGE_LANGS:
        for manhole_id in manhole_ids:
            entries.append(
                url_entry(
                    f"{BASE_URL}{lang}/manholes/{quote(manhole_id)}/", "weekly", "0.8",
                    manhole_dates.get(manhole_id, ""),
                )
            )

    # Pokemon LP pages (Japanese root)
    for slug in pokemon_slugs or []:
        entries.append(
            url_entry(f"{BASE_URL}pokemon/{quote(slug)}/", "weekly", "0.1", pokemon_dates.get(slug, ""))
        )

    # Pokemon LP pages (multilingual)
    for lang in I18N_LANGS:
        entries.append(url_entry(f"{BASE_URL}{lang}/pokemon/", "weekly", "0.9", all_date))
        for slug in pokemon_slugs or []:
            entries.append(
                url_entry(f"{BASE_URL}{lang}/pokemon/{quote(slug)}/", "weekly", "0.1", pokemon_dates.get(slug, ""))
            )

    return "\n".join(
        [
            '<?xml version="1.0" encoding="UTF-8"?>',
            '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">',
            *entries,
            "</urlset>",
            "",
        ]
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data", default="docs/pokefuta.ndjson")
    parser.add_argument("--pokemon", default="docs/pokemon_metadata.json")
    parser.add_argument("--characters", default="docs/character_manholes.ndjson")
    parser.add_argument("--gundam", default="docs/gmanhole.ndjson")
    parser.add_argument("--photos", default="docs/latest-manhole-photos.json",
                        help="latest-manhole-photos.json。lastmod（写真が増えた日）に使う。無ければ蓋の追加日だけ")
    parser.add_argument("--output", default="apps/web/sitemap.xml")
    args = parser.parse_args()

    manhole_ids = read_all_manhole_ids(Path(args.data))
    if not manhole_ids:
        print("No manhole IDs found in dataset")
        return 1

    pokemon_slugs = read_pokemon_slugs(Path(args.data), Path(args.pokemon))
    tag_slugs = read_tag_slugs(Path(args.data))
    character_work_pages = read_character_work_pages(Path(args.characters), Path(args.gundam))
    municipality_paths = sorted(municipality_page_paths(load_records(Path(args.data))).values())
    trip_paths = trip_page_paths(load_records(Path(args.data)), load_trip_areas())
    records = load_records(Path(args.data))
    records_by_id = {str(r.get("id", "")): r for r in records}
    feature_paths = [feature_path(f) for f in load_features(records_by_id)]
    lastmods = build_lastmods(records, load_photos(Path(args.photos)), build_ja_to_slug(read_pokemon_meta(Path(args.pokemon))))

    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        build_sitemap(
            manhole_ids, pokemon_slugs, tag_slugs, character_work_pages, municipality_paths,
            trip_paths, feature_paths, lastmods,
        ),
        encoding="utf-8",
    )
    print(
        f"[generate_sitemap] lastmod: top {lastmods['all'] or '-'}, "
        f"{len(lastmods['manhole'])} manholes, {len(lastmods['prefecture'])} prefectures, {len(lastmods['pokemon'])} pokemon"
    )
    print(
        f"[generate_sitemap] wrote {output_path} with "
        f"{len(manhole_ids)} manhole URLs + {len(pokemon_slugs)} pokemon URLs "
        f"+ {len(tag_slugs)} tag URLs + {len(character_work_pages)} character work URLs "
        f"+ {len(municipality_paths)} municipality URLs + {len(trip_paths)} trip URLs "
        f"+ {len(feature_paths)} feature URLs"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
