#!/usr/bin/env python3
"""Manhole Map の公開検索結果を取得し、JSON-LD に変換する。

Usage:
  python3 apps/tools/import_manholemap.py
  python3 apps/tools/import_manholemap.py --refresh
  python3 apps/tools/import_manholemap.py --prefecture 東京都 --output /tmp/tokyo.json
"""

import argparse
import json
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

BASE_URL = "https://manholemap.juge.me"
CITY_CODES_URL = f"{BASE_URL}/getcitycodes?format=json"
SEARCH_URL = f"{BASE_URL}/searchmisc"
REPO_ROOT = Path(__file__).parent.parent.parent
DEFAULT_OUTPUT = REPO_ROOT / "dataset" / "manholemap.json"
DEFAULT_CACHE_DIR = REPO_ROOT / "dataset" / "manholemap-cache"
USER_AGENT = "pokefuta-tracker-manholemap-import/1.0 (+https://github.com/nishioka/pokefuta-tracker)"


def fetch_json(url, *, timeout=60, retries=3):
    request = urllib.request.Request(
        url,
        headers={
            "Accept": "application/json",
            "User-Agent": USER_AGENT,
        },
    )
    for attempt in range(retries):
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                charset = response.headers.get_content_charset() or "utf-8"
                return json.loads(response.read().decode(charset))
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError):
            if attempt == retries - 1:
                raise
            time.sleep(2**attempt)


def load_city_codes():
    cities = fetch_json(CITY_CODES_URL)
    if not isinstance(cities, list):
        raise ValueError("getcitycodes returned a non-list response")
    return cities


def build_municipality_index(cities):
    by_prefecture = {}
    for city in cities:
        prefecture = str(city.get("pref", "")).strip()
        municipality = str(city.get("city", "")).strip()
        if not prefecture or not municipality:
            continue
        by_prefecture.setdefault(prefecture, []).append(municipality)

    # 政令市の区など、長い自治体名を先に照合する。
    return {
        prefecture: sorted(set(names), key=len, reverse=True)
        for prefecture, names in by_prefecture.items()
    }


def detect_municipality(address, prefecture, municipality_index):
    remainder = address[len(prefecture):] if address.startswith(prefecture) else address
    for municipality in municipality_index.get(prefecture, []):
        if remainder.startswith(municipality):
            return municipality
    return ""


def cache_path(cache_dir, prefecture):
    return cache_dir / f"{prefecture}.json"


def fetch_prefecture_records(prefecture, cache_dir, refresh=False):
    path = cache_path(cache_dir, prefecture)
    if path.exists() and not refresh:
        return json.loads(path.read_text(encoding="utf-8"))

    query = urllib.parse.urlencode({"format": "json", "misc": prefecture})
    records = fetch_json(f"{SEARCH_URL}?{query}")
    if not isinstance(records, list):
        raise ValueError(f"searchmisc returned a non-list response for {prefecture}")

    cache_dir.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(records, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return records


def clean_text(value):
    return str(value or "").strip()


def as_number(value, number_type, default=0):
    try:
        return number_type(value)
    except (TypeError, ValueError):
        return default


def record_to_jsonld(record, prefecture, municipality_index):
    identifier = clean_text(record.get("id"))
    address_text = clean_text(record.get("misc") or record.get("address"))
    municipality = detect_municipality(address_text, prefecture, municipality_index)
    tag = clean_text(record.get("tag"))
    description = clean_text(record.get("text"))
    name = tag or description or address_text or f"Manhole Map {identifier}"
    lat = as_number(record.get("lat"), float, None)
    lng = as_number(record.get("lng"), float, None)

    item = {
        "@id": f"{BASE_URL}/page?id={urllib.parse.quote(identifier)}",
        "@type": "Place",
        "additionalType": "https://www.wikidata.org/wiki/Q652657",
        "identifier": identifier,
        "name": name,
        "url": f"{BASE_URL}/page?id={urllib.parse.quote(identifier)}",
        "mainEntityOfPage": f"{BASE_URL}/page?id={urllib.parse.quote(identifier)}",
        "image": {
            "@type": "ImageObject",
            "contentUrl": f"{BASE_URL}/get?id={urllib.parse.quote(identifier)}",
            "encodingFormat": clean_text(record.get("type")) or "image/jpeg",
            "width": as_number(record.get("width"), int),
            "height": as_number(record.get("height"), int),
        },
        "address": {
            "@type": "PostalAddress",
            "streetAddress": address_text,
            "addressRegion": prefecture,
            "addressCountry": "JP",
        },
        "geo": {
            "@type": "GeoCoordinates",
            "latitude": lat,
            "longitude": lng,
        },
        "dateCreated": clean_text(record.get("created")),
        "dateModified": clean_text(record.get("updated")),
        "author": {
            "@type": "Person",
            "name": clean_text(record.get("username")),
        },
        "interactionStatistic": {
            "@type": "InteractionCounter",
            "interactionType": "https://schema.org/LikeAction",
            "userInteractionCount": as_number(record.get("nice"), int),
        },
        "additionalProperty": [
            {
                "@type": "PropertyValue",
                "name": "tag",
                "value": tag,
            },
            {
                "@type": "PropertyValue",
                "name": "sourceAddress",
                "value": address_text,
            },
        ],
    }
    if description:
        item["description"] = description
    if municipality:
        item["address"]["addressLocality"] = municipality

    # 無効な座標や空文字をJSON-LDに残さない。
    if lat is None or lng is None:
        item.pop("geo")
    if not item["author"]["name"]:
        item.pop("author")
    if not item["dateCreated"]:
        item.pop("dateCreated")
    if not item["dateModified"]:
        item.pop("dateModified")
    if not tag:
        item["additionalProperty"] = [
            prop for prop in item["additionalProperty"] if prop["name"] != "tag"
        ]
    return item


def build_jsonld(records, municipality_index, fetched_at):
    seen = set()
    graph = []
    for prefecture, record in records:
        identifier = clean_text(record.get("id"))
        if not identifier or identifier in seen:
            continue
        seen.add(identifier)
        graph.append(record_to_jsonld(record, prefecture, municipality_index))

    graph.sort(key=lambda item: item["identifier"])
    return {
        "@context": "https://schema.org",
        "@type": "Dataset",
        "name": "Manhole Map public records",
        "description": "Manhole Map の公開検索結果を、近隣マンホール調査用にJSON-LDへ変換したローカルデータセット。",
        "url": f"{BASE_URL}/bycity",
        "isBasedOn": f"{BASE_URL}/bycity",
        "dateModified": fetched_at,
        "usageInfo": f"{BASE_URL}/tou",
        "creator": {
            "@type": "Organization",
            "name": "Manhole Map",
            "url": BASE_URL,
        },
        "distribution": {
            "@type": "DataDownload",
            "encodingFormat": "application/ld+json",
        },
        "numberOfItems": len(graph),
        "@graph": graph,
    }


def parse_args():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--cache-dir", type=Path, default=DEFAULT_CACHE_DIR)
    parser.add_argument(
        "--prefecture",
        action="append",
        help="対象都道府県。複数指定可。省略時は全国。",
    )
    parser.add_argument("--delay", type=float, default=0.25, help="API呼び出し間隔（秒）")
    parser.add_argument("--refresh", action="store_true", help="キャッシュを使わず再取得")
    return parser.parse_args()


def main():
    args = parse_args()
    cities = load_city_codes()
    municipality_index = build_municipality_index(cities)
    available = list(municipality_index)
    targets = args.prefecture or available
    unknown = sorted(set(targets) - set(available))
    if unknown:
        raise SystemExit(f"Unknown prefecture: {', '.join(unknown)}")

    all_records = []
    for index, prefecture in enumerate(targets, start=1):
        records = fetch_prefecture_records(
            prefecture,
            args.cache_dir,
            refresh=args.refresh,
        )
        print(f"[{index:02d}/{len(targets):02d}] {prefecture}: {len(records)} records")
        all_records.extend((prefecture, record) for record in records)
        if index < len(targets) and args.delay > 0:
            time.sleep(args.delay)

    fetched_at = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    jsonld = build_jsonld(all_records, municipality_index, fetched_at)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(jsonld, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(f"Saved {jsonld['numberOfItems']} records -> {args.output}")


if __name__ == "__main__":
    main()
