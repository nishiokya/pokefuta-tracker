#!/usr/bin/env python3
"""道の駅データ (linkdata.org) を JSON-LD 化し、50m以内の pokefuta を roadside 登録する。

Usage:
  python3 apps/tools/import_michineki.py [--dry-run]
"""

import json
import math
import re
import sys
import urllib.request
from pathlib import Path

DATA_URL = "https://linkdata.org/download/rdf1s2861i/link/roadside_station.txt"
REPO_ROOT = Path(__file__).parent.parent.parent
MICHINEKI_JSON = REPO_ROOT / "dataset" / "michineki.json"
TITLES_JSON = REPO_ROOT / "dataset" / "manhole_titles.json"
POKEFUTA_NDJSON = REPO_ROOT / "apps" / "scraper" / "pokefuta.ndjson"

RADIUS_M = 50

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


def download_and_parse():
    print(f"Downloading {DATA_URL} ...")
    with urllib.request.urlopen(DATA_URL) as resp:
        raw = resp.read().decode("utf-8")

    lines = raw.splitlines()

    # Find #property header to get column names
    props = None
    for line in lines:
        if line.startswith("#property\t"):
            props = line[len("#property\t"):].split("\t")
            break
    if not props:
        raise ValueError("#property header not found")

    stations = []
    for line in lines:
        if line.startswith("#") or not line.strip():
            continue
        parts = line.split("\t")
        if len(parts) < 11:
            continue

        # parts[0] = subject URI, parts[1:] = property values
        data = dict(zip(props, parts[1:]))

        if data.get("iclt:状態") == "廃止":
            continue

        try:
            lat = float(data["geo:lat"])
            lng = float(data["geo:long"])
        except (KeyError, ValueError):
            continue

        raw_name = data.get("iclt:名称", "")
        # Clean Wikipedia-style names: remove disambiguation "_(XXX)" and replace _ with space
        name = re.sub(r"_\([^)]+\)$", "", raw_name).replace("_", " ").strip()

        stations.append({
            "id": data.get("iclt:ID", ""),
            "name": name,
            "prefecture": data.get("iclt:都道府県", ""),
            "city": data.get("iclt:市区町村", ""),
            "address": data.get("iclt:住所", ""),
            "lat": lat,
            "lng": lng,
            "url": parts[0],
        })

    print(f"Parsed {len(stations)} active stations")
    return stations


def save_jsonld(stations):
    graph = [
        {
            "@type": "TouristAttraction",
            "identifier": s["id"],
            "name": s["name"],
            "address": {
                "@type": "PostalAddress",
                "streetAddress": s["address"],
                "addressRegion": s["prefecture"],
                "addressLocality": s["city"],
                "addressCountry": "JP",
            },
            "geo": {
                "@type": "GeoCoordinates",
                "latitude": s["lat"],
                "longitude": s["lng"],
            },
            "url": s["url"],
        }
        for s in stations
    ]
    jsonld = {
        "@context": "https://schema.org",
        "attribution": "「国土数値情報（道の駅データ）」（国土交通省）をもとに東京福祉専門学校IT医療ソーシャルワーカー科作成",
        "license": "https://creativecommons.org/licenses/by-nc/3.0/deed.ja",
        "@graph": graph,
    }
    MICHINEKI_JSON.write_text(json.dumps(jsonld, ensure_ascii=False, indent=2) + "\n")
    print(f"Saved JSON-LD → {MICHINEKI_JSON}")


def load_pokefuta():
    records = []
    with open(POKEFUTA_NDJSON) as f:
        for line in f:
            r = json.loads(line.strip())
            if r.get("status") == "active":
                records.append(r)
    print(f"Loaded {len(records)} active pokefuta")
    return records


def find_matches(stations, pokefuta):
    matches = []
    for r in pokefuta:
        for s in stations:
            d = haversine_m(r["lat"], r["lng"], s["lat"], s["lng"])
            if d <= RADIUS_M:
                matches.append({
                    "pokefuta_id": str(r["id"]),
                    "pokefuta_address": r["address"],
                    "station_name": s["name"],
                    "station_id": s["id"],
                    "distance_m": round(d, 1),
                })
    return sorted(matches, key=lambda x: x["distance_m"])


def reorder_entry(entry):
    result = {}
    for k in KEY_ORDER:
        if k in entry:
            result[k] = entry[k]
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


def apply_patches(matches, titles, dry_run):
    changed = 0
    for m in matches:
        mid = m["pokefuta_id"]
        station_name = m["station_name"]
        entry = titles["manholes"].get(mid, {})
        current_building = entry.get("building", "")
        current_tags = set(entry.get("tags") or [])

        new_entry = dict(entry)
        actions = []

        if not current_building:
            new_entry["building"] = station_name
            actions.append(f"building={station_name}")

        if "roadside" not in current_tags:
            new_entry["tags"] = sorted(current_tags | {"roadside"})
            actions.append("tag+roadside")

        if actions:
            changed += 1
            prefix = "[DRY-RUN] " if dry_run else ""
            print(
                f"  {prefix}#{mid} ({m['pokefuta_address']}) "
                f"← {station_name} {m['distance_m']}m  [{', '.join(actions)}]"
            )
            if not dry_run:
                titles["manholes"][mid] = new_entry
        else:
            print(f"  skip #{mid} — already registered ({station_name} {m['distance_m']}m)")

    return changed


def main():
    dry_run = "--dry-run" in sys.argv

    stations = download_and_parse()
    save_jsonld(stations)

    pokefuta = load_pokefuta()
    matches = find_matches(stations, pokefuta)

    print(f"\n{'=' * 50}")
    print(f"Matches within {RADIUS_M}m: {len(matches)}")
    if not matches:
        print("  (none)")
        return

    titles = json.loads(TITLES_JSON.read_text())
    changed = apply_patches(matches, titles, dry_run)

    if not dry_run and changed > 0:
        TITLES_JSON.write_text(serialize_titles(titles))
        print(f"\nUpdated {changed} record(s) in {TITLES_JSON.name}")
    elif dry_run:
        print(f"\n(dry-run) Would update {changed} record(s)")
    else:
        print("\nNo updates needed")


if __name__ == "__main__":
    main()
