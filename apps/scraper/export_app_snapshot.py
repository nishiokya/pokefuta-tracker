#!/usr/bin/env python3
"""Supabase から公開スナップショット JSON を書き出す日次エクスポート。

pokefuta.com アプリの /api/manholes・/api/site-stats が毎リクエストで
Supabase を読む構成をやめ、GitHub Pages (data.pokefuta.com) 配信の
静的 JSON へ置き換えるためのデータ源を生成する。

生成物:
  docs/api/manholes.json   … manhole 全件 + 写真有無（匿名ユーザー向け形状）
  docs/api/site-stats.json … /api/site-stats と同形状のサイト統計

実行元: .github/workflows/bake-app-data.yml（日次）

環境変数:
  SUPABASE_URL              例 https://xxxx.supabase.co
  SUPABASE_SERVICE_ROLE_KEY service role キー
"""

from __future__ import annotations

import json
import os
import struct
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parent.parent.parent
OUT_DIR = ROOT / "docs" / "api"
PAGE_SIZE = 1000
TIMEOUT = 30

# 公開してよいカラムの allowlist。将来 manhole テーブルに内部用カラムが
# 増えても、ここに足さない限り公開 JSON には出ない。
MANHOLE_COLUMNS = [
    "id",
    "title",
    "prefecture",
    "prefecture_id",
    "prefecture_code",
    "municipality",
    "address",
    "address_norm",
    "building",
    "location",
    "pokemons",
    "detail_url",
    "prefecture_site_url",
    "official_url",
    "titles",
    "hashtags",
    "title_tags",
    "region",
    "is_active",
    "last_verified_at",
    "data_source",
    "source_last_checked",
    "created_at",
]

# 遅延初期化（import 時に env を要求しない — テスト可能にするため）
SUPABASE_URL = ""
HEADERS: dict[str, str] = {}


def _env(name: str) -> str:
    value = os.environ.get(name, "").strip()
    if not value:
        print(f"ERROR: environment variable {name} is required", file=sys.stderr)
        sys.exit(1)
    return value


def init_config() -> None:
    global SUPABASE_URL, HEADERS
    SUPABASE_URL = _env("SUPABASE_URL").rstrip("/")
    service_key = _env("SUPABASE_SERVICE_ROLE_KEY")
    HEADERS = {
        "apikey": service_key,
        "Authorization": f"Bearer {service_key}",
    }


def fetch_all(table: str, params: dict) -> list[dict]:
    """PostgREST から全件をページングで取得する。"""
    rows: list[dict] = []
    offset = 0
    while True:
        headers = dict(HEADERS)
        headers["Range-Unit"] = "items"
        headers["Range"] = f"{offset}-{offset + PAGE_SIZE - 1}"
        res = requests.get(
            f"{SUPABASE_URL}/rest/v1/{table}",
            params=params,
            headers=headers,
            timeout=TIMEOUT,
        )
        res.raise_for_status()
        chunk = res.json()
        rows.extend(chunk)
        if len(chunk) < PAGE_SIZE:
            return rows
        offset += PAGE_SIZE


def fetch_count(table: str, params: dict) -> int:
    """行数だけを Content-Range ヘッダから取得する。"""
    headers = dict(HEADERS)
    headers["Prefer"] = "count=exact"
    headers["Range-Unit"] = "items"
    headers["Range"] = "0-0"
    res = requests.get(
        f"{SUPABASE_URL}/rest/v1/{table}",
        params=params,
        headers=headers,
        timeout=TIMEOUT,
    )
    if res.status_code not in (200, 206):
        res.raise_for_status()
    content_range = res.headers.get("Content-Range", "")
    total = content_range.rsplit("/", 1)[-1]
    return int(total) if total.isdigit() else 0


def fetch_first(table: str, column: str, order: str) -> str | None:
    rows = fetch_all(table, {"select": column, "order": order, "limit": "1"})
    return rows[0][column] if rows else None


def parse_wkb_point(wkb_hex: str) -> tuple[float, float] | None:
    """PostGIS の WKB(EWKB) hex 文字列から (lat, lng) を取り出す。"""
    try:
        raw = bytes.fromhex(wkb_hex)
        little = raw[0] == 1
        endian = "<" if little else ">"
        (geom_type,) = struct.unpack_from(f"{endian}I", raw, 1)
        offset = 5
        if geom_type & 0x20000000:  # SRID フラグ
            offset += 4
        if geom_type & 0xFF != 1:  # POINT 以外
            return None
        lng, lat = struct.unpack_from(f"{endian}dd", raw, offset)
        if not (-90 <= lat <= 90 and -180 <= lng <= 180):
            return None
        return lat, lng
    except (ValueError, struct.error, IndexError):
        return None


def build_manholes() -> dict:
    manholes = fetch_all(
        "manhole",
        {"select": ",".join(MANHOLE_COLUMNS), "order": "id.desc"},
    )
    photo_rows = fetch_all(
        "photo", {"select": "manhole_id", "manhole_id": "not.is.null"}
    )
    with_photo_ids = {row["manhole_id"] for row in photo_rows}

    entries = []
    skipped = 0
    for row in manholes:
        coords = parse_wkb_point(row.get("location") or "")
        if coords is None:
            skipped += 1
            continue
        lat, lng = coords
        entry = dict(row)
        entry["name"] = row.get("title") or "ポケふた"
        entry["city"] = row.get("municipality") or ""
        entry["latitude"] = lat
        entry["longitude"] = lng
        entry["is_visited"] = False
        entry["last_visit"] = None
        entry["photo_count"] = 1 if row["id"] in with_photo_ids else 0
        entries.append(entry)

    if skipped:
        print(f"WARN: skipped {skipped} manholes without parsable location")

    return {
        "success": True,
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        # total は DB 行数（旧 /api/manholes の total と同義）。座標を解釈
        # できない行は manholes リストから除外されるため、その差分は
        # skipped_without_location で明示する。
        "total": len(manholes),
        "with_photos": len(with_photo_ids),
        "skipped_without_location": skipped,
        "manholes": entries,
    }


def fetch_auth_user_stats() -> tuple[int | None, int | None]:
    """auth.users の総数と直近7日ログイン数。"""
    ago_7d = datetime.now(timezone.utc) - timedelta(days=7)
    total: int | None = None
    active = 0
    page = 1
    while True:
        res = requests.get(
            f"{SUPABASE_URL}/auth/v1/admin/users",
            params={"per_page": PAGE_SIZE, "page": page},
            headers=HEADERS,
            timeout=TIMEOUT,
        )
        if not res.ok:
            return None, None
        if page == 1:
            header = res.headers.get("x-total-count")
            total = int(header) if header and header.isdigit() else None
        users = res.json().get("users", [])
        for user in users:
            signed_in = user.get("last_sign_in_at")
            if signed_in and datetime.fromisoformat(
                signed_in.replace("Z", "+00:00")
            ) >= ago_7d:
                active += 1
        if len(users) < PAGE_SIZE:
            return total, active
        page += 1


def build_site_stats() -> dict:
    res = requests.post(
        f"{SUPABASE_URL}/rest/v1/rpc/get_site_stats",
        headers={**HEADERS, "Content-Type": "application/json"},
        json={},
        timeout=TIMEOUT,
    )
    res.raise_for_status()
    data = res.json()
    row = data[0] if isinstance(data, list) else data

    def count_of(key: str) -> int:
        value = row.get(key) if row else None
        return int(value) if value is not None else 0

    now = datetime.now(timezone.utc)
    ago_7d = (now - timedelta(days=7)).isoformat(timespec="seconds")
    ago_30d = (now - timedelta(days=30)).isoformat(timespec="seconds")

    manholes_with_photos = count_of("total_manholes_with_photos")
    if row is None or row.get("total_manholes_with_photos") is None:
        photo_rows = fetch_all(
            "photo", {"select": "manhole_id", "manhole_id": "not.is.null"}
        )
        manholes_with_photos = len({r["manhole_id"] for r in photo_rows})

    auth_users, active_users_7d = fetch_auth_user_stats()

    return {
        "success": True,
        "generated_at": now.isoformat(timespec="seconds"),
        "users": count_of("total_users"),
        "posts": count_of("total_posts"),
        "manholes": count_of("total_manhole"),
        "manholes_with_photos": manholes_with_photos,
        "latest_photo_at": fetch_first("photo", "created_at", "created_at.desc"),
        "latest_user_at": fetch_first("app_user", "created_at", "created_at.desc"),
        "latest_visit_at": fetch_first("visit", "created_at", "created_at.desc"),
        "posts_last_7d": fetch_count("photo", {"created_at": f"gte.{ago_7d}"}),
        "posts_last_30d": fetch_count("photo", {"created_at": f"gte.{ago_30d}"}),
        "auth_users": auth_users,
        "active_users_7d": active_users_7d,
        "manhole_comments": fetch_count("manhole_comment", {}),
        "public_posts": fetch_count(
            "photo",
            {"select": "id,visit:visit_id!inner(is_public)", "visit.is_public": "eq.true"},
        ),
        "private_posts": fetch_count(
            "photo",
            {"select": "id,visit:visit_id!inner(is_public)", "visit.is_public": "eq.false"},
        ),
        "source": "baked",
    }


def write_manholes_json(payload: dict, path: Path) -> None:
    """1マンホール1行で書き出し、git diff を読みやすくする。payload は変更しない。"""
    head_obj = {k: v for k, v in payload.items() if k != "manholes"}
    head = json.dumps(head_obj, ensure_ascii=False, sort_keys=True)
    lines = ",\n".join(
        json.dumps(m, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        for m in payload["manholes"]
    )
    path.write_text(
        head[:-1] + ',"manholes":[\n' + lines + "\n]}\n", encoding="utf-8"
    )


def main() -> None:
    init_config()
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    manholes_payload = build_manholes()
    write_manholes_json(manholes_payload, OUT_DIR / "manholes.json")
    print(
        f"docs/api/manholes.json: {manholes_payload['total']} manholes "
        f"({manholes_payload['with_photos']} with photos)"
    )

    stats = build_site_stats()
    (OUT_DIR / "site-stats.json").write_text(
        json.dumps(stats, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
        encoding="utf-8",
    )
    print(
        "docs/api/site-stats.json: "
        f"users={stats['users']} posts={stats['posts']} manholes={stats['manholes']}"
    )


if __name__ == "__main__":
    main()
