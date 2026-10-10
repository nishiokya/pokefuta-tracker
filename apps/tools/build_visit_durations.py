"""自治体のポケふたを1日で全部回った人の所要時間を、DB バックアップから集計する（手動実行）。

入力は pokefuta.com の Supabase を pg_dump した data.sql（k11 の日次バックアップ）。
public.visit の user_id / manhole_id / shot_at と public.manhole だけを読む。

出力 dataset/visit_durations.json には集計値だけを書く（個人の時刻・順番・ID は出さない）。
集計する組は自治体ごと・都道府県ごと・dataset/trip_areas.json のエリアごと。
各ページは、ここに載った manhole_ids がそのページの回れる地点と一致するときだけ
所要時間を出す（apps/scraper/visit_durations.py）。

    python3 apps/tools/build_visit_durations.py --dump ~/backups/pokefuta/db/<日時>/data.sql
"""

from __future__ import annotations

import argparse
import collections
import json
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_OUTPUT = ROOT / "dataset" / "visit_durations.json"
DEFAULT_AREAS = ROOT / "dataset" / "trip_areas.json"
JST = timezone(timedelta(hours=9))
# この人数に満たない自治体は出さない（少人数だと個人の回り方そのものになる）
MIN_PEOPLE = 5
# よく回られる順を出すのに要る、同じ道筋（往復は同じとみなす）で回った人数
MIN_ORDER_PEOPLE = 3
# shot_at が投稿時刻とほぼ同じ visit は、EXIF が無く投稿時刻が入っただけとみなして使わない
FALLBACK_SECONDS = 120


def read_copy(dump: Path, table: str) -> list[dict[str, str]]:
    header = f'COPY "public"."{table}" '
    rows: list[dict[str, str]] = []
    cols: list[str] | None = None
    with dump.open(encoding="utf-8") as f:
        for line in f:
            if cols is None:
                if line.startswith(header):
                    cols = [c.strip(' "') for c in line.split("(", 1)[1].split(")")[0].split(",")]
                continue
            if line.startswith("\\."):
                break
            rows.append(dict(zip(cols, line.rstrip("\n").split("\t"))))
    if cols is None:
        raise SystemExit(f"{dump} に public.{table} がない")
    return rows


def _time(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("+00", "+00:00")).astimezone(JST)


def quartile(values: list[float], p: float) -> float:
    v = sorted(values)
    i = (len(v) - 1) * p
    lo = int(i)
    hi = min(lo + 1, len(v) - 1)
    return v[lo] + (v[hi] - v[lo]) * (i - lo)


def manhole_groups(manholes: list[dict[str, str]], areas: list[dict] | None = None) -> dict[frozenset[str], str]:
    """集計する地点の組 → 表示名。自治体ごと・都道府県ごと・手で登録したエリア（trip）ごと。

    同じ組が2回出たら先の名前を使う（県の全部が1自治体にあるときは自治体名）。
    """
    by_key: dict[tuple[str, str], set[str]] = collections.defaultdict(set)
    for r in manholes:
        if r.get("is_active") == "t":
            by_key[(r["prefecture"], r["municipality"])].add(r["id"])
            by_key[(r["prefecture"], "")].add(r["id"])
    groups: dict[frozenset[str], str] = {}
    for (prefecture, municipality), ids in sorted(by_key.items(), key=lambda kv: kv[0][1] == ""):
        groups.setdefault(frozenset(ids), f"{prefecture}{municipality}")
    for area in areas or []:
        groups.setdefault(frozenset(str(i) for i in area["manhole_ids"]), area.get("title", ""))
    return {ids: label for ids, label in groups.items() if len(ids) >= 2}


def build(
    manholes: list[dict[str, str]],
    visits: list[dict[str, str]],
    areas: list[dict] | None = None,
    photo_visit_ids: set[str] | None = None,
) -> list[dict]:
    """photo_visit_ids は写真のある visit の id。公開されていて写真のある visit だけを数える
    （サイトのほかの公開集計と同じ条件。export_app_snapshot.py の public_with_photo）。"""
    active = {r["id"] for r in manholes if r.get("is_active") == "t"}
    groups = manhole_groups(manholes, areas)

    # ユーザー × JST の日付ごとに、各マンホールを最初に撮った時刻
    days: dict[tuple[str, object], dict[str, datetime]] = collections.defaultdict(dict)
    for v in visits:
        if v["shot_at"] == "\\N" or v["manhole_id"] not in active:
            continue
        if v.get("is_public") != "t" or (photo_visit_ids is not None and v["id"] not in photo_visit_ids):
            continue
        shot = _time(v["shot_at"])
        if abs((shot - _time(v["created_at"])).total_seconds()) < FALLBACK_SECONDS:
            continue
        day = days[(v["user_id"], shot.date())]
        if v["manhole_id"] not in day or shot < day[v["manhole_id"]]:
            day[v["manhole_id"]] = shot

    out = []
    for ids, label in groups.items():
        # その組を同じ日に全部撮った人の、組の1枚目→最後の1枚の時間と順番。1人1回（最初の日）。
        per_user: dict[str, tuple[object, float, tuple[str, ...]]] = {}
        for (user, date), shots in days.items():
            if not ids <= shots.keys():
                continue
            seq = sorted(ids, key=lambda m: shots[m])
            minutes = (shots[seq[-1]] - shots[seq[0]]).total_seconds() / 60
            if user not in per_user or date < per_user[user][0]:
                per_user[user] = (date, minutes, tuple(seq))
        if len(per_user) < MIN_PEOPLE:
            continue
        minutes = [m for _, m, _ in per_user.values()]
        entry = {
            "label": label,
            "manhole_ids": sorted(ids, key=int),
            "people": len(per_user),
            "p25_minutes": round(quartile(minutes, 0.25)),
            "p75_minutes": round(quartile(minutes, 0.75)),
        }
        # 往路と復路は同じ道筋として数える。MIN_ORDER_PEOPLE 人以上が同じ道筋のときだけ出す
        orders = collections.Counter(min(o, o[::-1]) for _, _, o in per_user.values())
        (order, n), = orders.most_common(1)
        if n >= MIN_ORDER_PEOPLE:
            entry["common_order"] = list(order)
            entry["common_order_people"] = n
        out.append(entry)
    return sorted(out, key=lambda e: (-e["people"], e["label"]))


def measured_on_from_path(dump: Path) -> str | None:
    """バックアップの日時ディレクトリ（…/2026-10-11T0416+0900/data.sql）から日付を取る。実行日は使わない。"""
    for part in reversed(dump.resolve().parts):
        match = re.match(r"(\d{4}-\d{2}-\d{2})T", part)
        if match:
            return match.group(1)
    return None


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dump", type=Path, required=True)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--areas", type=Path, default=DEFAULT_AREAS)
    parser.add_argument(
        "--measured-on",
        help="ページに出す集計日（YYYY-MM-DD）。省略時はバックアップのディレクトリ名（2026-10-11T0416+0900）から取る",
    )
    args = parser.parse_args()
    measured_on = args.measured_on or measured_on_from_path(args.dump)
    if not measured_on:
        raise SystemExit("集計日が分からない。--measured-on YYYY-MM-DD を渡す")
    areas = json.loads(args.areas.read_text(encoding="utf-8"))["areas"] if args.areas.exists() else []
    photo_visit_ids = {p["visit_id"] for p in read_copy(args.dump, "photo")}
    entries = build(
        read_copy(args.dump, "manhole"), read_copy(args.dump, "visit"), areas, photo_visit_ids
    )
    payload = {
        "measured_on": measured_on,
        "min_people": MIN_PEOPLE,
        "entries": entries,
    }
    args.output.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"[build_visit_durations] {len(entries)} 組 → {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
