from __future__ import annotations

import importlib.util
import sys
import unittest
from pathlib import Path

MODULE_PATH = Path(__file__).with_name("prefecture_completion.py")
SPEC = importlib.util.spec_from_file_location("prefecture_completion", MODULE_PATH)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC and SPEC.loader
# dataclass は自分のモジュールを sys.modules から引くので、exec_module の前に
# 登録しておかないと `@dataclass` の解決で落ちる（他のテストが読む対象は
# dataclass を使っていないのでこの一行が要らなかった）。
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


def record(manhole_id: str, installed: bool | None = None) -> dict:
    entry: dict = {"id": manhole_id}
    if installed is not None:
        entry["installed"] = installed
    return entry


class PrefectureCompletionTest(unittest.TestCase):
    def test_counts_missing_photos_per_prefecture(self) -> None:
        rollup = MODULE.build_completion(
            {"香川県": [record("1"), record("2"), record("3")]},
            {"1"},
        )
        entry = rollup.by_prefecture("香川県")
        assert entry is not None
        self.assertEqual((entry.total, entry.with_photo, entry.missing), (3, 1, 2))
        self.assertFalse(entry.is_complete)
        self.assertEqual(entry.coverage, 33)

    def test_prefecture_is_complete_when_every_manhole_has_a_photo(self) -> None:
        rollup = MODULE.build_completion(
            {"徳島県": [record("1"), record("2")]}, {"1", "2"}
        )
        self.assertEqual(rollup.complete_count, 1)
        self.assertEqual(rollup.incomplete_count, 0)
        self.assertEqual(rollup.missing_total, 0)

    def test_planned_installations_are_not_counted_as_missing(self) -> None:
        """installed:false はまだ現地に無いので「写真が足りない」に数えない。

        数えると、撮りに行きようのない残数がコンプリートを永遠に遠ざける。
        """
        rollup = MODULE.build_completion(
            {"香川県": [record("1"), record("2", installed=False)]},
            {"1"},
        )
        entry = rollup.by_prefecture("香川県")
        assert entry is not None
        self.assertEqual(entry.total, 1)
        self.assertTrue(entry.is_complete)

    def test_prefectures_without_any_pokefuta_are_excluded(self) -> None:
        """ポケふたが無い県はコンプリート率の母数に入れない。

        入れると「未設置なのでコンプリート」と「全部撮った」が同じ扱いになり、
        listed_count も47に見えてしまう（実際にポケふたがあるのは42都道府県）。
        """
        rollup = MODULE.build_completion(
            {"香川県": [record("1")], "群馬県": []}, {"1"}
        )
        self.assertEqual(rollup.listed_count, 1)
        self.assertIsNone(rollup.by_prefecture("群馬県"))

    def test_incomplete_is_ordered_by_fewest_missing_first(self) -> None:
        """先頭が「次に達成できる県」になるように並べる。"""
        rollup = MODULE.build_completion(
            {
                "長崎県": [record(str(i)) for i in range(10, 25)],
                "香川県": [record(str(i)) for i in range(30, 48)],
            },
            {str(i) for i in range(10, 20)} | {str(i) for i in range(30, 45)},
        )
        self.assertEqual(
            [(e.prefecture, e.missing) for e in rollup.incomplete],
            [("香川県", 3), ("長崎県", 5)],
        )

    def test_real_dataset_has_a_small_number_of_incomplete_prefectures(self) -> None:
        """実データでも「残りN県」が読める数に収まっていること。

        ここが2桁になっているなら県単位のカウントダウンは成立しないので、
        コピー（「残り{N}都道府県」）を見直す合図として落とす。
        """
        import json

        root = Path(__file__).resolve().parents[2]
        records_by_pref: dict[str, list[dict]] = {}
        for line in (root / "docs" / "pokefuta.ndjson").read_text(
            encoding="utf-8"
        ).splitlines():
            if not line.strip():
                continue
            entry = json.loads(line)
            if entry.get("status", "active") != "active":
                continue
            records_by_pref.setdefault(entry.get("prefecture", ""), []).append(entry)
        photos = json.loads(
            (root / "docs" / "latest-manhole-photos.json").read_text(encoding="utf-8")
        )
        rollup = MODULE.build_completion(
            records_by_pref, {str(k) for k in photos.get("photos", {})}
        )
        self.assertGreater(rollup.listed_count, 0)
        self.assertLessEqual(rollup.incomplete_count, 9)
        self.assertEqual(
            rollup.complete_count + rollup.incomplete_count, rollup.listed_count
        )


if __name__ == "__main__":
    unittest.main()
