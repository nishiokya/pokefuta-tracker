"""自治体のポケふたを1日で全部回った人の所要時間を、DB バックアップから集計する（手動実行）。

入力は pokefuta.com の Supabase を pg_dump した data.sql（k11 の日次バックアップ）。
public.visit の user_id / manhole_id / shot_at と public.manhole だけを読む。

出力 dataset/visit_durations.json には集計値だけを書く（個人の時刻・順番・ID は出さない）。
都道府県ページ・市区町村ページは、ここに載った manhole_ids がその自治体の
回れる地点と一致するときだけ所要時間を出す（apps/scraper/visit_durations.py）。

    python3 apps/tools/build_visit_durations.py --dump ~/backups/pokefuta/db/<日時>/data.sql
"""

from __future__ import annotations

import argparse
import collections
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_OUTPUT = ROOT / "dataset" / "visit_durations.json"
JST = timezone(timedelta(hours=9))
# この人数に満たない自治体は出さない（少人数だと個人の回り方そのものになる）
MIN_PEOPLE = 5
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


def build(manholes: list[dict[str, str]], visits: list[dict[str, str]]) -> list[dict]:
    group_of = {
        r["id"]: (r["prefecture"], r["municipality"])
        for r in manholes if r.get("is_active") == "t"
    }
    groups: dict[tuple[str, str], set[str]] = collections.defaultdict(set)
    for mid, key in group_of.items():
        groups[key].add(mid)

    # ユーザー × JST の日付ごとに、各マンホールを最初に撮った時刻
    days: dict[tuple[str, object], dict[str, datetime]] = collections.defaultdict(dict)
    for v in visits:
        if v["shot_at"] == "\\N" or v["manhole_id"] not in group_of:
            continue
        shot = _time(v["shot_at"])
        if abs((shot - _time(v["created_at"])).total_seconds()) < FALLBACK_SECONDS:
            continue
        day = days[(v["user_id"], shot.date())]
        if v["manhole_id"] not in day or shot < day[v["manhole_id"]]:
            day[v["manhole_id"]] = shot

    # 同じ自治体の蓋を続けて撮った区間のうち、その自治体の全部を含むものの所要時間。1人1回（最初の日）。
    per_user: dict[tuple[str, str], dict[str, tuple[object, float]]] = collections.defaultdict(dict)
    for (user, date), shots in days.items():
        seq = sorted(shots.items(), key=lambda kv: kv[1])
        run = [seq[0]]
        for item in seq[1:] + [None]:
            if item and group_of[item[0]] == group_of[run[-1][0]]:
                run.append(item)
                continue
            key = group_of[run[0][0]]
            if len(groups[key]) >= 2 and {m for m, _ in run} >= groups[key]:
                minutes = (run[-1][1] - run[0][1]).total_seconds() / 60
                if user not in per_user[key] or date < per_user[key][user][0]:
                    per_user[key][user] = (date, minutes)
            if item:
                run = [item]

    out = []
    for key, users in per_user.items():
        if len(users) < MIN_PEOPLE:
            continue
        minutes = [m for _, m in users.values()]
        out.append({
            "label": f"{key[0]}{key[1]}",
            "manhole_ids": sorted(groups[key], key=int),
            "people": len(users),
            "p25_minutes": round(quartile(minutes, 0.25)),
            "p75_minutes": round(quartile(minutes, 0.75)),
        })
    return sorted(out, key=lambda e: (-e["people"], e["label"]))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dump", type=Path, required=True)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    entries = build(read_copy(args.dump, "manhole"), read_copy(args.dump, "visit"))
    payload = {
        "measured_on": datetime.now(JST).strftime("%Y-%m-%d"),
        "min_people": MIN_PEOPLE,
        "entries": entries,
    }
    args.output.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"[build_visit_durations] {len(entries)} 自治体 → {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
