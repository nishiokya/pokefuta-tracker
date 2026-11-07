"""公式サイトに載っていない新しいポケふた（仮番号）を、図鑑の生成用データに合流させる。

公式 local.pokemon.jp が止まっている間に写真館のデザインふた投稿で来たポケふたを、
dataset/provisional_manholes.json（手動の台帳）に仮番号（9001〜）で載せる。
緯度経度・住所は投稿（docs/design_manholes.ndjson、写真の GPS から）を元にし、台帳には書かない。

公式の docs/pokefuta.ndjson は変えない。Pages のデプロイで公式＋仮の NDJSON を別に書き出し、
詳細・県・ポケモンのページと sitemap だけがそれを読む（全国の枚数・トップ・まとめは公式のみ）。

  python3 apps/scraper/provisional_manholes.py \
      --out build/pokefuta_with_provisional.ndjson --image-dir dataset/manhole/image

--image-dir を付けると投稿の写真を {仮番号}_latest.jpeg として落とす。写真館が投稿を
非公開にすると写真 API が 404 を返すので、その仮番号は出力から外す（台帳と取り込みデータが
古いままでも、次のデプロイで図鑑から消える）。
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Callable, Optional

try:
    from apps.scraper.display_names import build_place_label, municipality_label
except ModuleNotFoundError as exc:
    if exc.name != "apps":
        raise
    from display_names import build_place_label, municipality_label


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_LEDGER = ROOT / "dataset" / "provisional_manholes.json"
DEFAULT_OFFICIAL = ROOT / "docs" / "pokefuta.ndjson"
DEFAULT_DESIGN = ROOT / "docs" / "design_manholes.ndjson"
DEFAULT_OVERRIDES = ROOT / "dataset" / "design_manhole_overrides.json"

# 仮番号の範囲。公式は 1 から振っていて 2026-11 時点で 490 まで。
PROVISIONAL_MIN_ID = 9001
PHOTO_URL = "https://pokefuta.com/api/design-manholes/{uuid}/photo"
POST_URL = "https://pokefuta.com/design-manholes/{uuid}"
USER_AGENT = "pokefuta-tracker provisional-manholes (+https://github.com/nishiokya/pokefuta-tracker)"
_UUID = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$")


# 写真館に仮番号のページ・投稿先は無いので、写真の投稿はデザインふた投稿（新しいポケふた）へ向ける
PROVISIONAL_UPLOAD_URL = "https://pokefuta.com/design-manholes/new?kind=pokefuta"


class LedgerError(ValueError):
    """台帳の書き間違い。デプロイを止める。"""


def read_ndjson(path: Path) -> list[dict]:
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def load_ledger(path: Path) -> dict[str, dict]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    manholes = payload.get("manholes") if isinstance(payload, dict) else None
    if not isinstance(manholes, dict):
        raise LedgerError(f"{path}: manholes がありません")
    return manholes


def validate_ledger(
    ledger: dict[str, dict], official_ids: set[str], overrides: dict[str, dict]
) -> None:
    """番号・投稿ID の重複、公式との衝突、override の書き忘れを見る。"""
    errors: list[str] = []
    seen_uuids: dict[str, str] = {}
    for pid, entry in ledger.items():
        if not pid.isdigit() or int(pid) < PROVISIONAL_MIN_ID:
            errors.append(f"{pid}: 仮番号は {PROVISIONAL_MIN_ID} 以上の数字にする")
        if pid in official_ids:
            errors.append(f"{pid}: 公式の番号とぶつかっている")
        if not isinstance(entry, dict):
            errors.append(f"{pid}: 中身がオブジェクトでない")
            continue
        uuid = str(entry.get("design_manhole_id") or "")
        if not _UUID.match(uuid):
            errors.append(f"{pid}: design_manhole_id が投稿の UUID でない")
        elif uuid in seen_uuids:
            errors.append(f"{pid}: 投稿 {uuid} は {seen_uuids[uuid]} でも使っている")
        else:
            seen_uuids[uuid] = pid
            ref = (overrides.get(uuid) or {}).get("canonical_ref")
            if ref != f"pokefuta:{pid}":
                errors.append(
                    f"{pid}: design_manhole_overrides.json の {uuid} に canonical_ref \"pokefuta:{pid}\" が無い"
                )
        for key in ("prefecture", "city"):
            if not str(entry.get(key) or "").strip():
                errors.append(f"{pid}: {key} が空")
        pokemons = entry.get("pokemons")
        if not isinstance(pokemons, list) or not pokemons or not all(isinstance(p, str) and p for p in pokemons):
            errors.append(f"{pid}: pokemons はポケモン名の配列にする")
        official_id = entry.get("official_id")
        if official_id is not None and str(official_id) not in official_ids:
            errors.append(f"{pid}: official_id {official_id} が公式データに無い")
    if errors:
        raise LedgerError("provisional_manholes.json:\n  " + "\n  ".join(errors))


def build_records(ledger: dict[str, dict], design_records: list[dict]) -> list[dict]:
    """台帳と投稿から、pokefuta.ndjson と同じ形のレコードを作る。

    投稿が取り込みデータに無い・掲載中でないもの、公式に載って official_id が付いたものは出さない。
    """
    by_uuid = {
        str(row.get("source_id")): row
        for row in design_records
        if row.get("source") == "pokefuta.com" and row.get("status") == "active"
    }
    records: list[dict] = []
    for pid, entry in sorted(ledger.items(), key=lambda item: int(item[0])):
        if entry.get("official_id") is not None:
            continue
        uuid = entry["design_manhole_id"]
        post = by_uuid.get(uuid)
        if post is None:
            print(f"[provisional] {pid}: 投稿 {uuid} が掲載中の取り込みデータに無いので出さない", file=sys.stderr)
            continue
        try:
            lat, lng = float(post["lat"]), float(post["lng"])
        except (KeyError, TypeError, ValueError):
            print(f"[provisional] {pid}: 投稿 {uuid} に緯度経度が無いので出さない", file=sys.stderr)
            continue
        prefecture = entry["prefecture"].strip()
        city = entry["city"].strip()
        record: dict[str, Any] = {
            "id": pid,
            "prefecture": prefecture,
            "city": city,
            "address": str(post.get("address") or "").strip(),
            "building": str(entry.get("building") or "").strip(),
            "lat": lat,
            "lng": lng,
            "pokemons": list(entry["pokemons"]),
            "installed": True,
            "status": "active",
            "detail_url": "",
            "city_url": "",
            "prefecture_site_url": "",
            "is_prefecture_site": False,
            "tags": [],
            "titles": [],
            "added_at": post.get("created_at") or "",
            "first_seen": post.get("created_at") or "",
            "last_updated": post.get("last_updated") or "",
            "provisional": True,
            "provisional_post_url": POST_URL.format(uuid=uuid),
            "provisional_source_url": str(entry.get("source_url") or "").strip(),
            "design_manhole_id": uuid,
        }
        record["title"] = f"{prefecture}/{municipality_label(record)}"
        record["place_label"] = build_place_label(record)
        records.append(record)
    return records


def fetch_photo(uuid: str, timeout: float = 30.0) -> Optional[bytes]:
    """投稿の写真（原寸）。非公開・削除なら None。

    写真館が落ちているときも None にして、その仮番号だけ外す（図鑑全体のデプロイは止めない）。
    """
    request = urllib.request.Request(PHOTO_URL.format(uuid=uuid), headers={"User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return response.read()
    except urllib.error.HTTPError as exc:
        if exc.code not in (403, 404, 410):
            print(f"[provisional] WARN 投稿 {uuid} の写真が取れない（HTTP {exc.code}）", file=sys.stderr)
        return None
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        print(f"[provisional] WARN 投稿 {uuid} の写真が取れない（{exc}）", file=sys.stderr)
        return None


def attach_photos(
    records: list[dict], image_dir: Path, fetch: Callable[[str], Optional[bytes]] = fetch_photo
) -> list[dict]:
    """写真を {仮番号}_latest.jpeg に置く。写真が取れない（非公開になった）仮番号は外す。"""
    kept: list[dict] = []
    image_dir.mkdir(parents=True, exist_ok=True)
    for record in records:
        path = image_dir / f"{record['id']}_latest.jpeg"
        data = fetch(record["design_manhole_id"])
        if not data:
            path.unlink(missing_ok=True)
            print(f"[provisional] {record['id']}: 投稿の写真が公開されていないので出さない", file=sys.stderr)
            continue
        path.write_bytes(data)
        kept.append(record)
    return kept


def merge_photos(payload: dict, records: list[dict]) -> dict:
    """latest-manhole-photos.json に仮番号の写真の行を足す（県ページなどが「写真あり」と数えるため）。

    画像そのものは attach_photos() が置いた {仮番号}_latest.jpeg を各ページが読む。投稿者の名前は
    取り込みデータに無いので出さない（詳細ページの説明から投稿へリンクする）。
    """
    photos = dict(payload.get("photos") or {})
    for record in records:
        photos[record["id"]] = {
            "manhole_id": int(record["id"]),
            "photo_id": None,
            "created_at": record.get("added_at") or None,
            "shot_at": None,
            "comment": None,
            "display_name": None,
            "provisional": True,
        }
    return {**payload, "photos": photos, "count": len(photos)}


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--ledger", type=Path, default=DEFAULT_LEDGER)
    parser.add_argument("--official", type=Path, default=DEFAULT_OFFICIAL)
    parser.add_argument("--design", type=Path, default=DEFAULT_DESIGN)
    parser.add_argument("--overrides", type=Path, default=DEFAULT_OVERRIDES)
    parser.add_argument("--out", type=Path, help="公式＋仮の NDJSON の書き出し先（省略時は検査だけ）")
    parser.add_argument("--image-dir", type=Path, help="投稿の写真を落とすフォルダ")
    parser.add_argument("--photos-in", type=Path, help="latest-manhole-photos.json（--photos-out と一緒に）")
    parser.add_argument("--photos-out", type=Path, help="仮番号の写真の行を足した写真 JSON の書き出し先")
    args = parser.parse_args(argv)

    official_lines = [line for line in args.official.read_text(encoding="utf-8").splitlines() if line.strip()]
    official_ids = {str(json.loads(line).get("id", "")).strip() for line in official_lines}
    ledger = load_ledger(args.ledger)
    overrides = json.loads(args.overrides.read_text(encoding="utf-8")) if args.overrides.exists() else {}
    validate_ledger(ledger, official_ids, overrides)

    records = build_records(ledger, read_ndjson(args.design))
    if args.image_dir:
        records = attach_photos(records, args.image_dir)
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(
            "".join(line + "\n" for line in official_lines)
            + "".join(json.dumps(record, ensure_ascii=False) + "\n" for record in records),
            encoding="utf-8",
        )
    if args.photos_in and args.photos_out:
        payload = json.loads(args.photos_in.read_text(encoding="utf-8"))
        args.photos_out.parent.mkdir(parents=True, exist_ok=True)
        args.photos_out.write_text(
            json.dumps(merge_photos(payload, records if args.image_dir else []), ensure_ascii=False),
            encoding="utf-8",
        )
    print(f"[provisional] 台帳 {len(ledger)} 件のうち {len(records)} 件を出す: {[r['id'] for r in records]}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
