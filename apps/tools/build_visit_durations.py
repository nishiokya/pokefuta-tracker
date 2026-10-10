"""自治体のポケふたを1日で全部回った人の所要時間を、DB バックアップから集計する（手動実行）。

入力は pokefuta.com の Supabase を pg_dump した data.sql（k11 の日次バックアップ）。
public.visit の user_id / manhole_id / shot_at / is_public、public.photo の visit_id、public.manhole を読む。

出力 dataset/visit_durations.json には集計値だけを書く（人数・個人の時刻・ID は出さない）。
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
# 公開の記録だけで1日で全部回った人がこの人数に満たない組は出さない。よく回られる順も同じ人数で切る
MIN_PUBLIC_PEOPLE = 3
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
        groups.setdefault(frozenset(str(i) for i in area["manhole_ids"]), area.get("name", ""))
    return {ids: label for ids, label in groups.items() if len(ids) >= 2}


def build(
    manholes: list[dict[str, str]],
    visits: list[dict[str, str]],
    areas: list[dict] | None = None,
    photo_visit_ids: set[str] | None = None,
) -> list[dict]:
    """photo_visit_ids は写真のある visit の id（写真の無い visit は撮影時刻の出どころが不確かなので使わない）。

    - 出すかどうか: 公開の記録だけで、その組を1日で全部回った人が MIN_PUBLIC_PEOPLE 人以上
    - 所要時間の幅: 非公開の記録も含めた全員で計算する（プライバシーポリシー「3. 公開される情報」）
    - よく回られる順: 公開の記録の人だけで、MIN_PUBLIC_PEOPLE 人以上が同じ道筋のとき
    - 人数は出力しない
    """
    active = {r["id"] for r in manholes if r.get("is_active") == "t"}
    groups = manhole_groups(manholes, areas)

    # ユーザー × JST の日付ごとに、各マンホールを最初に撮った時刻（全部と、公開だけ）
    days_all: dict[tuple[str, object], dict[str, datetime]] = collections.defaultdict(dict)
    days_public: dict[tuple[str, object], dict[str, datetime]] = collections.defaultdict(dict)
    for v in visits:
        if v["shot_at"] == "\\N" or v["manhole_id"] not in active:
            continue
        if photo_visit_ids is not None and v["id"] not in photo_visit_ids:
            continue
        shot = _time(v["shot_at"])
        if abs((shot - _time(v["created_at"])).total_seconds()) < FALLBACK_SECONDS:
            continue
        targets = [days_all] + ([days_public] if v.get("is_public") == "t" else [])
        for days in targets:
            day = days[(v["user_id"], shot.date())]
            if v["manhole_id"] not in day or shot < day[v["manhole_id"]]:
                day[v["manhole_id"]] = shot

    def completions(days, ids) -> dict[str, tuple[object, float, tuple[str, ...]]]:
        # その組を同じ日に全部撮った人の、組の1枚目→最後の1枚の時間と順番。1人1回（最初の日）。
        per_user: dict[str, tuple[object, float, tuple[str, ...]]] = {}
        for (user, date), shots in days.items():
            if not ids <= shots.keys():
                continue
            seq = sorted(ids, key=lambda m: shots[m])
            minutes = (shots[seq[-1]] - shots[seq[0]]).total_seconds() / 60
            if user not in per_user or date < per_user[user][0]:
                per_user[user] = (date, minutes, tuple(seq))
        return per_user

    ranked = []
    for ids, label in groups.items():
        public = completions(days_public, ids)
        if len(public) < MIN_PUBLIC_PEOPLE:
            continue
        everyone = completions(days_all, ids)
        minutes = [m for _, m, _ in everyone.values()]
        entry = {
            "label": label,
            "manhole_ids": sorted(ids, key=int),
            "p25_minutes": round(quartile(minutes, 0.25)),
            "p75_minutes": round(quartile(minutes, 0.75)),
        }
        # 往路と復路は同じ道筋として数える
        orders = collections.Counter(min(o, o[::-1]) for _, _, o in public.values())
        (order, n), = orders.most_common(1)
        if n >= MIN_PUBLIC_PEOPLE:
            entry["common_order"] = list(order)
        ranked.append((len(everyone), entry))
    # 回った人が多い順に並べる（人数そのものは書かない）
    return [entry for _, entry in sorted(ranked, key=lambda t: (-t[0], t[1]["label"]))]


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
        "min_public_people": MIN_PUBLIC_PEOPLE,
        "entries": entries,
    }
    args.output.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"[build_visit_durations] {len(entries)} 組 → {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
