#!/usr/bin/env python3
"""Generate SNS post candidates for pokefuta tracker.

Outputs docs/social-post-candidates.json with raw_data for each candidate.
Body text generation is delegated to Claude (via the /social-post skill).
"""

from __future__ import annotations

import json
import math
from collections import Counter
from pathlib import Path
from urllib.parse import quote

ROOT = Path(__file__).resolve().parents[2]
NDJSON = ROOT / "docs" / "pokefuta.ndjson"
PHOTOS_JSON = ROOT / "docs" / "latest-manhole-photos.json"
POKEMON_METADATA_JSON = ROOT / "docs" / "pokemon_metadata.json"
CANDIDATES_JSON = ROOT / "docs" / "social-post-candidates.json"
MICHINEKI_JSON = ROOT / "dataset" / "michineki.json"

MICHINEKI_RADIUS_KM = 10
MICHINEKI_MIN_COUNT = 3

ISLAND_CITY_MAP: list[dict] = [
    {"island_name": "小笠原諸島", "pref": "東京都",  "city": "小笠原"},
    {"island_name": "小豆島",     "pref": "香川県",  "city": "小豆島"},
    {"island_name": "直島",       "pref": "香川県",  "city": "直島"},
    {"island_name": "隠岐諸島",   "pref": "島根県",  "city": "隠岐の島"},
    {"island_name": "宮古島",     "pref": "沖縄県",  "city": "宮古島"},
    {"island_name": "久米島",     "pref": "沖縄県",  "city": "久米島"},
    {"island_name": "五島列島",   "pref": "長崎県",  "city": "新上五島"},
]

BASE_URL = "https://data.pokefuta.com/"

PREFECTURE_ORDER: list[str] = [
    "北海道", "青森県", "岩手県", "宮城県", "秋田県",
    "山形県", "福島県", "茨城県", "栃木県", "群馬県",
    "埼玉県", "千葉県", "東京都", "神奈川県", "新潟県",
    "富山県", "石川県", "福井県", "山梨県", "長野県",
    "岐阜県", "静岡県", "愛知県", "三重県", "滋賀県",
    "京都府", "大阪府", "兵庫県", "奈良県", "和歌山県",
    "鳥取県", "島根県", "岡山県", "広島県", "山口県",
    "徳島県", "香川県", "愛媛県", "高知県", "福岡県",
    "佐賀県", "長崎県", "熊本県", "大分県", "宮崎県",
    "鹿児島県", "沖縄県",
]

REGION_MAP: dict[str, str] = {
    "北海道": "北海道",
    "青森県": "東北", "岩手県": "東北", "宮城県": "東北",
    "秋田県": "東北", "山形県": "東北", "福島県": "東北",
    "茨城県": "関東", "栃木県": "関東", "群馬県": "関東",
    "埼玉県": "関東", "千葉県": "関東", "東京都": "関東", "神奈川県": "関東",
    "新潟県": "中部", "富山県": "中部", "石川県": "中部", "福井県": "中部",
    "山梨県": "中部", "長野県": "中部", "岐阜県": "中部",
    "静岡県": "中部", "愛知県": "中部",
    "三重県": "近畿", "滋賀県": "近畿", "京都府": "近畿",
    "大阪府": "近畿", "兵庫県": "近畿", "奈良県": "近畿", "和歌山県": "近畿",
    "鳥取県": "中国", "島根県": "中国", "岡山県": "中国",
    "広島県": "中国", "山口県": "中国",
    "徳島県": "四国", "香川県": "四国", "愛媛県": "四国", "高知県": "四国",
    "福岡県": "九州", "佐賀県": "九州", "長崎県": "九州",
    "熊本県": "九州", "大分県": "九州", "宮崎県": "九州",
    "鹿児島県": "九州", "沖縄県": "九州",
}

_FORM_PREFIX: dict[str, str] = {
    "alola": "アローラ",
    "galar": "ガラル",
    "hisui": "ヒスイ",
    "paldea": "パルデア",
}


def _normalize_katakana(text: str) -> str:
    return "".join(chr(ord(c) + 0x60) if "ぁ" <= c <= "ゖ" else c for c in text)


def _filter_pokemons(pokemons: object) -> list[str]:
    if not isinstance(pokemons, list):
        return []
    return [p for p in pokemons if isinstance(p, str) and p.strip() and "ローカルActs" not in p]


def _pref_slug(pref: str) -> str:
    idx = PREFECTURE_ORDER.index(pref) + 1 if pref in PREFECTURE_ORDER else 0
    return f"pref{idx:02d}"


def _haversine(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    R = 6371.0
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = (math.sin(dlat / 2) ** 2
         + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlon / 2) ** 2)
    return R * 2 * math.asin(math.sqrt(a))


def load_michineki(path: Path) -> list[dict]:
    if not path.exists():
        return []
    try:
        return json.loads(path.read_text(encoding="utf-8")).get("@graph", [])
    except (json.JSONDecodeError, OSError):
        return []


def load_records(path: Path) -> list[dict]:
    by_id: dict[str, dict] = {}
    with path.open(encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                record = json.loads(line)
            except json.JSONDecodeError:
                continue
            record_id = str(record.get("id", "")).strip()
            if not record_id:
                continue
            by_id[record_id] = {**by_id.get(record_id, {}), **record}
    return list(by_id.values())


def load_pokemon_metadata(path: Path) -> dict[str, dict]:
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}
    result: dict[str, dict] = {}
    for entry in data:
        if not isinstance(entry, dict):
            continue
        ja_name = entry.get("names", {}).get("ja", "")
        slug = entry.get("slug", "")
        form = entry.get("form") or ""
        if not ja_name or not slug:
            continue
        if ja_name not in result or not form:
            result[ja_name] = entry
        prefix = _FORM_PREFIX.get(form, "")
        if prefix:
            combined = prefix + ja_name
            if combined not in result:
                result[combined] = entry
    for key in list(result.keys()):
        normalized = _normalize_katakana(key)
        if normalized != key and normalized not in result:
            result[normalized] = result[key]
    return result


def load_photos(path: Path) -> dict:
    if not path.exists():
        return {"photos": {}}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {"photos": {}}


def build_stats(records: list[dict]) -> dict:
    counts: dict[str, int] = {pref: 0 for pref in PREFECTURE_ORDER}
    for record in records:
        pref = record.get("prefecture", "")
        if pref in counts:
            counts[pref] += 1

    by_pref = [{"pref": p, "count": counts[p]} for p in PREFECTURE_ORDER]
    total = sum(item["count"] for item in by_pref)
    installed = [item for item in by_pref if item["count"] > 0]
    empty = [item for item in by_pref if item["count"] == 0]
    ranking = sorted(
        installed,
        key=lambda x: (-x["count"], PREFECTURE_ORDER.index(x["pref"])),
    )[:10]

    regional: dict[str, int] = {}
    for pref, count in counts.items():
        region = REGION_MAP.get(pref, "その他")
        regional[region] = regional.get(region, 0) + count

    return {
        "total": total,
        "by_pref": by_pref,
        "ranking": ranking,
        "empty": empty,
        "installed": installed,
        "regional": regional,
    }


def build_pokemon_stats(records: list[dict], pokemon_metadata: dict) -> dict:
    manhole_counts: dict[str, int] = {}
    city_sets: dict[str, set] = {}

    for record in records:
        if record.get("status") != "active":
            continue
        pref = record.get("prefecture", "")
        city = record.get("city", "")
        city_key = f"{pref}/{city}"
        for poke_ja in _filter_pokemons(record.get("pokemons", [])):
            meta = pokemon_metadata.get(poke_ja) or pokemon_metadata.get(_normalize_katakana(poke_ja))
            if not meta:
                continue
            manhole_counts[poke_ja] = manhole_counts.get(poke_ja, 0) + 1
            city_sets.setdefault(poke_ja, set()).add(city_key)

    entries = []
    for ja_name, count in manhole_counts.items():
        meta = pokemon_metadata.get(ja_name) or pokemon_metadata.get(_normalize_katakana(ja_name))
        if not meta:
            continue
        slug = meta.get("slug", "")
        if not slug:
            continue
        entries.append({
            "ja_name": ja_name,
            "slug": slug,
            "count": count,
            "city_count": len(city_sets.get(ja_name, set())),
        })

    by_count = sorted(entries, key=lambda x: (-x["count"], x["ja_name"]))
    by_city_count = sorted(entries, key=lambda x: (-x["city_count"], x["ja_name"]))
    return {"by_count": by_count, "by_city_count": by_city_count}


def gen_prefecture_rank_candidates(stats: dict) -> list[dict]:
    total = stats["total"]
    candidates = []
    for i, item in enumerate(stats["ranking"], start=1):
        pref = item["pref"]
        count = item["count"]
        percent = round(count / total * 100, 1) if total else 0
        candidates.append({
            "id": f"{_pref_slug(pref)}-rank{i:02d}",
            "type": "prefecture_rank",
            "title": f"{pref}のポケふた（{count}枚・全国{i}位）",
            "url": f"{BASE_URL}summary/",
            "hashtags": ["#ポケふた", "#ポケモンマンホール"],
            "imageType": "summary_prefecture_rank",
            "source": "summary",
            "raw_data": {
                "pref": pref,
                "count": count,
                "total": total,
                "rank": i,
                "percent": percent,
            },
        })
    return candidates


def gen_pokemon_rank_candidates(pokemon_stats: dict) -> list[dict]:
    candidates = []
    for i, item in enumerate(pokemon_stats["by_count"][:10], start=1):
        slug = item["slug"]
        candidates.append({
            "id": f"pokemon-rank{i:02d}-{slug}",
            "type": "pokemon_rank",
            "title": f"{item['ja_name']}のポケふた（登場数{i}位）",
            "url": f"{BASE_URL}pokemon/{quote(slug)}/",
            "hashtags": ["#ポケふた", "#ポケモンマンホール"],
            "imageType": "pokemon_rank",
            "source": "summary",
            "raw_data": {
                "ja_name": item["ja_name"],
                "slug": slug,
                "count": item["count"],
                "city_count": item["city_count"],
                "rank": i,
            },
        })
    return candidates


def gen_rare_area_candidates(stats: dict) -> list[dict]:
    total = stats["total"]
    candidates = []
    for item in stats["by_pref"]:
        if not (1 <= item["count"] <= 3):
            continue
        pref = item["pref"]
        count = item["count"]
        candidates.append({
            "id": f"{_pref_slug(pref)}-rare",
            "type": "rare_area",
            "title": f"{pref}のポケふたはわずか{count}枚",
            "url": f"{BASE_URL}summary/",
            "hashtags": ["#ポケふた", "#ポケモンマンホール"],
            "imageType": "summary_rare_area",
            "source": "summary",
            "raw_data": {"pref": pref, "count": count, "total": total},
        })
    return candidates


_PHOTO_RANK_ORDER = {"first_ever": 0, "long_gap": 1, "recent": 2}


def gen_latest_photo_candidates(photos_data: dict, records_by_id: dict) -> list[dict]:
    from datetime import datetime, timezone

    photos = photos_data.get("photos", {})
    r2_base = photos_data.get("image", {}).get("r2_public_base_url", "")
    now = datetime.now(timezone.utc)

    # 都市ごとに写真があるマンホール数をカウント（photo_rank判定に使用）
    city_photo_count: dict[tuple, int] = {}
    for mid in photos:
        rec = records_by_id.get(str(mid), {})
        key = (rec.get("prefecture", ""), rec.get("city", ""))
        if key[0]:
            city_photo_count[key] = city_photo_count.get(key, 0) + 1

    sorted_photos = sorted(
        photos.values(),
        key=lambda p: p.get("created_at", ""),
        reverse=True,
    )[:20]  # 重複除去後に12件に絞るため多めに取る

    raw_candidates = []
    for photo in sorted_photos:
        manhole_id = str(photo.get("manhole_id", ""))
        record = records_by_id.get(manhole_id, {})
        pref = record.get("prefecture", "")
        city = record.get("city", "")
        title = record.get("title", manhole_id)
        pokemons = _filter_pokemons(record.get("pokemons", []))
        storage_key = photo.get("storage_key", "")
        image_url = photo.get("url") or (f"{r2_base}/{storage_key}" if storage_key and r2_base else "")
        photo_id_short = (photo.get("photo_id") or "")[:8]

        created_at_str = photo.get("created_at", "")
        try:
            created_dt = datetime.fromisoformat(created_at_str)
            age_days = (now - created_dt).days
        except ValueError:
            age_days = 0

        city_key = (pref, city)
        n = city_photo_count.get(city_key, 0)
        photo_rank = "first_ever" if n == 1 else ("long_gap" if age_days >= 180 else "recent")

        raw_candidates.append({
            "id": f"photo-{manhole_id}-{photo_id_short}",
            "type": "latest_photo",
            "title": f"最新写真：{title}",
            "url": f"{BASE_URL}manholes/{quote(manhole_id)}/",
            "hashtags": ["#ポケふた", "#ポケモンマンホール"],
            "imageType": "latest_photo",
            "source": "photos",
            "raw_data": {
                "manhole_id": manhole_id,
                "title": title,
                "pref": pref,
                "city": city,
                "pokemon": pokemons[0] if pokemons else "",
                "pokemon_list": pokemons,
                "created_at": created_at_str,
                "image_url": image_url,
                "display_name": photo.get("display_name", ""),
                "photo_rank": photo_rank,
            },
        })

    # 同一都市は best rank のみ残す
    seen: dict[tuple, dict] = {}
    for c in raw_candidates:
        key = (c["raw_data"]["pref"], c["raw_data"]["city"])
        if key not in seen or _PHOTO_RANK_ORDER[c["raw_data"]["photo_rank"]] < _PHOTO_RANK_ORDER[seen[key]["raw_data"]["photo_rank"]]:
            seen[key] = c

    candidates = sorted(
        seen.values(),
        key=lambda c: (_PHOTO_RANK_ORDER[c["raw_data"]["photo_rank"]], c["raw_data"]["created_at"]),
    )
    return list(candidates)[:12]


def gen_no_photo_candidates(records: list[dict], photos_data: dict) -> list[dict]:
    photo_ids = {str(k) for k in photos_data.get("photos", {}).keys()}
    pref_no_photo: dict[str, int] = {}
    pref_total: dict[str, int] = {}
    for record in records:
        if record.get("status") != "active":
            continue
        pref = record.get("prefecture", "")
        if not pref:
            continue
        pref_total[pref] = pref_total.get(pref, 0) + 1
        if str(record.get("id", "")) not in photo_ids:
            pref_no_photo[pref] = pref_no_photo.get(pref, 0) + 1

    top5 = sorted(pref_no_photo.items(), key=lambda x: -x[1])[:5]
    candidates = []
    for pref, no_count in top5:
        candidates.append({
            "id": f"{_pref_slug(pref)}-nophoto",
            "type": "no_photo",
            "title": f"{pref}：写真なしポケふた{no_count}枚",
            "url": f"{BASE_URL}summary/",
            "hashtags": ["#ポケふた", "#ポケモンマンホール"],
            "imageType": "summary_no_photo",
            "source": "summary",
            "raw_data": {
                "pref": pref,
                "no_photo_count": no_count,
                "total_count": pref_total.get(pref, 0),
            },
        })
    return candidates


def gen_travel_trivia_candidates(stats: dict, pokemon_stats: dict) -> list[dict]:
    total = stats["total"]
    empty_prefs = [item["pref"] for item in stats["empty"]]
    regional = stats["regional"]
    top_region = max(regional.items(), key=lambda x: x[1]) if regional else ("", 0)
    species_count = len(pokemon_stats["by_count"])
    widest = pokemon_stats["by_city_count"][0] if pokemon_stats["by_city_count"] else None
    top3 = stats["ranking"][:3]

    candidates: list[dict] = [
        {
            "id": "trivia-total-count",
            "type": "travel_trivia",
            "title": f"全国のポケふたは{total}枚",
            "url": f"{BASE_URL}summary/",
            "hashtags": ["#ポケふた", "#ポケモンマンホール"],
            "imageType": "summary_trivia",
            "source": "summary",
            "raw_data": {"fact_type": "total_count", "values": {"total": total}},
        },
        {
            "id": "trivia-empty-prefs",
            "type": "travel_trivia",
            "title": f"ポケふた未設置県：{len(empty_prefs)}県",
            "url": f"{BASE_URL}summary/",
            "hashtags": ["#ポケふた", "#ポケモンマンホール"],
            "imageType": "summary_trivia",
            "source": "summary",
            "raw_data": {
                "fact_type": "empty_prefs",
                "values": {"empty_count": len(empty_prefs), "pref_names": empty_prefs},
            },
        },
        {
            "id": "trivia-regional-top",
            "type": "travel_trivia",
            "title": f"ポケふたが最も多い地方：{top_region[0]}（{top_region[1]}枚）",
            "url": f"{BASE_URL}summary/",
            "hashtags": ["#ポケふた", "#ポケモンマンホール"],
            "imageType": "summary_trivia",
            "source": "summary",
            "raw_data": {
                "fact_type": "regional_top",
                "values": {"region": top_region[0], "count": top_region[1], "total": total},
            },
        },
        {
            "id": "trivia-pokemon-variety",
            "type": "travel_trivia",
            "title": f"ポケふたに登場するポケモンは{species_count}種類",
            "url": f"{BASE_URL}pokemon/",
            "hashtags": ["#ポケふた", "#ポケモンマンホール"],
            "imageType": "summary_trivia",
            "source": "summary",
            "raw_data": {
                "fact_type": "pokemon_variety",
                "values": {"species_count": species_count},
            },
        },
    ]

    if widest:
        candidates.append({
            "id": f"trivia-widest-{widest['slug']}",
            "type": "travel_trivia",
            "title": f"{widest['ja_name']}のポケふたは{widest['city_count']}市区町村に設置",
            "url": f"{BASE_URL}pokemon/{quote(widest['slug'])}/",
            "hashtags": ["#ポケふた", "#ポケモンマンホール"],
            "imageType": "summary_trivia",
            "source": "summary",
            "raw_data": {
                "fact_type": "pokemon_widest_spread",
                "values": {
                    "ja_name": widest["ja_name"],
                    "slug": widest["slug"],
                    "city_count": widest["city_count"],
                },
            },
        })

    if len(top3) >= 3:
        candidates.append({
            "id": "trivia-top3-ranking",
            "type": "travel_trivia",
            "title": f"都道府県TOP3（{top3[0]['pref']}・{top3[1]['pref']}・{top3[2]['pref']}）",
            "url": f"{BASE_URL}summary/",
            "hashtags": ["#ポケふた", "#ポケモンマンホール"],
            "imageType": "summary_trivia",
            "source": "summary",
            "raw_data": {
                "fact_type": "top3_ranking",
                "values": {
                    "top3": [
                        {"rank": i + 1, "pref": item["pref"], "count": item["count"]}
                        for i, item in enumerate(top3)
                    ],
                    "total": total,
                },
            },
        })

    candidates += [
        {
            "id": "trivia-first-pokefuta",
            "type": "travel_trivia",
            "title": "ポケふた第1号（2018年12月・指宿市・イーブイ）",
            "url": f"{BASE_URL}manholes/1/",
            "hashtags": ["#ポケふた", "#ポケモンマンホール"],
            "imageType": "summary_trivia",
            "source": "summary",
            "raw_data": {
                "fact_type": "first_pokefuta",
                "values": {
                    "date": "2018年12月20日",
                    "pref": "鹿児島県",
                    "city": "指宿市",
                    "location": "指宿駅前",
                    "pokemon": "イーブイ",
                    "reason": "いーぶいすき＝指宿（いぶすき）の語呂合わせ",
                },
            },
        },
        {
            "id": "trivia-ibusuki-eevee-9",
            "type": "travel_trivia",
            "title": "指宿市にイーブイ進化系含む9枚のポケふた",
            "url": f"{BASE_URL}summary/",
            "hashtags": ["#ポケふた", "#ポケモンマンホール"],
            "imageType": "summary_trivia",
            "source": "summary",
            "raw_data": {
                "fact_type": "ibusuki_eevee_9",
                "values": {
                    "city": "指宿市",
                    "pref": "鹿児島県",
                    "count": 9,
                    "pokemon": "イーブイ",
                    "evolution_note": "イーブイ＋進化形8種",
                },
            },
        },
    ]

    return candidates


def gen_michineki_candidates(records: list[dict], michineki: list[dict]) -> list[dict]:
    active = [r for r in records if r.get("status") == "active" and r.get("lat") and r.get("lng")]
    candidates = []
    for station in michineki:
        geo = station.get("geo", {})
        slat, slng = geo.get("latitude"), geo.get("longitude")
        if not slat or not slng:
            continue
        nearby = sorted(
            [
                {
                    "id": r["id"],
                    "title": r.get("title", ""),
                    "city": r.get("city", ""),
                    "pokemons": _filter_pokemons(r.get("pokemons", []))[:2],
                    "dist_km": round(_haversine(slat, slng, r["lat"], r["lng"]), 2),
                    "lat": r["lat"],
                    "lng": r["lng"],
                }
                for r in active
                if _haversine(slat, slng, r["lat"], r["lng"]) <= MICHINEKI_RADIUS_KM
            ],
            key=lambda x: x["dist_km"],
        )
        if len(nearby) < MICHINEKI_MIN_COUNT:
            continue
        pref = station.get("address", {}).get("addressRegion", "")
        sid = station.get("identifier", "")
        candidates.append({
            "id": f"michineki-{sid}",
            "type": "michineki",
            "title": f"{station['name']}周辺のポケふた（{len(nearby)}枚）",
            "url": station.get("url", f"{BASE_URL}summary/"),
            "hashtags": ["#ポケふた", "#ポケモンマンホール"],
            "imageType": "michineki",
            "source": "michineki",
            "raw_data": {
                "station_id": sid,
                "station_name": station["name"],
                "pref": pref,
                "lat": slat,
                "lng": slng,
                "manhole_count": len(nearby),
                "radius_km": MICHINEKI_RADIUS_KM,
                "manholes": nearby,
            },
        })
    return candidates


def gen_remote_island_candidates(records: list[dict]) -> list[dict]:
    by_pref_city: dict[tuple, list] = {}
    for r in records:
        if r.get("status") != "active":
            continue
        key = (r.get("prefecture", ""), r.get("city", ""))
        by_pref_city.setdefault(key, []).append(r)

    candidates = []
    for island in ISLAND_CITY_MAP:
        manholes = by_pref_city.get((island["pref"], island["city"]), [])
        if not manholes:
            continue
        poke_counter: Counter = Counter()
        for m in manholes:
            for p in _filter_pokemons(m.get("pokemons", [])):
                poke_counter[p] += 1
        candidates.append({
            "id": f"island-{island['city']}",
            "type": "remote_island",
            "title": f"{island['island_name']}のポケふた（{len(manholes)}枚）",
            "url": f"{BASE_URL}summary/",
            "hashtags": ["#ポケふた", "#ポケモンマンホール"],
            "imageType": "remote_island",
            "source": "remote_island",
            "raw_data": {
                "island_name": island["island_name"],
                "pref": island["pref"],
                "city": island["city"],
                "manhole_count": len(manholes),
                "manholes": [
                    {
                        "id": m["id"],
                        "title": m.get("title", ""),
                        "pokemons": _filter_pokemons(m.get("pokemons", []))[:3],
                        "lat": m.get("lat"),
                        "lng": m.get("lng"),
                    }
                    for m in manholes
                ],
                "top_pokemons": [p for p, _ in poke_counter.most_common(3)],
            },
        })
    return candidates


def main() -> int:
    if not NDJSON.exists():
        print(f"[ERROR] {NDJSON} not found")
        return 1

    records = load_records(NDJSON)
    active_records = [r for r in records if r.get("status") == "active"]
    records_by_id = {str(r.get("id", "")): r for r in active_records}
    pokemon_metadata = load_pokemon_metadata(POKEMON_METADATA_JSON)
    photos_data = load_photos(PHOTOS_JSON)
    michineki = load_michineki(MICHINEKI_JSON)

    stats = build_stats(active_records)
    pokemon_stats = build_pokemon_stats(active_records, pokemon_metadata)

    candidates: list[dict] = []
    candidates.extend(gen_prefecture_rank_candidates(stats))
    candidates.extend(gen_pokemon_rank_candidates(pokemon_stats))
    candidates.extend(gen_rare_area_candidates(stats))
    candidates.extend(gen_latest_photo_candidates(photos_data, records_by_id))
    candidates.extend(gen_no_photo_candidates(records, photos_data))
    candidates.extend(gen_travel_trivia_candidates(stats, pokemon_stats))
    candidates.extend(gen_michineki_candidates(active_records, michineki))
    candidates.extend(gen_remote_island_candidates(active_records))

    CANDIDATES_JSON.write_text(
        json.dumps(candidates, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    type_counts = Counter(c["type"] for c in candidates)
    print(f"[generate_social_posts] {len(candidates)} candidates → {CANDIDATES_JSON.relative_to(ROOT)}")
    for t, n in sorted(type_counts.items()):
        print(f"  {t}: {n}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
