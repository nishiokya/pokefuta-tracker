from __future__ import annotations

import unittest
from pathlib import Path

from apps.tools import build_visit_durations as MODULE


def _manhole(mid: str) -> dict:
    return {"id": mid, "prefecture": "大阪府", "municipality": "東大阪", "is_active": "t"}


def _visit(vid: str, user: str, mid: str, shot: str, is_public: str = "t") -> dict:
    # created_at は撮影の1日後（投稿時刻と同じ shot_at は除外されるので、離しておく）
    return {"id": vid, "user_id": user, "manhole_id": mid, "shot_at": f"2026-10-01 {shot}+00",
            "created_at": "2026-10-02 00:00:00+00", "is_public": is_public}


def _trip(user: str, minutes: int, is_public: str = "t", first: str = "1") -> list[dict]:
    second = "2" if first == "1" else "1"
    return [
        _visit(f"{user}a", user, first, "01:00:00", is_public),
        _visit(f"{user}b", user, second, f"{1 + minutes // 60:02d}:{minutes % 60:02d}:00", is_public),
    ]


class BuildTest(unittest.TestCase):
    manholes = [_manhole("1"), _manhole("2")]

    def build(self, visits: list[dict], photos: set[str] | None = None) -> list[dict]:
        return MODULE.build(self.manholes, visits, [], photos or {v["id"] for v in visits})

    def test_needs_three_public_people(self) -> None:
        two_public = _trip("u0", 60) + _trip("u1", 60) + _trip("p0", 60, "f") + _trip("p1", 60, "f")
        self.assertEqual(self.build(two_public), [])
        self.assertEqual(len(self.build(two_public + _trip("u2", 60))), 1)

    def test_durations_include_private_records(self) -> None:
        """出すかどうかは公開の人数で決め、時間の幅は非公開も含めて計算する。"""
        visits = _trip("u0", 30) + _trip("u1", 30) + _trip("u2", 30)
        visits += _trip("p0", 120, "f") + _trip("p1", 120, "f") + _trip("p2", 120, "f")
        entry = self.build(visits)[0]
        self.assertEqual((entry["p25_minutes"], entry["p75_minutes"]), (30, 120))

    def test_no_head_count_in_the_output(self) -> None:
        entry = self.build(_trip("u0", 60) + _trip("u1", 60) + _trip("u2", 60))[0]
        self.assertNotIn("people", entry)
        self.assertNotIn("common_order_people", entry)

    def test_common_order_comes_from_public_records_only(self) -> None:
        public = _trip("u0", 60) + _trip("u1", 60) + _trip("u2", 60, first="2")
        private = sum((_trip(f"p{n}", 60, "f", first="2") for n in range(5)), [])
        # 公開の3人は同じ道筋（往復は同じ）なので出る。非公開は道筋の数に入らない
        self.assertEqual(self.build(public + private)[0]["common_order"], ["1", "2"])

    def test_photoless_visits_are_not_counted(self) -> None:
        visits = _trip("u0", 60) + _trip("u1", 60) + _trip("u2", 60)
        photos = {v["id"] for v in visits} - {"u0a"}
        self.assertEqual(self.build(visits, photos), [])

    def test_measured_on_comes_from_the_backup_not_today(self) -> None:
        path = Path("/home/x/backups/pokefuta/db/2026-09-30T0416+0900/data.sql")
        self.assertEqual(MODULE.measured_on_from_path(path), "2026-09-30")
        self.assertIsNone(MODULE.measured_on_from_path(Path("/tmp/data.sql")))


if __name__ == "__main__":
    unittest.main()
