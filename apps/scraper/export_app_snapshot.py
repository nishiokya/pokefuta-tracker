#!/usr/bin/env python3
"""Supabase から公開スナップショット JSON を書き出す日次エクスポート。

pokefuta.com アプリの /api/manholes・/api/site-stats が毎リクエストで
Supabase を読む構成をやめ、GitHub Pages (data.pokefuta.com) 配信の
静的 JSON へ置き換えるためのデータ源を生成する。

生成物:
  docs/api/manholes.json   … manhole 全件 + 写真有無（匿名ユーザー向け形状）
  docs/api/site-stats.json … /api/site-stats と同形状のサイト統計
  docs/api/regulars.json   … 投稿者に付ける称号（🌱 ROOKIE〜🏆 LEGEND の5段階）の判定（公開ID → 段階）

実行元: .github/workflows/import-manhole-photos.yml（日次）

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

sys.path.insert(0, str(Path(__file__).resolve().parent))
from display_names import attach_place_labels, compose_display_name  # noqa: E402

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


MANHOLE_TITLES_JSON = ROOT / "dataset" / "manhole_titles.json"

# 手動マスタから重ねる、表示名の組み立てに効くフィールドだけ。
# address は address_norm -> address_raw の順で採用する（update_pokefuta.py の
# apply_title_metadata と同じ優先順位）。
_OVERLAY_FIELDS = ("building", "prefecture", "city")


def overlay_manual_metadata(entries: list[dict],
                            master_path: Path = MANHOLE_TITLES_JSON) -> int:
    """dataset/manhole_titles.json の手動修正を entry に重ねる。

    Supabase の manhole テーブルはこのリポジトリからは読むだけで、書き込む口が無い。
    そのため手動マスタの訂正（例: id=3 の building「ふれあいプラザなのはな館敷」→
    「ふれあいプラザなのはな館」）が Supabase 側へ届かない。重ねずに name を
    組み立てると、誤記がアプリの主表示に昇格してしまう。

    NDJSON 側と揃うのは表示名に効くフィールドだけで、住所そのものの同期は別課題。
    上書きした件数を返す。
    """
    try:
        master = json.loads(master_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        print(f"WARN: {master_path} を読めないため手動マスタを重ねません: {exc}")
        return 0

    manholes = master.get("manholes") or {}
    updated = 0
    for entry in entries:
        curated = manholes.get(str(entry.get("id")))
        if not isinstance(curated, dict):
            continue
        touched = False
        for field in _OVERLAY_FIELDS:
            value = curated.get(field)
            if isinstance(value, str) and value.strip() and entry.get(field) != value:
                entry[field] = value
                touched = True
        address = curated.get("address_norm") or curated.get("address_raw")
        if isinstance(address, str) and address.strip() and entry.get("address") != address:
            entry["address"] = address
            touched = True
        # city は municipality 由来なので両方を揃える
        if entry.get("city"):
            entry["municipality"] = entry["city"]
        if touched:
            updated += 1
    return updated


def apply_place_labels(entries: list[dict]) -> int:
    """entry["name"] を同一自治体内で区別できる表示名にする。

    Supabase の `title` は local.pokemon.jp の見出しそのままで
    「鹿児島県/指宿市」のように自治体単位でしか区別できず、そのまま name に
    入れるとアプリの一覧で指宿市9枚が全部同じ名前になる。
    pokefuta.ndjson 側と同じ display_names の規則で場所名を組み立てる
    （必要な address / building / municipality / pokemons は取得済み）。

    Supabase 側は status ではなく is_active を持つので判定を差し替える。
    place_label / place_ambiguous も JSON に載せるため、クライアント側で
    独自に組み立てたい場合はそちらを読めばよい。
    """
    # Supabase には手動マスタの訂正が届かないので、名前を組み立てる前に重ねる
    overlay_manual_metadata(entries)
    # is_active は真値のときだけ active とみなす。`is not False` にすると
    # DB の NULL や移行データの欠損まで active 扱いになり、本来一意なレコードに
    # place_label が付いたり place_ambiguous が立ったりする
    attached = attach_place_labels(
        entries,
        active_predicate=lambda e: e.get("is_active") is True,
    )
    for entry in entries:
        # KML と同じく、アプリの一覧はポケモン名を別枠で見せられるとは限らないので
        # 場所で区別できないものにだけポケモン名を添える
        entry["name"] = compose_display_name(entry) or "ポケふた"
    return attached


def build_manholes() -> dict:
    manholes = fetch_all(
        "manhole",
        {"select": ",".join(MANHOLE_COLUMNS), "order": "id.desc"},
    )
    photo_rows = fetch_all(
        "photo", {
            "select": "manhole_id,visit!inner(is_public)",
            "order": "id.asc",
            "manhole_id": "not.is.null",
            "visit.is_public": "eq.true",
            "is_landscape": "eq.false",
        }
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
        entry["city"] = row.get("municipality") or ""
        entry["latitude"] = lat
        entry["longitude"] = lng
        entry["is_visited"] = False
        entry["last_visit"] = None
        entry["photo_count"] = 1 if row["id"] in with_photo_ids else 0
        entries.append(entry)

    apply_place_labels(entries)

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

    # 古い get_site_stats は風景・非公開写真も充足に数えるため、同じ公開条件で算出。
    photo_rows = fetch_all(
        "photo", {
            "select": "manhole_id,visit!inner(is_public)",
            "order": "id.asc",
            "manhole_id": "not.is.null",
            "visit.is_public": "eq.true",
            "is_landscape": "eq.false",
        }
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


# --- 称号（docs/api/regulars.json） ---
#
# 投稿者名に付ける称号。公開で訪問したポケふたの枚数（manhole_id の重複なし、これまでの累計）で
# 5段階に分ける。線は写真館の /badges に全部書いてある（目標として見せる）。
# 写真館の src/lib/regular-badges.ts の REGULAR_TIER_MIN_MANHOLES と同じ値にする。
#
# 2026-10-24 に「直近の何週に投稿があったか（線は非公開）」と「初投稿から30日の新人」から置き換えた。
# 段階の名前（JSON の値）は写真館との互換のため据え置き: regular=EXPLORER、crown=MASTER。
#
# アプリが毎リクエスト集計すると Amplify の SSR 実行時間が増えるので、ここで日次に
# 焼いて data.pokefuta.com から配る。
# 運営者のアカウント（app_user.id）。自分のサイトで自分にバッジを出さない
REGULAR_EXCLUDED_PUBLIC_IDS = frozenset({
    "08c2bb09-8aa0-44f7-8287-7b332a589f33",
})

# 高い段から順に。最初に届いた段を付ける
TIER_MIN_MANHOLES: tuple[tuple[str, int], ...] = (
    ("legend", 100),
    ("crown", 50),
    ("ranger", 30),
    ("regular", 10),
    ("rookie", 1),
)
LEGEND_MIN_MANHOLES = dict(TIER_MIN_MANHOLES)["legend"]


def tier_for_count(count: int) -> str | None:
    for tier, minimum in TIER_MIN_MANHOLES:
        if count >= minimum:
            return tier
    return None


def compute_tiers(visits: list[dict], public_id_by_auth: dict[str, str]) -> dict[str, str]:
    """公開の訪問のポケふた（manhole_id の重複なし）の枚数から、公開ID → 段階 を返す。

    visits は公開の {user_id, manhole_id}。期間では絞らない（これまでの累計）。
    写真の有無は問わない（公開スタンプ帳の訪問数と同じ数え方）。
    """
    manholes: dict[str, set] = {}
    for v in visits:
        public_id = public_id_by_auth.get(v.get("user_id") or "")
        if not public_id or public_id in REGULAR_EXCLUDED_PUBLIC_IDS or v.get("manhole_id") is None:
            continue
        manholes.setdefault(public_id, set()).add(v["manhole_id"])
    tiers = {public_id: tier_for_count(len(ids)) for public_id, ids in manholes.items()}
    return dict(sorted((k, v) for k, v in tiers.items() if v))


# LEGEND の人は写真館のトップ（「LEGEND を目指そう」のカード）と /badges に名前を出す。
# 表示名が空の人は写真館の表示と同じ「トレーナー」にする
FALLBACK_DISPLAY_NAME = "トレーナー"


def legend_entries(tiers: dict[str, str], users: list[dict]) -> list[dict]:
    """LEGEND の公開ID と表示名。順位にしないため、枚数は出さず名前順に並べる。

    公開 JSON に出してよい利用者の情報は公開ID と表示名まで（CLAUDE.md）。
    LEGEND の人は公開の訪問を持つので、get_public_display_names() で名前が出る条件にも当たる。
    """
    name_by_id = {u["id"]: (u.get("display_name") or "").strip() for u in users if u.get("id")}
    entries = [
        {"id": public_id, "name": name_by_id.get(public_id) or FALLBACK_DISPLAY_NAME}
        for public_id, tier in tiers.items()
        if tier == "legend"
    ]
    return sorted(entries, key=lambda e: (e["name"], e["id"]))


def build_regulars() -> dict:
    now = datetime.now(timezone.utc)
    visits = fetch_all(
        "visit", {"select": "user_id,manhole_id", "is_public": "eq.true", "order": "id.asc"}
    )
    # 公開 JSON に auth UID を出さないため、ここで公開ID（app_user.id）に置き換える
    users = fetch_all("app_user", {"select": "id,auth_uid,display_name", "order": "id.asc"})
    public_id_by_auth = {u["auth_uid"]: u["id"] for u in users if u.get("auth_uid")}
    tiers = compute_tiers(visits, public_id_by_auth)
    return {
        "success": True,
        "generated_at": now.isoformat(timespec="seconds"),
        "users": tiers,
        "legends": legend_entries(tiers, users),
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

    # バッジは飾りなので、取れなくても蓋一覧・統計の更新を止めない（前日の regulars.json が残る）
    try:
        regulars = build_regulars()
    except requests.RequestException as exc:
        print(f"::warning::docs/api/regulars.json を更新できませんでした: {exc}", file=sys.stderr)
        return
    (OUT_DIR / "regulars.json").write_text(
        json.dumps(regulars, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
        encoding="utf-8",
    )
    tiers = list(regulars["users"].values())
    print(
        "docs/api/regulars.json: "
        + " ".join(f"{tier}={tiers.count(tier)}" for tier, _ in TIER_MIN_MANHOLES)
    )


if __name__ == "__main__":
    main()
