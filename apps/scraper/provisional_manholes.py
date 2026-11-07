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
import http.client
import io
import json
import re
import sys
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Callable, Optional

try:
    from apps.scraper.display_names import build_place_label, municipality_label
    from apps.scraper.prefectures import PREFECTURE_ORDER, PREFECTURE_SLUGS
except ModuleNotFoundError as exc:
    if exc.name != "apps":
        raise
    from display_names import build_place_label, municipality_label
    from prefectures import PREFECTURE_ORDER, PREFECTURE_SLUGS


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_LEDGER = ROOT / "dataset" / "provisional_manholes.json"
DEFAULT_OFFICIAL = ROOT / "docs" / "pokefuta.ndjson"
DEFAULT_DESIGN = ROOT / "docs" / "design_manholes.ndjson"
DEFAULT_OVERRIDES = ROOT / "dataset" / "design_manhole_overrides.json"
DEFAULT_WANTED = ROOT / "dataset" / "provisional_wanted.json"

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


class PhotoGone(Exception):
    """写真 API が 403/404/410 を返した（投稿が非公開・削除になった）。"""


def fetch_photo(uuid: str, timeout: float = 30.0) -> Optional[bytes]:
    """投稿の写真（原寸）。非公開・削除なら PhotoGone、写真館が落ちている・途中で切れたなら None。

    None のときも図鑑全体のデプロイは止めない（attach_photos() がその仮番号を写真なしで出す）。
    """
    request = urllib.request.Request(PHOTO_URL.format(uuid=uuid), headers={"User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return response.read()
    except urllib.error.HTTPError as exc:
        if exc.code in (403, 404, 410):
            raise PhotoGone(uuid) from exc
        print(f"[provisional] WARN 投稿 {uuid} の写真が取れない（HTTP {exc.code}）", file=sys.stderr)
        return None
    except (urllib.error.URLError, http.client.HTTPException, TimeoutError, OSError) as exc:
        print(f"[provisional] WARN 投稿 {uuid} の写真が取れない（{exc}）", file=sys.stderr)
        return None


def strip_metadata(data: bytes) -> Optional[bytes]:
    """向きを直し、EXIF（位置情報・端末情報）を持たない JPEG に描き直す。画像として読めなければ None。

    写真館は投稿時に位置情報を消しているが、公開リポジトリの配信物に原本をそのまま置かないよう
    既存の写真取り込み（import_latest_manhole_photos.py）と同じく再エンコードする。
    """
    from PIL import Image, ImageOps, UnidentifiedImageError

    try:
        with Image.open(io.BytesIO(data)) as image:
            image = ImageOps.exif_transpose(image).convert("RGB")
            out = io.BytesIO()
            image.save(out, "JPEG", quality=88, optimize=True, progressive=True)
            return out.getvalue()
    except (UnidentifiedImageError, OSError, ValueError) as exc:
        print(f"[provisional] WARN 写真を画像として読めない（{exc}）", file=sys.stderr)
        return None


def attach_photos(
    records: list[dict], image_dir: Path, fetch: Callable[[str], Optional[bytes]] = fetch_photo
) -> tuple[list[dict], list[dict]]:
    """写真を {仮番号}_latest.jpeg に置き、(出す仮番号, そのうち写真を置けた仮番号) を返す。

    投稿が非公開・削除になった（PhotoGone）仮番号は外す。写真館が一時的に落ちている・画像が読めない
    ときは仮番号を残し、写真なしで出す（一時的な障害でページを消さない）。
    """
    kept: list[dict] = []
    with_photo: list[dict] = []
    image_dir.mkdir(parents=True, exist_ok=True)
    for record in records:
        path = image_dir / f"{record['id']}_latest.jpeg"
        try:
            data = fetch(record["design_manhole_id"])
        except PhotoGone:
            path.unlink(missing_ok=True)
            print(f"[provisional] {record['id']}: 投稿が公開されていないので出さない", file=sys.stderr)
            continue
        kept.append(record)
        data = strip_metadata(data) if data else None
        if data:
            path.write_bytes(data)
            with_photo.append(record)
        else:
            # 前回の写真が手元に残っていても使わない（今の投稿の写真か確かめられない）
            path.unlink(missing_ok=True)
            print(f"[provisional] WARN {record['id']}: 写真なしで出す", file=sys.stderr)
    return kept, with_photo


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


def load_wanted(path: Path = DEFAULT_WANTED) -> dict[str, dict]:
    """場所を調べているポケふた（dataset/provisional_wanted.json）。ファイルが無ければ空。"""
    if not path.exists():
        return {}
    payload = json.loads(path.read_text(encoding="utf-8"))
    prefectures = payload.get("prefectures") if isinstance(payload, dict) else None
    return prefectures if isinstance(prefectures, dict) else {}


def wanted_places(wanted: dict[str, dict], records: list[dict]) -> dict[str, dict]:
    """県 → {places, source_url, feature}。図鑑に同じ自治体の蓋（公式・仮番号）があれば、その場所は出さない。

    投稿が来て仮番号を振る、または公式に載ると、台帳を直さなくてもカードから消える。
    """
    known = {(r.get("prefecture"), municipality_label(r)) for r in records}
    out: dict[str, dict] = {}
    for prefecture, entry in wanted.items():
        places = [
            place for place in entry.get("places") or []
            if isinstance(place, dict) and place.get("city")
            and (prefecture, str(place["city"])) not in known
        ]
        if places:
            out[prefecture] = {**entry, "places": places}
    return out


def wanted_summary(places_by_prefecture: dict[str, dict]) -> dict:
    """写真館に渡す形。県は北から（PREFECTURE_ORDER）、場所は市町と施設名だけ。"""
    prefectures = [
        {
            "prefecture": prefecture,
            "slug": PREFECTURE_SLUGS.get(prefecture, ""),
            "count": len(places_by_prefecture[prefecture]["places"]),
            "places": [
                {"city": str(p["city"]), "place": str(p.get("place") or "")}
                for p in places_by_prefecture[prefecture]["places"]
            ],
        }
        for prefecture in PREFECTURE_ORDER
        if prefecture in places_by_prefecture
    ]
    return {"total": sum(p["count"] for p in prefectures), "prefectures": prefectures}


SITE_URL = "https://data.pokefuta.com/"
# 詳細ページの日本語版と訳した版（generate_manhole_pages*.py の出力先）
REDIRECT_PREFIXES = ("", "en/", "zh-TW/")


def redirect_html(official_path: str) -> str:
    target = SITE_URL + official_path
    return f"""<!doctype html>
<html lang="ja"><head>
  <meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
  <title>正式な番号のページへ移動しました</title>
  <link rel="canonical" href="{target}"><meta name="robots" content="noindex,follow">
  <meta http-equiv="refresh" content="0; url={target}">
</head><body>
  <p>このポケふたは公式サイトに載りました。<a href="{target}">正式な番号のページ</a>へ移動します。</p>
</body></html>
"""


def write_redirects(ledger: dict[str, dict], output: Path) -> list[Path]:
    """公式に載って official_id が付いた仮番号の詳細ページを、正式な番号のページへの転送にする。

    静的ホスティングで 301 は出せないので canonical + meta refresh（generate_character_work_pages と同じ形）。
    詳細ページを作った後に呼ぶ（仮番号のページは build_records() が出さないので上書きの心配はない）。
    """
    written: list[Path] = []
    for pid, entry in sorted(ledger.items(), key=lambda item: int(item[0])):
        official_id = entry.get("official_id")
        if official_id is None:
            continue
        for prefix in REDIRECT_PREFIXES:
            path = output / prefix / "manholes" / pid / "index.html"
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(redirect_html(f"{prefix}manholes/{official_id}/"), encoding="utf-8")
            written.append(path)
    return written


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--ledger", type=Path, default=DEFAULT_LEDGER)
    parser.add_argument("--official", type=Path, default=DEFAULT_OFFICIAL)
    parser.add_argument("--design", type=Path, default=DEFAULT_DESIGN)
    parser.add_argument("--overrides", type=Path, default=DEFAULT_OVERRIDES)
    parser.add_argument("--out", type=Path, help="公式＋仮の NDJSON の書き出し先（省略時は検査だけ）")
    parser.add_argument("--image-dir", type=Path, help="投稿の写真を落とすフォルダ")
    parser.add_argument("--wanted", type=Path, default=DEFAULT_WANTED)
    parser.add_argument("--photos-in", type=Path, help="latest-manhole-photos.json（--photos-out と一緒に）")
    parser.add_argument("--photos-out", type=Path, help="仮番号の写真の行を足した写真 JSON の書き出し先")
    parser.add_argument(
        "--provisional-out", type=Path,
        help="仮番号の蓋だけの NDJSON（地図 map.html が公式の pokefuta.ndjson に重ねて読む）",
    )
    parser.add_argument(
        "--wanted-out", type=Path,
        help="緯度経度を調べているポケふたの JSON（写真館トップの「募集中」カードが読む。api/provisional-wanted.json）",
    )
    parser.add_argument("--redirects-dir", type=Path, help="公式に載った仮番号の転送ページを書くサイトのルート（dist）")
    args = parser.parse_args(argv)

    official_lines = [line for line in args.official.read_text(encoding="utf-8").splitlines() if line.strip()]
    official_ids = {str(json.loads(line).get("id", "")).strip() for line in official_lines}
    ledger = load_ledger(args.ledger)
    overrides = json.loads(args.overrides.read_text(encoding="utf-8")) if args.overrides.exists() else {}
    validate_ledger(ledger, official_ids, overrides)

    records = build_records(ledger, read_ndjson(args.design))
    with_photo: list[dict] = []
    if args.image_dir:
        records, with_photo = attach_photos(records, args.image_dir)
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(
            "".join(line + "\n" for line in official_lines)
            + "".join(json.dumps(record, ensure_ascii=False) + "\n" for record in records),
            encoding="utf-8",
        )
    if args.redirects_dir:
        written = write_redirects(ledger, args.redirects_dir)
        print(f"[provisional] 公式に載った仮番号の転送ページ {len(written)} 件")
        return 0
    if args.provisional_out:
        photo_ids = {record["id"] for record in with_photo}
        args.provisional_out.parent.mkdir(parents=True, exist_ok=True)
        args.provisional_out.write_text(
            "".join(
                json.dumps({**record, "has_photo": record["id"] in photo_ids}, ensure_ascii=False) + "\n"
                for record in records
            ),
            encoding="utf-8",
        )
    if args.wanted_out:
        official = [json.loads(line) for line in official_lines]
        args.wanted_out.parent.mkdir(parents=True, exist_ok=True)
        args.wanted_out.write_text(
            json.dumps(wanted_summary(wanted_places(load_wanted(args.wanted), official + records)), ensure_ascii=False),
            encoding="utf-8",
        )
    if args.photos_in and args.photos_out:
        payload = json.loads(args.photos_in.read_text(encoding="utf-8"))
        args.photos_out.parent.mkdir(parents=True, exist_ok=True)
        args.photos_out.write_text(
            json.dumps(merge_photos(payload, with_photo), ensure_ascii=False),
            encoding="utf-8",
        )
    print(f"[provisional] 台帳 {len(ledger)} 件のうち {len(records)} 件を出す: {[r['id'] for r in records]}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
