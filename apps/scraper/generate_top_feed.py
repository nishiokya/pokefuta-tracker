#!/usr/bin/env python3
"""Generate a lightweight top-feed.json for the top page hero + community stats.

docs/latest-manhole-photos.json (200KB+) をトップページでそのまま fetch させず、
ヒーロー表示に必要な最小メタデータだけをビルド時に焼き込む。
pages-deploy.yml から実行され dist/api/top-feed.json を出力する。

Usage:
  python3 apps/scraper/generate_top_feed.py --output dist/api/top-feed.json
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PHOTOS_JSON = ROOT / "docs" / "latest-manhole-photos.json"
NDJSON = ROOT / "docs" / "pokefuta.ndjson"
SITE_STATS_JSON = ROOT / "docs" / "api" / "site-stats.json"
IMAGE_DIR = ROOT / "dataset" / "manhole" / "image"

MAX_PHOTOS = 12
COMMENT_MAX_LEN = 80

# pokefuta.ndjson の pokemons に混ざる非ポケモン表記（トップページ JS と同じ除外規則）
_EXCLUDED_POKEMON_PATTERN = "ローカルActs"


def load_json(path: Path) -> dict:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}


def load_records_by_id(path: Path) -> dict[str, dict]:
    records: dict[str, dict] = {}
    if not path.exists():
        return records
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            record = json.loads(line)
        except json.JSONDecodeError:
            continue
        if record.get("status", "active") != "active":
            continue
        records[str(record.get("id", ""))] = record
    return records


def sanitize_comment(text: object) -> str | None:
    """Collapse whitespace/newlines and cap the length for hero display."""
    if not isinstance(text, str):
        return None
    collapsed = re.sub(r"\s+", " ", text).strip()
    if not collapsed:
        return None
    if len(collapsed) > COMMENT_MAX_LEN:
        collapsed = collapsed[: COMMENT_MAX_LEN - 1].rstrip() + "…"
    return collapsed


def build_top_feed(
    photos_data: dict,
    records_by_id: dict[str, dict],
    site_stats: dict,
    image_dir: Path = IMAGE_DIR,
    max_photos: int = MAX_PHOTOS,
) -> dict:
    photos = photos_data.get("photos", {}) or {}
    sorted_photos = sorted(
        photos.values(),
        key=lambda p: p.get("created_at", ""),
        reverse=True,
    )

    entries = []
    for photo in sorted_photos:
        mid = str(photo.get("manhole_id", ""))
        # 画像 URL は焼き込まない: クライアントは manhole/image/{id}_latest.jpeg を
        # 組み立てるので、ローカルミラーが存在するものだけを採用する
        if not mid or not (image_dir / f"{mid}_latest.jpeg").exists():
            continue
        record = records_by_id.get(mid)
        if not record:
            continue
        pokemons = [
            p for p in record.get("pokemons", [])
            if p and _EXCLUDED_POKEMON_PATTERN not in p
        ]
        entries.append({
            "id": mid,
            "title": record.get("title", ""),
            "prefecture": record.get("prefecture", ""),
            "city": record.get("city", ""),
            "pokemons": pokemons,
            "display_name": photo.get("display_name") or None,
            "public_user_id": photo.get("public_user_id") or None,
            "comment": sanitize_comment(photo.get("comment")),
            "created_at": (photo.get("created_at") or "")[:10],
        })
        if len(entries) >= max_photos:
            break

    stats = {
        key: site_stats[key]
        for key in ("manholes", "manholes_with_photos", "posts")
        if isinstance(site_stats.get(key), int)
    }

    return {
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "stats": stats,
        "photos": entries,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--photos", type=Path, default=PHOTOS_JSON)
    parser.add_argument("--records", type=Path, default=NDJSON)
    parser.add_argument("--stats", type=Path, default=SITE_STATS_JSON)
    parser.add_argument("--image-dir", type=Path, default=IMAGE_DIR)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)

    feed = build_top_feed(
        load_json(args.photos),
        load_records_by_id(args.records),
        load_json(args.stats),
        image_dir=args.image_dir,
    )

    args.output.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(feed, ensure_ascii=False, separators=(",", ":"))
    args.output.write_text(payload + "\n", encoding="utf-8")
    print(
        f"[top-feed] wrote {args.output} "
        f"({len(payload):,} bytes, {len(feed['photos'])} photos, stats={feed['stats']})"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
