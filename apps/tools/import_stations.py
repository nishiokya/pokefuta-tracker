#!/usr/bin/env python3
"""国土数値情報の鉄道データ (N02) から駅一覧を作り、駅前/駅近/駅遠タグを付け直す。

Usage:
  python3 apps/tools/import_stations.py [--dry-run]

タグの定義（最寄り駅の中心からの直線距離）:
  station_front  <= 150m   駅前広場・駅舎に隣接している
  near_station   <= 500m   駅から歩いてすぐ
  far_station    >= 10km   公共交通では行きにくい

離島（remote_island）は「駅が無いのが当たり前」なので far_station から外す。
in_station（駅構内）は距離では判定できないので手動運用のまま触らない。
"""

import argparse
import io
import json
import math
import sys
import urllib.request
import zipfile
from collections import defaultdict
from pathlib import Path

DATA_URL = "https://nlftp.mlit.go.jp/ksj/gml/data/N02/N02-24/N02-24_GML.zip"
GEOJSON_NAME = "UTF-8/N02-24_Station.geojson"
REPO_ROOT = Path(__file__).parent.parent.parent
STATIONS_JSON = REPO_ROOT / "dataset" / "stations.json"
TITLES_JSON = REPO_ROOT / "dataset" / "manhole_titles.json"
POKEFUTA_NDJSON = REPO_ROOT / "apps" / "scraper" / "pokefuta.ndjson"

FRONT_M = 150
NEAR_M = 500
FAR_M = 10_000

DISTANCE_TAGS = ("station_front", "near_station", "far_station")

KEY_ORDER = [
    "building", "address_raw", "address_norm", "prefecture", "city",
    "place_detail", "verified_at", "tags", "confidence", "official_url",
]


def haversine_m(lat1, lng1, lat2, lng2):
    R = 6_371_000
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = math.radians(lat2 - lat1)
    dl = math.radians(lng2 - lng1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return R * 2 * math.asin(math.sqrt(a))


def _centroid(geometry):
    """N02 の駅はホームに沿った線分。その重心を駅の代表点として使う。"""
    kind = geometry.get("type")
    if kind == "LineString":
        coords = geometry["coordinates"]
    elif kind == "MultiLineString":
        coords = [c for part in geometry["coordinates"] for c in part]
    elif kind == "Point":
        coords = [geometry["coordinates"]]
    else:
        return None
    if not coords:
        return None
    return (
        sum(c[1] for c in coords) / len(coords),
        sum(c[0] for c in coords) / len(coords),
    )


def download_and_parse():
    print(f"Downloading {DATA_URL} ...")
    with urllib.request.urlopen(DATA_URL) as resp:
        raw = resp.read()

    with zipfile.ZipFile(io.BytesIO(raw)) as z:
        geojson = json.loads(z.read(GEOJSON_NAME).decode("utf-8"))

    # 同じ駅がホームごとに複数レコードで入っているので、駅名×事業者×路線でまとめる
    groups = defaultdict(list)
    for feature in geojson["features"]:
        point = _centroid(feature["geometry"])
        if point is None:
            continue
        props = feature["properties"]
        key = (props.get("N02_005"), props.get("N02_004"), props.get("N02_003"))
        groups[key].append(point)

    stations = []
    for (name, operator, line), points in groups.items():
        if not name:
            continue
        stations.append({
            "name": name,
            "operator": operator,
            "line": line,
            "lat": sum(p[0] for p in points) / len(points),
            "lng": sum(p[1] for p in points) / len(points),
        })

    print(f"Parsed {len(stations)} stations "
          f"({len({s['name'] for s in stations})} unique names)")
    return stations


def save_jsonld(stations):
    graph = [
        {
            "@type": "TrainStation",
            "name": s["name"],
            "provider": s["operator"],
            "containedInPlace": s["line"],
            "geo": {
                "@type": "GeoCoordinates",
                "latitude": s["lat"],
                "longitude": s["lng"],
            },
        }
        for s in stations
    ]
    jsonld = {
        "@context": "https://schema.org",
        "attribution": "「国土数値情報（鉄道データ N02-24）」（国土交通省）を加工して作成",
        "license": "https://nlftp.mlit.go.jp/ksj/other/agreement.html",
        "@graph": graph,
    }
    STATIONS_JSON.write_text(json.dumps(jsonld, ensure_ascii=False, indent=2) + "\n")
    print(f"Saved JSON-LD → {STATIONS_JSON}")


def load_pokefuta():
    records = []
    with open(POKEFUTA_NDJSON, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            r = json.loads(line)
            if r.get("status") == "active" and r.get("lat") and r.get("lng"):
                records.append(r)
    print(f"Loaded {len(records)} active pokefuta")
    return records


def nearest_station(record, stations):
    best = (float("inf"), None)
    lat, lng = record["lat"], record["lng"]
    for s in stations:
        # 粗い矩形で足切りしてから距離を出す（緯度0.06度 ≒ 6.7km）
        if abs(s["lat"] - lat) > 0.12 or abs(s["lng"] - lng) > 0.14:
            continue
        d = haversine_m(lat, lng, s["lat"], s["lng"])
        if d < best[0]:
            best = (d, s)
    if best[1] is None:
        for s in stations:
            d = haversine_m(lat, lng, s["lat"], s["lng"])
            if d < best[0]:
                best = (d, s)
    return best


def desired_tag(distance_m, current_tags):
    if distance_m <= FRONT_M:
        return "station_front"
    if distance_m <= NEAR_M:
        return "near_station"
    if distance_m >= FAR_M and "remote_island" not in current_tags:
        return "far_station"
    return None


def reorder_entry(entry):
    result = {k: entry[k] for k in KEY_ORDER if k in entry}
    for k, v in entry.items():
        if k not in result:
            result[k] = v
    return result


def serialize_titles(data):
    sorted_manholes = dict(
        sorted(
            ((k, reorder_entry(v)) for k, v in data["manholes"].items()),
            key=lambda x: int(x[0]),
        )
    )
    out = {**data, "manholes": sorted_manholes}
    return json.dumps(out, ensure_ascii=False, indent=2) + "\n"


def apply_patches(pokefuta, stations, titles, dry_run):
    changed = 0
    prefix = "[DRY-RUN] " if dry_run else ""
    for r in sorted(pokefuta, key=lambda x: int(x["id"])):
        mid = str(r["id"])
        entry = titles["manholes"].get(mid, {})
        current = list(entry.get("tags") or [])

        distance, station = nearest_station(r, stations)
        want = desired_tag(distance, current)
        have = [t for t in current if t in DISTANCE_TAGS]

        # in_station は駅構内かどうかの手動判断なので、距離では上書きしない
        if "in_station" in current:
            continue
        if have == ([want] if want else []):
            continue

        tags = [t for t in current if t not in DISTANCE_TAGS]
        if want:
            tags.append(want)

        changed += 1
        name = station["name"] if station else "?"
        print(f"  {prefix}#{mid} {distance:7.0f}m ~{name}  "
              f"{have or ['なし']} → {[want] if want else ['なし']}")
        if not dry_run:
            entry = dict(entry)
            entry["tags"] = tags
            titles["manholes"][mid] = entry
    return changed


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    stations = download_and_parse()
    save_jsonld(stations)

    pokefuta = load_pokefuta()
    titles = json.loads(TITLES_JSON.read_text(encoding="utf-8"))

    print(f"\n{'=' * 50}")
    print(f"駅前 <={FRONT_M}m / 駅近 <={NEAR_M}m / 駅遠 >={FAR_M}m")
    changed = apply_patches(pokefuta, stations, titles, args.dry_run)

    if not changed:
        print("\nNo updates needed")
        return
    if args.dry_run:
        print(f"\n(dry-run) Would update {changed} record(s)")
        return

    TITLES_JSON.write_text(serialize_titles(titles), encoding="utf-8")
    print(f"\nUpdated {changed} record(s) in {TITLES_JSON.name}")


if __name__ == "__main__":
    main()
