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


class BuildTest(unittest.TestCase):
    def setUp(self) -> None:
        self.manholes = [_manhole("1"), _manhole("2")]
        self.visits = []
        for n in range(5):
            self.visits += [_visit(f"a{n}", f"u{n}", "1", "01:00:00"), _visit(f"b{n}", f"u{n}", "2", "02:00:00")]
        self.photos = {v["id"] for v in self.visits}

    def test_five_people_are_published(self) -> None:
        entries = MODULE.build(self.manholes, self.visits, [], self.photos)
        self.assertEqual(entries[0]["people"], 5)
        self.assertEqual(entries[0]["p25_minutes"], 60)

    def test_private_or_photoless_visits_are_not_counted(self) -> None:
        """非公開・写真なしの visit は公開ページの集計に入れない（Codex レビュー、#608）。"""
        private = [dict(v, is_public="f") if v["user_id"] == "u0" else v for v in self.visits]
        self.assertEqual(MODULE.build(self.manholes, private, [], self.photos), [])
        no_photo = self.photos - {"a0"}
        self.assertEqual(MODULE.build(self.manholes, self.visits, [], no_photo), [])

    def test_measured_on_comes_from_the_backup_not_today(self) -> None:
        path = Path("/home/x/backups/pokefuta/db/2026-09-30T0416+0900/data.sql")
        self.assertEqual(MODULE.measured_on_from_path(path), "2026-09-30")
        self.assertIsNone(MODULE.measured_on_from_path(Path("/tmp/data.sql")))


if __name__ == "__main__":
    unittest.main()
