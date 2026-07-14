#!/usr/bin/env python3
"""Import public design-manhole submissions from pokefuta.com.

The upstream API exposes photo submissions, not canonical manhole places.  This
importer therefore keeps the source snapshot separate, reverse-geocodes the
coordinates, and only links a submission to an existing place when a manual
override explicitly supplies ``canonical_ref``.
"""

from __future__ import annotations

import argparse
import json
import math
import os
import re
import tempfile
import time
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Iterable


API_URL = "https://pokefuta.com/api/design-manholes"
SITE_URL = "https://pokefuta.com/design-manholes"
PHOTO_BASE_URL = "https://pokefuta.com"
GSI_REVERSE_URL = "https://mreversegeocoder.gsi.go.jp/reverse-geocoder/LonLatToAddress"
GSI_MUNI_URL = "https://maps.gsi.go.jp/js/muni.js"
USER_AGENT = "pokefuta-tracker design-manhole importer (+https://github.com/nishiokya/pokefuta-tracker)"
DEFAULT_LIMIT = 200
NEARBY_THRESHOLD_METERS = 50.0


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def load_json(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    return json.loads(path.read_text(encoding="utf-8"))


def load_ndjson(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def atomic_write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        "w", delete=False, dir=path.parent, encoding="utf-8"
    ) as handle:
        handle.write(content)
        handle.flush()
        os.fsync(handle.fileno())
        temporary = Path(handle.name)
    temporary.replace(path)


def write_ndjson(path: Path, rows: Iterable[dict[str, Any]]) -> None:
    atomic_write_text(
        path,
        "".join(
            json.dumps(row, ensure_ascii=False, separators=(",", ":"), sort_keys=True)
            + "\n"
            for row in rows
        ),
    )


def write_json(path: Path, value: Any) -> None:
    atomic_write_text(
        path,
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
    )


def fetch_json(url: str, params: dict[str, str] | None = None) -> Any:
    if params:
        url += "?" + urllib.parse.urlencode(params)
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(request, timeout=30) as response:
        return json.load(response)


def fetch_text(url: str) -> str:
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(request, timeout=30) as response:
        return response.read().decode("utf-8", errors="replace")


def normalize_submission(item: dict[str, Any]) -> dict[str, Any]:
    required = ("id", "latitude", "longitude", "created_at", "photo_url")
    missing = [field for field in required if item.get(field) in (None, "")]
    if missing:
        raise ValueError(f"Design-manhole submission is missing: {', '.join(missing)}")

    latitude = float(item["latitude"])
    longitude = float(item["longitude"])
    if not (-90 <= latitude <= 90 and -180 <= longitude <= 180):
        raise ValueError(f"Invalid coordinates for design-manhole {item['id']}")

    photo_url = urllib.parse.urljoin(PHOTO_BASE_URL, str(item["photo_url"]))
    return {
        "id": str(item["id"]),
        "title": str(item.get("title") or "").strip() or None,
        "description": str(item.get("description") or "").strip() or None,
        "submitter_name": str(item.get("submitter_name") or "").strip() or None,
        "latitude": latitude,
        "longitude": longitude,
        "width": item.get("width"),
        "height": item.get("height"),
        "created_at": str(item["created_at"]),
        "photo_url": photo_url,
    }


def fetch_submissions(limit: int, api_url: str = API_URL) -> list[dict[str, Any]]:
    payload = fetch_json(api_url, {"limit": str(limit)})
    if not payload.get("success") or not isinstance(payload.get("design_manholes"), list):
        raise ValueError("Design-manhole API returned an invalid payload")
    submissions = [normalize_submission(item) for item in payload["design_manholes"]]
    ids = [item["id"] for item in submissions]
    if len(ids) != len(set(ids)):
        raise ValueError("Design-manhole API returned duplicate IDs")
    return sorted(submissions, key=lambda item: (item["created_at"], item["id"]))


class GSIReverseGeocoder:
    def __init__(self) -> None:
        self._municipalities: dict[str, tuple[str, str]] | None = None

    def _load_municipalities(self) -> dict[str, tuple[str, str]]:
        if self._municipalities is not None:
            return self._municipalities
        table: dict[str, tuple[str, str]] = {}
        source = fetch_text(GSI_MUNI_URL)
        for match in re.finditer(r'MUNI_ARRAY\["?(\d{4,5})"?\]\s*=\s*\'([^\']*)\'', source):
            parts = match.group(2).split(",")
            prefecture = parts[1] if len(parts) > 1 else ""
            city = parts[3] if len(parts) > 3 else (parts[2] if len(parts) > 2 else "")
            table[match.group(1).zfill(5)] = (prefecture, city)
        self._municipalities = table
        return table

    def __call__(self, latitude: float, longitude: float) -> dict[str, str]:
        payload = fetch_json(
            GSI_REVERSE_URL,
            {"lat": str(latitude), "lon": str(longitude)},
        )
        result = payload.get("results") or {}
        code = str(result.get("muniCd") or "").zfill(5)
        prefecture, city = self._load_municipalities().get(code, ("", ""))
        town = str(result.get("lv01Nm") or "")
        return {
            "prefecture": prefecture,
            "city": city,
            "address": f"{prefecture}{city}{town}" if (prefecture or city) else town,
        }


def coordinate_key(latitude: float, longitude: float) -> str:
    return f"{latitude:.7f},{longitude:.7f}"


def geocode_submissions(
    submissions: list[dict[str, Any]],
    cache: dict[str, dict[str, str]],
    resolver: Callable[[float, float], dict[str, str]],
    sleep_seconds: float = 0.5,
) -> dict[str, dict[str, str]]:
    updated = dict(cache)
    for submission in submissions:
        key = coordinate_key(submission["latitude"], submission["longitude"])
        if key in updated and (
            updated[key].get("prefecture") or updated[key].get("city")
        ):
            continue
        updated[key] = resolver(submission["latitude"], submission["longitude"])
        if sleep_seconds:
            time.sleep(sleep_seconds)
    return updated


def distance_meters(
    latitude: float, longitude: float, other_latitude: float, other_longitude: float
) -> float:
    lat1, lat2 = math.radians(latitude), math.radians(other_latitude)
    delta_lat = lat2 - lat1
    delta_lng = math.radians(other_longitude - longitude)
    value = (
        math.sin(delta_lat / 2) ** 2
        + math.cos(lat1) * math.cos(lat2) * math.sin(delta_lng / 2) ** 2
    )
    return 6_371_000 * 2 * math.asin(math.sqrt(value))


def nearby_references(
    submission: dict[str, Any],
    reference_sets: dict[str, list[dict[str, Any]]],
    threshold_meters: float = NEARBY_THRESHOLD_METERS,
) -> list[dict[str, Any]]:
    candidates: list[dict[str, Any]] = []
    for source, rows in reference_sets.items():
        for row in rows:
            if row.get("lat") is None or row.get("lng") is None:
                continue
            distance = distance_meters(
                submission["latitude"],
                submission["longitude"],
                float(row["lat"]),
                float(row["lng"]),
            )
            if distance <= threshold_meters:
                candidates.append(
                    {
                        "ref": f"{source}:{row['id']}",
                        "distance_m": round(distance),
                        "title": row.get("title") or row.get("character") or "",
                    }
                )
    return sorted(candidates, key=lambda candidate: (candidate["distance_m"], candidate["ref"]))


def build_public_records(
    submissions: list[dict[str, Any]],
    geocode_cache: dict[str, dict[str, str]],
    overrides: dict[str, dict[str, Any]],
    reference_sets: dict[str, list[dict[str, Any]]],
    imported_at: str,
    previous_records: list[dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    previous_by_id = {
        record.get("source_id"): record for record in (previous_records or [])
    }
    records: list[dict[str, Any]] = []
    for submission in submissions:
        source_id = submission["id"]
        override = overrides.get(source_id, {})
        geography = geocode_cache.get(
            coordinate_key(submission["latitude"], submission["longitude"]), {}
        )
        nearby = nearby_references(submission, reference_sets)
        canonical_ref = override.get("canonical_ref")
        if canonical_ref:
            review_status = "matched"
        elif override.get("review_status"):
            review_status = override["review_status"]
        elif nearby:
            review_status = "needs_review"
        else:
            review_status = "pending"

        record = {
            "id": f"pokefuta-design:{source_id}",
            "source_id": source_id,
            "source": "pokefuta.com",
            "title": override.get("title") or submission.get("title") or "デザインマンホール",
            "description": override.get("description", submission.get("description")),
            "category": override.get("category", "community"),
            "work": override.get("work", ""),
            "prefecture": override.get("prefecture", geography.get("prefecture", "")),
            "city": override.get("city", geography.get("city", "")),
            "address": override.get("address", geography.get("address", "")),
            "lat": submission["latitude"],
            "lng": submission["longitude"],
            "photo_url": submission["photo_url"],
            "source_url": SITE_URL,
            "canonical_ref": canonical_ref,
            "nearby_refs": nearby,
            "review_status": review_status,
            "created_at": submission["created_at"],
            "last_updated": imported_at,
            "status": override.get("status", "active"),
        }
        previous = previous_by_id.get(source_id)
        if previous:
            comparable = {key: value for key, value in record.items() if key != "last_updated"}
            previous_comparable = {
                key: value for key, value in previous.items() if key != "last_updated"
            }
            if comparable == previous_comparable:
                record["last_updated"] = previous.get("last_updated", imported_at)
        records.append(record)
    return sorted(records, key=lambda record: (record["created_at"], record["source_id"]))


def validate_snapshot_size(
    submissions: list[dict[str, Any]],
    previous: list[dict[str, Any]],
    limit: int,
    allow_shrink: bool,
    allow_truncated: bool,
) -> None:
    if len(submissions) >= limit and not allow_truncated:
        raise ValueError(
            f"API returned {len(submissions)} records at the {limit}-record limit; "
            "pagination is required before this snapshot can be trusted"
        )
    if previous and len(submissions) < len(previous) * 0.8 and not allow_shrink:
        raise ValueError(
            f"Refusing suspicious snapshot shrink: {len(previous)} -> {len(submissions)}"
        )


def main() -> None:
    root = Path(__file__).resolve().parents[2]
    parser = argparse.ArgumentParser()
    parser.add_argument("--api-url", default=API_URL)
    parser.add_argument("--limit", type=int, default=DEFAULT_LIMIT)
    parser.add_argument(
        "--raw-output", type=Path, default=root / "apps/scraper/design_manhole_submissions.ndjson"
    )
    parser.add_argument(
        "--output", type=Path, default=root / "docs/design_manholes.ndjson"
    )
    parser.add_argument(
        "--geocode-cache",
        type=Path,
        default=root / "dataset/design_manhole_geocode_cache.json",
    )
    parser.add_argument(
        "--overrides",
        type=Path,
        default=root / "dataset/design_manhole_overrides.json",
    )
    parser.add_argument("--allow-shrink", action="store_true")
    parser.add_argument("--allow-truncated", action="store_true")
    args = parser.parse_args()

    previous = load_ndjson(args.raw_output)
    submissions = fetch_submissions(args.limit, args.api_url)
    validate_snapshot_size(
        submissions, previous, args.limit, args.allow_shrink, args.allow_truncated
    )

    cache = load_json(args.geocode_cache, {})
    cache = geocode_submissions(submissions, cache, GSIReverseGeocoder())
    overrides = load_json(args.overrides, {})
    references = {
        "gundam": load_ndjson(root / "docs/gmanhole.ndjson"),
        "character": load_ndjson(root / "docs/character_manholes.ndjson"),
        "pokefuta": load_ndjson(root / "docs/pokefuta.ndjson"),
    }
    imported_at = utc_now()
    previous_public = load_ndjson(args.output)
    public_records = build_public_records(
        submissions,
        cache,
        overrides,
        references,
        imported_at,
        previous_records=previous_public,
    )

    write_ndjson(args.raw_output, submissions)
    write_json(args.geocode_cache, cache)
    write_ndjson(args.output, public_records)
    print(
        f"Imported {len(submissions)} design-manhole submissions; "
        f"matched={sum(bool(row['canonical_ref']) for row in public_records)} "
        f"needs_review={sum(row['review_status'] == 'needs_review' for row in public_records)}"
    )


if __name__ == "__main__":
    main()
