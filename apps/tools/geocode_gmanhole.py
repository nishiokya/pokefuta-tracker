#!/usr/bin/env python3
"""Re-geocode Gundam manholes and persist a complete provider audit trail."""

from __future__ import annotations

import argparse
import json
import math
import re
import time
import unicodedata
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

USER_AGENT = "pokefuta-tracker-gmanhole-geocoder/1.0"
WARNING_TITLE = "Warning:"


def load_ndjson(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def write_ndjson(path: Path, rows: list[dict[str, Any]]) -> None:
    path.write_text(
        "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows),
        encoding="utf-8",
    )


def normalize(value: str) -> str:
    value = unicodedata.normalize("NFKC", value or "")
    value = value.replace("－", "-").replace("―", "-")
    return re.sub(r"\s+", " ", value).strip()


def ensure_full_address(address: str, prefecture: str, city: str) -> str:
    query = normalize(address)
    if prefecture and prefecture not in query:
        query = prefecture + query
    if city and city not in query:
        query = prefecture + city + normalize(address)
    return query


def fetch_json(url: str, params: dict[str, str]) -> Any:
    request = urllib.request.Request(
        url + "?" + urllib.parse.urlencode(params),
        headers={"User-Agent": USER_AGENT},
    )
    with urllib.request.urlopen(request, timeout=25) as response:
        return json.load(response)


def text_overlap(left: str, right: str) -> float:
    left_chars = set(re.sub(r"[\W_]", "", normalize(left)))
    right_chars = set(re.sub(r"[\W_]", "", normalize(right)))
    if not left_chars:
        return 0.0
    return len(left_chars & right_chars) / len(left_chars)


def distance_km(left: dict[str, Any], right: dict[str, Any]) -> float:
    lat1, lng1, lat2, lng2 = map(
        math.radians,
        [left["lat"], left["lng"], right["lat"], right["lng"]],
    )
    dlat = lat2 - lat1
    dlng = lng2 - lng1
    value = math.sin(dlat / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlng / 2) ** 2
    return 6371 * 2 * math.asin(math.sqrt(value))


def gsi_candidates(query: str, strategy: str, record: dict[str, Any]) -> list[dict[str, Any]]:
    raw = fetch_json(
        "https://msearch.gsi.go.jp/address-search/AddressSearch",
        {"q": query},
    )
    candidates = []
    for index, item in enumerate(raw[:5]):
        coords = item.get("geometry", {}).get("coordinates", [])
        if len(coords) < 2:
            continue
        label = item.get("properties", {}).get("title", "")
        overlap = text_overlap(query, label)
        score = round(45 + overlap * 45 - index * 2)
        candidates.append({
            "provider": "gsi",
            "strategy": strategy,
            "query": query,
            "rank": index + 1,
            "label": label,
            "lat": float(coords[1]),
            "lng": float(coords[0]),
            "score": score,
            "reason": f"GSI住所候補（文字一致 {overlap:.0%}）",
        })
    return candidates


def nominatim_candidates(query: str, strategy: str, record: dict[str, Any]) -> list[dict[str, Any]]:
    raw = fetch_json(
        "https://nominatim.openstreetmap.org/search",
        {
            "q": query + ", Japan",
            "format": "jsonv2",
            "limit": "5",
            "addressdetails": "1",
            "countrycodes": "jp",
        },
    )
    candidates = []
    expected = " ".join([
        record.get("prefecture", ""),
        record.get("city", ""),
        record.get("title", "") if strategy == "place_name" else record.get("address", ""),
    ])
    for index, item in enumerate(raw):
        label = item.get("display_name", "")
        overlap = text_overlap(expected, label)
        score = round((78 if strategy == "place_name" else 70) + overlap * 20 - index * 2)
        candidates.append({
            "provider": "nominatim",
            "strategy": strategy,
            "query": query,
            "rank": index + 1,
            "label": label,
            "lat": float(item["lat"]),
            "lng": float(item["lon"]),
            "score": min(98, score),
            "reason": f"Nominatim {strategy}候補（文字一致 {overlap:.0%}）",
            "category": item.get("category", ""),
            "type": item.get("type", ""),
        })
    return candidates


def yahoo_candidates(query: str, strategy: str, app_id: str) -> list[dict[str, Any]]:
    raw = fetch_json(
        "https://map.yahooapis.jp/geocode/V1/geoCoder",
        {
            "output": "json",
            "appid": app_id,
            "query": query,
            "results": "5",
        },
    )
    candidates = []
    for index, item in enumerate(raw.get("Feature", [])[:5]):
        coordinates = item.get("Geometry", {}).get("Coordinates", "").split(",")
        if len(coordinates) != 2:
            continue
        properties = item.get("Property", {})
        label = properties.get("Address") or item.get("Name", "")
        matching_level = int(properties.get("AddressMatchingLevel") or 0)
        overlap = text_overlap(query, label)
        score = min(99, round(50 + matching_level * 6 + overlap * 15 - index * 2))
        candidates.append({
            "provider": "yahoo",
            "strategy": strategy,
            "query": query,
            "rank": index + 1,
            "label": label,
            "lat": float(coordinates[1]),
            "lng": float(coordinates[0]),
            "score": score,
            "reason": f"Yahoo住所候補（一致レベル {matching_level} / 文字一致 {overlap:.0%}）",
            "matching_level": matching_level,
            "address_type": properties.get("AddressType", ""),
            "government_code": properties.get("GovernmentCode", ""),
        })
    return candidates


def select_candidate(candidates: list[dict[str, Any]]) -> tuple[dict[str, Any] | None, str]:
    if not candidates:
        return None, "候補なし"
    exact_yahoo_matches = [
        candidate for candidate in candidates
        if candidate["provider"] == "yahoo"
        and candidate["strategy"] == "official_address"
        and candidate["rank"] == 1
        and candidate.get("matching_level", 0) >= 4
        and candidate["score"] >= 75
    ]
    if exact_yahoo_matches:
        selected = max(exact_yahoo_matches, key=lambda candidate: candidate["score"])
        return selected, "Yahooが公式住所を街区・地番以上の精度で解決したため優先採用"
    exact_gsi_matches = [
        candidate for candidate in candidates
        if candidate["provider"] == "gsi"
        and candidate["strategy"] == "official_address"
        and candidate["score"] >= 70
    ]
    if exact_gsi_matches:
        selected = max(exact_gsi_matches, key=lambda candidate: candidate["score"])
        return selected, "公式住所を変更せずに得たGSI候補を優先採用"
    gsi_matches = [
        candidate for candidate in candidates
        if candidate["provider"] == "gsi" and candidate["score"] >= 60
    ]
    if gsi_matches:
        selected = max(gsi_matches, key=lambda candidate: candidate["score"])
        return selected, "公式住所のGSI候補を優先し、文字一致が最も高い候補を採用"
    address_matches = [
        candidate for candidate in candidates
        if candidate["strategy"] == "official_address" and candidate["score"] >= 70
    ]
    if address_matches:
        selected = max(address_matches, key=lambda candidate: candidate["score"])
        return selected, "公式住所のフォールバック候補を採用"
    selected = max(candidates, key=lambda candidate: candidate["score"])
    return selected, "低信頼候補を暫定採用（要確認）"


def gsi_queries(record: dict[str, Any], address: str) -> list[tuple[str, str]]:
    queries = [("official_address", address)]
    without_number = re.sub(r"\s*[0-9]+(?:[-ーの番地号0-9]*)?\s*$", "", address).strip()
    if without_number and without_number != address:
        queries.append(("address_without_number", without_number))

    title = normalize(record.get("title", ""))
    tail = title.split(" ")[-1]
    tail = re.sub(r"(入口|付近|敷地内|公園内|広場内|歩道)$", "", tail)
    if tail and tail != title and len(tail) >= 3:
        place_query = normalize(record.get("prefecture", "") + record.get("city", "") + tail)
        if place_query not in {query for _, query in queries}:
            queries.append(("title_locality", place_query))
    return queries


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", default="docs/gmanhole.ndjson")
    parser.add_argument("--output", default="docs/gmanhole.ndjson")
    parser.add_argument("--audit", default="dataset/gmanhole_geocode_audit.json")
    parser.add_argument("--cache", default="gmanhole_geocode_cache.json")
    parser.add_argument("--addresses", help="Optional ID-tab-address file from the official site")
    parser.add_argument("--reuse-audit", help="Reuse attempts/candidates from an existing audit without network calls")
    parser.add_argument("--yahoo-app-id", default="nishioka")
    parser.add_argument("--skip-yahoo", action="store_true")
    parser.add_argument("--nominatim-sleep", type=float, default=1.05)
    parser.add_argument("--skip-nominatim", action="store_true")
    args = parser.parse_args()

    rows = load_ndjson(Path(args.input))
    official_addresses: dict[str, str] = {}
    if args.addresses:
        for line in Path(args.addresses).read_text(encoding="utf-8").splitlines():
            record_id, address = line.split("\t", 1)
            official_addresses[record_id] = address
    reused_records: dict[str, dict[str, Any]] = {}
    if args.reuse_audit:
        reused = json.loads(Path(args.reuse_audit).read_text(encoding="utf-8"))
        reused_records = {str(record["id"]): record for record in reused.get("records", [])}

    generated_at = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    audits: list[dict[str, Any]] = []
    cache: dict[str, dict[str, Any]] = {}
    for record in rows:
        record_id = str(record.get("id", ""))
        old_coordinate = (
            {"lat": record["lat"], "lng": record["lng"]}
            if record.get("lat") is not None and record.get("lng") is not None
            else None
        )
        if record_id in official_addresses:
            record["address"] = official_addresses[record_id]

        if WARNING_TITLE in record.get("title", "") or not record.get("prefecture"):
            record["status"] = "invalid"
            record["lat"] = None
            record["lng"] = None
            record["geocoded"] = False
            audits.append({
                "id": record_id,
                "title": record.get("title", ""),
                "status": "invalid_source_page",
                "address": record.get("address", ""),
                "old_coordinate": old_coordinate,
                "selected": None,
                "selection_reason": "公式ページがPHP Warningで実在レコードを返していない",
                "attempts": [],
                "candidates": [],
            })
            continue

        address = ensure_full_address(
            record.get("address", ""),
            record.get("prefecture", ""),
            record.get("city", ""),
        )
        record["address"] = address
        reused_record = reused_records.get(record_id)
        if reused_record and "old_coordinate" in reused_record:
            old_coordinate = reused_record["old_coordinate"]
        attempts: list[dict[str, Any]] = list(reused_record.get("attempts", [])) if reused_record else []
        candidates: list[dict[str, Any]] = list(reused_record.get("candidates", [])) if reused_record else []

        if not reused_record:
            for strategy, query in gsi_queries(record, address):
                try:
                    found = gsi_candidates(query, strategy, record)
                    candidates.extend(found)
                    attempts.append({"provider": "gsi", "strategy": strategy, "query": query, "result_count": len(found), "error": None})
                except Exception as error:  # noqa: BLE001
                    attempts.append({"provider": "gsi", "strategy": strategy, "query": query, "result_count": 0, "error": str(error)})

        if not args.skip_yahoo:
            # Reused audits may predate Yahoo support, so only skip an already recorded Yahoo attempt.
            has_yahoo_attempt = any(
                attempt.get("provider") == "yahoo"
                and attempt.get("strategy") == "official_address"
                and attempt.get("query") == address
                for attempt in attempts
            )
            if not has_yahoo_attempt:
                try:
                    found = yahoo_candidates(address, "official_address", args.yahoo_app_id)
                    candidates.extend(found)
                    attempts.append({"provider": "yahoo", "strategy": "official_address", "query": address, "result_count": len(found), "error": None})
                except Exception as error:  # noqa: BLE001
                    attempts.append({"provider": "yahoo", "strategy": "official_address", "query": address, "result_count": 0, "error": str(error)})

        if not reused_record and not args.skip_nominatim:
            queries = [
                ("official_address", address),
                ("place_name", " ".join(filter(None, [record.get("prefecture"), record.get("city"), record.get("title")]))),
            ]
            for strategy, query in queries:
                try:
                    found = nominatim_candidates(query, strategy, record)
                    candidates.extend(found)
                    attempts.append({"provider": "nominatim", "strategy": strategy, "query": query, "result_count": len(found), "error": None})
                except Exception as error:  # noqa: BLE001
                    attempts.append({"provider": "nominatim", "strategy": strategy, "query": query, "result_count": 0, "error": str(error)})
                time.sleep(max(args.nominatim_sleep, 1.0))

        selected, selection_reason = select_candidate(candidates)
        if selected:
            record["lat"] = selected["lat"]
            record["lng"] = selected["lng"]
            record["geocoded"] = True
            record["geocode_provider"] = selected["provider"]
            record["geocode_strategy"] = selected["strategy"]
            record["geocode_score"] = selected["score"]
            record["last_updated"] = generated_at
            cache_key = "|".join([
                record.get("prefecture", ""),
                record.get("city", ""),
                normalize(record.get("address", "")),
            ])
            cache[cache_key] = {
                "lat": selected["lat"],
                "lng": selected["lng"],
                "provider": selected["provider"],
                "strategy": selected["strategy"],
                "score": selected["score"],
                "query": selected["query"],
                "updated_at": generated_at,
            }
        else:
            record["lat"] = None
            record["lng"] = None
            record["geocoded"] = False

        audits.append({
            "id": record_id,
            "title": record.get("title", ""),
            "prefecture": record.get("prefecture", ""),
            "city": record.get("city", ""),
            "status": "selected" if selected else "unresolved",
            "address": address,
            "detail_url": record.get("detail_url", ""),
            "old_coordinate": old_coordinate,
            "selected": selected,
            "selection_reason": selection_reason,
            "old_distance_km": round(distance_km(old_coordinate, selected), 3) if old_coordinate and selected else None,
            "attempts": attempts,
            "candidates": candidates,
        })

    write_ndjson(Path(args.output), rows)
    Path(args.audit).write_text(
        json.dumps({"generated_at": generated_at, "records": audits}, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    Path(args.cache).write_text(
        json.dumps(cache, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    selected_count = sum(audit["selected"] is not None for audit in audits)
    invalid_count = sum(audit["status"] == "invalid_source_page" for audit in audits)
    print(f"updated={selected_count} invalid={invalid_count} unresolved={len(audits) - selected_count - invalid_count}")


if __name__ == "__main__":
    main()
