from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from generate_character_manhole_page import (  # noqa: E402
    build_latest_posts,
    build_prefecture_summaries,
    build_work_summaries,
    generate_html,
    load_active_manholes,
)


def _write_ndjson(directory: Path, name: str, records: list[dict]) -> Path:
    path = directory / name
    path.write_text(
        "\n".join(json.dumps(record, ensure_ascii=False) for record in records),
        encoding="utf-8",
    )
    return path


CHARACTER_RECORDS = [
    {
        "id": "zls-1", "work": "ゾンビランドサガ", "character": "源さくら",
        "prefecture": "佐賀県", "city": "佐賀市", "status": "active",
        "marker_color": "#10b981", "marker_label": "ゾ", "landmark": "唐人プラザビル",
    },
    {
        "id": "zls-2", "work": "ゾンビランドサガ", "character": "二階堂サキ",
        "prefecture": "佐賀県", "city": "佐賀市", "status": "active",
        "marker_color": "#10b981", "marker_label": "ゾ",
    },
    {
        "id": "yp-1", "work": "弱虫ペダル", "character": "小野田坂道",
        "prefecture": "長崎県", "city": "長崎市", "status": "active",
        "marker_color": "#ec4899", "marker_label": "弱",
    },
    {
        # status != active は除外される
        "id": "removed-1", "work": "ゾンビランドサガ", "character": "撤去済み",
        "prefecture": "佐賀県", "city": "佐賀市", "status": "invalid",
        "marker_color": "#10b981", "marker_label": "ゾ",
    },
    {
        # installation_status が明示的に撤去済みなら除外
        "id": "removed-2", "work": "弱虫ペダル", "character": "撤去済み2",
        "prefecture": "長崎県", "city": "長崎市", "status": "active",
        "installation_status": "removed",
        "marker_color": "#ec4899", "marker_label": "弱",
    },
    {
        # installation_status が None は許容
        "id": "yp-2", "work": "弱虫ペダル", "character": "今泉俊輔",
        "prefecture": "長崎県", "city": "長崎市", "status": "active",
        "installation_status": None,
        "marker_color": "#ec4899", "marker_label": "弱",
    },
]

GUNDAM_RECORDS = [
    {"id": "1", "prefecture": "北海道", "city": "豊富町", "status": "active", "franchise": "gundam"},
    {"id": "2", "prefecture": "佐賀県", "city": "佐賀市", "status": "active", "franchise": "gundam"},
    {"id": "3", "prefecture": "佐賀県", "city": "唐津市", "status": "invalid", "franchise": "gundam"},
]

DESIGN_MANHOLE_RECORDS = [
    {
        "id": "d-1", "title": "写真あり最新", "status": "active",
        "photo_url": "https://pokefuta.com/api/design-manholes/d-1/photo",
        "prefecture": "愛知県", "city": "名古屋市", "source_url": "https://pokefuta.com/design-manholes/d-1",
        "created_at": "2026-07-19T00:00:00+00:00",
    },
    {
        "id": "d-2", "title": "写真なし", "status": "active",
        "photo_url": "",
        "prefecture": "愛知県", "city": "豊橋市", "source_url": "https://pokefuta.com/design-manholes/d-2",
        "created_at": "2026-07-18T00:00:00+00:00",
    },
    {
        "id": "d-3", "title": "写真あり2番目", "status": "active",
        "photo_url": "https://pokefuta.com/api/design-manholes/d-3/photo",
        "prefecture": "北海道", "city": "剣淵町", "source_url": "https://pokefuta.com/design-manholes/d-3",
        "created_at": "2026-07-10T00:00:00+00:00",
    },
    {
        "id": "d-4", "title": "非アクティブ", "status": "removed",
        "photo_url": "https://pokefuta.com/api/design-manholes/d-4/photo",
        "prefecture": "愛知県", "city": "名古屋市", "source_url": "https://pokefuta.com/design-manholes/d-4",
        "created_at": "2026-07-20T00:00:00+00:00",
    },
]


class WorkSummaryTest(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmpdir.cleanup)
        directory = Path(self.tmpdir.name)
        character_path = _write_ndjson(directory, "character_manholes.ndjson", CHARACTER_RECORDS)
        gundam_path = _write_ndjson(directory, "gmanhole.ndjson", GUNDAM_RECORDS)
        self.character_records = load_active_manholes(character_path)
        self.gundam_records = load_active_manholes(gundam_path)

    def test_excludes_inactive_and_removed_records(self):
        ids = {record["id"] for record in self.character_records}
        self.assertNotIn("removed-1", ids)
        self.assertNotIn("removed-2", ids)
        self.assertIn("yp-2", ids)  # installation_status=None は許容
        self.assertEqual(4, len(self.character_records))

        gundam_ids = {record["id"] for record in self.gundam_records}
        self.assertNotIn("3", gundam_ids)
        self.assertEqual(2, len(self.gundam_records))

    def test_work_summaries_sorted_by_count_descending(self):
        summaries = build_work_summaries(self.character_records, self.gundam_records)
        counts = [summary["count"] for summary in summaries]
        self.assertEqual(counts, sorted(counts, reverse=True))
        works = [summary["work"] for summary in summaries]
        # ゾンビランドサガ(2) / 弱虫ペダル(2) / ガンダム(1) が含まれる
        self.assertIn("ゾンビランドサガ", works)
        self.assertIn("弱虫ペダル", works)
        self.assertTrue(any("ガンダム" in work for work in works))

    def test_gundam_entry_uses_special_work_query(self):
        summaries = build_work_summaries(self.character_records, self.gundam_records)
        gundam = next(s for s in summaries if "ガンダム" in s["work"])
        self.assertEqual("gundam", gundam["query"])
        self.assertEqual(2, gundam["count"])

    def test_prefecture_summaries_combine_character_and_gundam(self):
        summaries = build_prefecture_summaries(self.character_records, self.gundam_records)
        by_pref = {entry["prefecture"]: entry["count"] for entry in summaries}
        # 佐賀県: キャラ蓋2件 + ガンダム(active)1件 = 3
        self.assertEqual(3, by_pref["佐賀県"])
        # 長崎県: キャラ蓋2件（active）
        self.assertEqual(2, by_pref["長崎県"])
        # 北海道: ガンダムのみ1件
        self.assertEqual(1, by_pref["北海道"])
        counts = [entry["count"] for entry in summaries]
        self.assertEqual(counts, sorted(counts, reverse=True))


class LatestPostsTest(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmpdir.cleanup)
        directory = Path(self.tmpdir.name)
        self.design_path = _write_ndjson(directory, "design_manholes.ndjson", DESIGN_MANHOLE_RECORDS)

    def test_excludes_posts_without_photo_and_inactive(self):
        posts = build_latest_posts(self.design_path, limit=4)
        titles = [post["title"] for post in posts]
        self.assertNotIn("写真なし", titles)
        self.assertNotIn("非アクティブ", titles)
        self.assertIn("写真あり最新", titles)
        self.assertIn("写真あり2番目", titles)

    def test_sorted_by_created_at_descending(self):
        posts = build_latest_posts(self.design_path, limit=4)
        self.assertEqual("写真あり最新", posts[0]["title"])
        self.assertEqual("写真あり2番目", posts[1]["title"])

    def test_respects_limit(self):
        posts = build_latest_posts(self.design_path, limit=1)
        self.assertEqual(1, len(posts))


class GenerateHtmlTest(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmpdir.cleanup)
        directory = Path(self.tmpdir.name)
        character_path = _write_ndjson(directory, "character_manholes.ndjson", CHARACTER_RECORDS)
        gundam_path = _write_ndjson(directory, "gmanhole.ndjson", GUNDAM_RECORDS)
        self.design_path = _write_ndjson(directory, "design_manholes.ndjson", DESIGN_MANHOLE_RECORDS)
        self.character_records = load_active_manholes(character_path)
        self.gundam_records = load_active_manholes(gundam_path)
        self.html = generate_html(self.character_records, self.gundam_records, self.design_path)

    def test_includes_work_names_and_counts(self):
        self.assertIn("ゾンビランドサガ", self.html)
        self.assertIn("弱虫ペダル", self.html)
        self.assertIn("2枚", self.html)

    def test_includes_pref_and_work_deep_links(self):
        self.assertIn("gmanhole_map.html?pref=", self.html)
        self.assertIn("gmanhole_map.html?work=", self.html)

    def test_includes_design_manhole_submission_link(self):
        self.assertIn("design_manhole.html", self.html)

    def test_excludes_photo_less_posts_from_latest_section(self):
        self.assertNotIn("写真なし", self.html)
        self.assertIn("写真あり最新", self.html)

    def test_does_not_hardcode_totals_and_reacts_to_data_changes(self):
        total_before = len(self.character_records) + len(self.gundam_records)
        self.assertIn(f"{total_before}枚", self.html)

        # データを1件減らして再生成すると出力の数字も変わることを確認する
        # （件数が生成時に直書きされていないことの回帰防止）
        fewer_records = self.character_records[:-1]
        html_after = generate_html(fewer_records, self.gundam_records, self.design_path)
        total_after = len(fewer_records) + len(self.gundam_records)
        self.assertNotEqual(total_before, total_after)
        self.assertIn(f"{total_after}枚", html_after)
        self.assertNotIn(f'<strong>{total_before}</strong><span>枚</span>', html_after)


if __name__ == "__main__":
    unittest.main()
