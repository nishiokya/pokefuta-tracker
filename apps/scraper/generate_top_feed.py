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

sys.path.insert(0, str(Path(__file__).parent))
from export_latest_manhole_photos import DEFAULT_GALLERY_LIMIT  # noqa: E402
from photo_caption import to_jst_date  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
PHOTOS_JSON = ROOT / "docs" / "latest-manhole-photos.json"
NDJSON = ROOT / "docs" / "pokefuta.ndjson"
SITE_STATS_JSON = ROOT / "docs" / "api" / "site-stats.json"
IMAGE_DIR = ROOT / "dataset" / "manhole" / "image"

MAX_PHOTOS = 12
COMMENT_MAX_LEN = 80

# 称号バッジに採用する最低 priority。「ここだけ」(90) / 離島 (95) / 最北端等 (100) /
# レア (70) / 市内唯一 (60) は拾い、観光・駅前などの汎用タグ (36 帯) は拾わない
HERO_BADGE_MIN_PRIORITY = 60

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


def hero_badge(record: dict) -> dict | None:
    """ndjson の titles[0]（priority 降順格納済み）から称号バッジを作る。

    label には hashtag から '#' を落とした短縮形を使う（titles の label は
    「ガラルダルマッカは全国でここだけ」のように長く、ヒーローのバッジ枠に
    収まらないため）。希少称号（HERO_BADGE_MIN_PRIORITY 以上）のみ採用。
    """
    titles = record.get("titles") or []
    if not titles or not isinstance(titles[0], dict):
        return None
    top = titles[0]
    priority = top.get("priority")
    hashtag = top.get("hashtag")
    if not isinstance(priority, (int, float)) or priority < HERO_BADGE_MIN_PRIORITY:
        return None
    if not isinstance(hashtag, str):
        return None
    label = hashtag.lstrip("#").strip()
    if not label:
        return None
    return {
        "emoji": top.get("emoji") or "",
        "label": label,
        "priority": int(priority),
    }


def photo_count_for(photo: dict) -> int:
    """その地点の既知の写真枚数。

    gallery は代表写真（ヒーロー）自身を先頭に含む public 写真のリスト
    （export_latest_manhole_photos.py の select_gallery_photos は全写真から選ぶ）。
    export 側で gallery_limit 件にキャップされるため、この値は実際の枚数の
    下限でしかない（上限到達かどうかは at_cap を参照）。
    """
    gallery = photo.get("gallery")
    if isinstance(gallery, list) and gallery:
        return len(gallery)
    return 1


def build_top_feed(
    photos_data: dict,
    records_by_id: dict[str, dict],
    site_stats: dict,
    image_dir: Path = IMAGE_DIR,
    max_photos: int = MAX_PHOTOS,
    gallery_limit: int = DEFAULT_GALLERY_LIMIT,
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
        # UTC のまま [:10] すると UTC 15:00 以降の投稿が1日前にずれるため
        # JST に変換してから日付化する（トップの formatFeedDate は JST 日付を前提）
        created_jst = to_jst_date(photo.get("created_at"))
        entry = {
            "id": mid,
            "title": record.get("title", ""),
            "prefecture": record.get("prefecture", ""),
            "city": record.get("city", ""),
            "pokemons": pokemons,
            "display_name": photo.get("display_name") or None,
            "public_user_id": photo.get("public_user_id") or None,
            "comment": sanitize_comment(photo.get("comment")),
            "created_at": created_jst.isoformat() if created_jst else "",
        }
        # badge / photo_count は任意フィールド: 値があるときだけキーを足す
        # （既存フィールドと違い null を焼き込まず、クライアントは in 判定で読む）
        badge = hero_badge(record)
        if badge:
            entry["badge"] = badge
        photo_count = photo_count_for(photo)
        if photo_count >= 2:
            entry["photo_count"] = photo_count
            # gallery が export のキャップに達している = 実際はこれ以上ある可能性がある。
            # キャップ値をクライアントに焼き込ませないためフラグで渡す（'📷5+' の判定用）
            if photo_count >= gallery_limit:
                entry["photo_count_at_cap"] = True
        entries.append(entry)
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
