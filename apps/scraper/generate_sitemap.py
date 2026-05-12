#!/usr/bin/env python3
"""Generate the public sitemap for the Pokefuta map."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Optional
from urllib.parse import quote
from xml.sax.saxutils import escape


BASE_URL = "https://data.pokefuta.com/"

PREFECTURES = [
    "北海道",
    "青森県",
    "岩手県",
    "宮城県",
    "秋田県",
    "山形県",
    "福島県",
    "茨城県",
    "栃木県",
    "群馬県",
    "埼玉県",
    "千葉県",
    "東京都",
    "神奈川県",
    "新潟県",
    "富山県",
    "石川県",
    "福井県",
    "山梨県",
    "長野県",
    "岐阜県",
    "静岡県",
    "愛知県",
    "三重県",
    "滋賀県",
    "京都府",
    "大阪府",
    "兵庫県",
    "奈良県",
    "和歌山県",
    "鳥取県",
    "島根県",
    "岡山県",
    "広島県",
    "山口県",
    "徳島県",
    "香川県",
    "愛媛県",
    "高知県",
    "福岡県",
    "佐賀県",
    "長崎県",
    "熊本県",
    "大分県",
    "宮崎県",
    "鹿児島県",
    "沖縄県",
]


def read_known_manhole_ids(path: Path) -> Optional[set[str]]:
    ids: set[str] = set()
    if not path.exists():
        return None

    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            record = json.loads(line)
        except json.JSONDecodeError:
            continue
        manhole_id = str(record.get("id") or "").strip()
        if manhole_id:
            ids.add(manhole_id)
    return ids


def read_photo_manhole_ids(image_dir: Path, known_ids: Optional[set[str]]) -> list[str]:
    if not image_dir.exists():
        return []

    ids = []
    for image_path in image_dir.glob("*_latest.jpeg"):
        manhole_id = image_path.name.removesuffix("_latest.jpeg").strip()
        if manhole_id and (known_ids is None or manhole_id in known_ids):
            ids.append(manhole_id)
    return sorted(set(ids), key=lambda value: (len(value), value))


def url_entry(loc: str, changefreq: str, priority: str) -> str:
    return "\n".join(
        [
            "  <url>",
            f"    <loc>{escape(loc)}</loc>",
            f"    <changefreq>{changefreq}</changefreq>",
            f"    <priority>{priority}</priority>",
            "  </url>",
        ]
    )


def build_sitemap(photo_ids: list[str]) -> str:
    entries = [
        url_entry(BASE_URL, "daily", "1.0"),
        url_entry(f"{BASE_URL}nearby.html", "weekly", "0.6"),
        url_entry(f"{BASE_URL}gmanhole_map.html", "weekly", "0.6"),
    ]

    for prefecture in PREFECTURES:
        entries.append(
            url_entry(f"{BASE_URL}?pref={quote(prefecture)}", "weekly", "0.7")
        )

    for manhole_id in photo_ids:
        entries.append(
            url_entry(f"{BASE_URL}?manhole={quote(manhole_id)}", "weekly", "0.8")
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
    parser.add_argument("--image-dir", default="dataset/manhole/image")
    parser.add_argument("--output", default="apps/web/sitemap.xml")
    args = parser.parse_args()

    known_ids = read_known_manhole_ids(Path(args.data))
    photo_ids = read_photo_manhole_ids(Path(args.image_dir), known_ids)
    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(build_sitemap(photo_ids), encoding="utf-8")
    print(f"wrote {output_path} with {len(photo_ids)} manhole photo URLs")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
