from __future__ import annotations

import json
import re
import sys
import tempfile
import unittest
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from generate_character_manhole_page import (  # noqa: E402
    FAQ_ITEMS,
    build_hero_mosaic,
    build_latest_posts,
    build_mini_map_pins,
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
        "lat": 33.256344, "lng": 130.299759,
    },
    {
        "id": "zls-2", "work": "ゾンビランドサガ", "character": "二階堂サキ",
        "prefecture": "佐賀県", "city": "佐賀市", "status": "active",
        "marker_color": "#10b981", "marker_label": "ゾ",
        "lat": 33.246159, "lng": 130.3026375,
    },
    {
        "id": "yp-1", "work": "弱虫ペダル", "character": "小野田坂道",
        "prefecture": "長崎県", "city": "長崎市", "status": "active",
        "marker_color": "#ec4899", "marker_label": "弱",
        # lat/lng が無いレコードもある想定（ジオコーディング未済など）
    },
    {
        # status != active は除外される
        "id": "removed-1", "work": "ゾンビランドサガ", "character": "撤去済み",
        "prefecture": "佐賀県", "city": "佐賀市", "status": "invalid",
        "marker_color": "#10b981", "marker_label": "ゾ",
        "lat": 33.0, "lng": 130.0,
    },
    {
        # installation_status が明示的に撤去済みなら除外
        "id": "removed-2", "work": "弱虫ペダル", "character": "撤去済み2",
        "prefecture": "長崎県", "city": "長崎市", "status": "active",
        "installation_status": "removed",
        "marker_color": "#ec4899", "marker_label": "弱",
        "lat": 32.0, "lng": 129.0,
    },
    {
        # installation_status が None は許容
        "id": "yp-2", "work": "弱虫ペダル", "character": "今泉俊輔",
        "prefecture": "長崎県", "city": "長崎市", "status": "active",
        "installation_status": None,
        "marker_color": "#ec4899", "marker_label": "弱",
        "lat": 32.744, "lng": 129.8737,
    },
]

GUNDAM_RECORDS = [
    {"id": "1", "prefecture": "北海道", "city": "豊富町", "status": "active", "franchise": "gundam", "lat": 45.10487, "lng": 141.772842},
    {"id": "2", "prefecture": "佐賀県", "city": "佐賀市", "status": "active", "franchise": "gundam", "lat": 33.25, "lng": 130.3},
    {"id": "3", "prefecture": "佐賀県", "city": "唐津市", "status": "invalid", "franchise": "gundam", "lat": 33.45, "lng": 129.97},
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

# ヒーローモザイク専用フィクスチャ（?size=small を含む実際の photo_url の形に合わせる）
HERO_MOSAIC_RECORDS = [
    {
        # canonical_ref がキャラクターマンホール参照 → 優先枠
        "id": "hm-gundam", "title": "稚内副港市場", "status": "active",
        "photo_url": "https://pokefuta.com/api/design-manholes/hm-gundam/photo?size=small",
        "canonical_ref": "gundam:5",
        "nearby_refs": [{"distance_m": 27, "ref": "gundam:5", "title": "稚内副港市場"}],
        "prefecture": "北海道", "city": "稚内市",
    },
    {
        # nearby_refs 側にキャラクターマンホール参照 → 優先枠
        "id": "hm-character", "title": "常滑のアイマスマンホール", "status": "active",
        "photo_url": "https://pokefuta.com/api/design-manholes/hm-character/photo?size=small",
        "canonical_ref": None,
        "nearby_refs": [{"distance_m": 5, "ref": "character:aichi-idolmaster-maekawa-miku", "title": "前川みく"}],
        "prefecture": "愛知県", "city": "常滑市",
    },
    {
        # 紐付けなし普通の投稿 → その他枠
        "id": "hm-plain-1", "title": "鯱", "status": "active",
        "photo_url": "https://pokefuta.com/api/design-manholes/hm-plain-1/photo?size=small",
        "canonical_ref": None, "nearby_refs": [],
        "prefecture": "愛知県", "city": "名古屋市",
    },
    {
        # pokefuta: 参照はキャラマンホールではないのでその他枠
        "id": "hm-plain-2", "title": "豊橋駅前", "status": "active",
        "photo_url": "https://pokefuta.com/api/design-manholes/hm-plain-2/photo?size=small",
        "canonical_ref": None,
        "nearby_refs": [{"distance_m": 46, "ref": "pokefuta:272", "title": "愛知県/豊橋市"}],
        "prefecture": "愛知県", "city": "豊橋市",
    },
    {
        "id": "hm-plain-3", "title": "絵本のマンホール", "status": "active",
        "photo_url": "https://pokefuta.com/api/design-manholes/hm-plain-3/photo?size=small",
        "canonical_ref": None, "nearby_refs": [],
        "prefecture": "北海道", "city": "剣淵町",
    },
    {
        # 非アクティブは除外
        "id": "hm-inactive", "title": "非アクティブ投稿", "status": "removed",
        "photo_url": "https://pokefuta.com/api/design-manholes/hm-inactive/photo?size=small",
        "canonical_ref": "gundam:1", "nearby_refs": [],
        "prefecture": "北海道", "city": "豊富町",
    },
    {
        # size=medium は 2MB 原寸への 307 リダイレクトになるため、優先枠でも除外
        "id": "hm-medium", "title": "サイズ違反(medium)", "status": "active",
        "photo_url": "https://pokefuta.com/api/design-manholes/hm-medium/photo?size=medium",
        "canonical_ref": "gundam:9", "nearby_refs": [],
        "prefecture": "北海道", "city": "豊富町",
    },
    {
        # size=large も同様に除外
        "id": "hm-large", "title": "サイズ違反(large)", "status": "active",
        "photo_url": "https://pokefuta.com/api/design-manholes/hm-large/photo?size=large",
        "canonical_ref": None, "nearby_refs": [],
        "prefecture": "北海道", "city": "豊富町",
    },
    {
        # size 未指定（=原寸へ落ちうる）も除外
        "id": "hm-nosize", "title": "サイズ指定なし", "status": "active",
        "photo_url": "https://pokefuta.com/api/design-manholes/hm-nosize/photo",
        "canonical_ref": None, "nearby_refs": [],
        "prefecture": "北海道", "city": "豊富町",
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

    def test_escapes_quotes_in_user_submitted_attributes(self):
        """投稿タイトルは pokefuta.com のユーザー入力。属性を抜け出せてはいけない。"""
        directory = Path(self.tmpdir.name)
        evil = '\u30c6\u30b9\u30c8" onload="alert(1)'
        design_path = _write_ndjson(
            directory,
            "design_manholes_xss.ndjson",
            [
                {
                    "id": "d-x", "title": evil, "status": "active",
                    "photo_url": "https://pokefuta.com/api/design-manholes/d-x/photo",
                    "prefecture": "\u611b\u77e5\u770c", "city": "\u540d\u53e4\u5c4b\u5e02",
                    "source_url": "https://pokefuta.com/design-manholes/d-x",
                    "created_at": "2026-07-19T00:00:00+00:00",
                }
            ],
        )
        html = generate_html(self.character_records, self.gundam_records, design_path)
        self.assertNotIn('onload="alert(1)"', html)
        self.assertNotIn('" onload=', html)
        self.assertIn("&quot;", html)

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


class HeroMosaicTest(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmpdir.cleanup)
        directory = Path(self.tmpdir.name)
        self.design_path = _write_ndjson(directory, "design_manholes.ndjson", HERO_MOSAIC_RECORDS)

    def test_prioritizes_gundam_and_character_linked_records(self):
        # 複数の日付シードで確認: 優先枠(gundam:/character: 紐付け)は
        # シャッフルされても常にその他枠より前に来る。
        for day in range(1, 15):
            posts = build_hero_mosaic(self.design_path, seed_date=date(2026, 7, day))
            titles = [post["title"] for post in posts]
            priority_titles = {"稚内副港市場", "常滑のアイマスマンホール"}
            other_titles = {"鯱", "豊橋駅前", "絵本のマンホール"}
            priority_positions = [titles.index(t) for t in priority_titles if t in titles]
            other_positions = [titles.index(t) for t in other_titles if t in titles]
            if priority_positions and other_positions:
                self.assertLess(
                    max(priority_positions), min(other_positions),
                    f"priority records must sort before others (seed day={day}, titles={titles})",
                )
            # 優先枠2件は必ず両方含まれる（limit=6 かつ候補は9件・うち有効6件なので入り切る）
            self.assertTrue(priority_titles.issubset(set(titles)))

    def test_excludes_non_small_size_urls(self):
        posts = build_hero_mosaic(self.design_path, seed_date=date(2026, 7, 1))
        titles = {post["title"] for post in posts}
        self.assertNotIn("サイズ違反(medium)", titles)
        self.assertNotIn("サイズ違反(large)", titles)
        self.assertNotIn("サイズ指定なし", titles)
        for post in posts:
            self.assertIn("size=small", post["photo_url"])
            self.assertNotIn("size=medium", post["photo_url"])
            self.assertNotIn("size=large", post["photo_url"])

    def test_excludes_inactive_records(self):
        posts = build_hero_mosaic(self.design_path, seed_date=date(2026, 7, 1))
        titles = {post["title"] for post in posts}
        self.assertNotIn("非アクティブ投稿", titles)

    def test_same_seed_is_deterministic(self):
        posts_a = build_hero_mosaic(self.design_path, seed_date=date(2026, 7, 3))
        posts_b = build_hero_mosaic(self.design_path, seed_date=date(2026, 7, 3))
        self.assertEqual([p["title"] for p in posts_a], [p["title"] for p in posts_b])

    def test_missing_dataset_returns_empty_list(self):
        missing_path = Path(self.tmpdir.name) / "does_not_exist.ndjson"
        self.assertEqual([], build_hero_mosaic(missing_path))

    def test_empty_dataset_returns_empty_list(self):
        directory = Path(self.tmpdir.name)
        empty_path = _write_ndjson(directory, "empty.ndjson", [])
        self.assertEqual([], build_hero_mosaic(empty_path))


class HeroMosaicHtmlTest(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmpdir.cleanup)
        directory = Path(self.tmpdir.name)
        character_path = _write_ndjson(directory, "character_manholes.ndjson", CHARACTER_RECORDS)
        gundam_path = _write_ndjson(directory, "gmanhole.ndjson", GUNDAM_RECORDS)
        self.character_records = load_active_manholes(character_path)
        self.gundam_records = load_active_manholes(gundam_path)
        self.directory = directory

    def test_renders_mosaic_with_priority_first(self):
        design_path = _write_ndjson(self.directory, "design_manholes.ndjson", HERO_MOSAIC_RECORDS)
        html = generate_html(self.character_records, self.gundam_records, design_path)
        self.assertIn("lp-hero-mosaic", html)
        # 優先枠のURLが、その他枠のURLより前に出現する
        priority_pos = html.index("hm-gundam")
        other_pos = html.index("hm-plain-1")
        self.assertLess(priority_pos, other_pos)

    def test_never_emits_medium_or_large_size_urls(self):
        design_path = _write_ndjson(self.directory, "design_manholes.ndjson", HERO_MOSAIC_RECORDS)
        html = generate_html(self.character_records, self.gundam_records, design_path)
        self.assertNotIn("size=medium", html)
        self.assertNotIn("size=large", html)

    def test_hero_images_are_not_lazy_and_have_explicit_dimensions(self):
        design_path = _write_ndjson(self.directory, "design_manholes.ndjson", HERO_MOSAIC_RECORDS)
        html = generate_html(self.character_records, self.gundam_records, design_path)
        # "lp-hero-mosaic-caption" は <style> 内のCSSセレクタとしても出現するため、
        # 実際の <ul> マークアップの開始位置以降だけを対象に検索する
        ul_start = html.index('<ul class="lp-hero-mosaic">')
        caption_pos = html.index("lp-hero-mosaic-caption", ul_start)
        mosaic_section = html[ul_start:caption_pos]
        self.assertNotIn('loading="lazy"', mosaic_section)
        # 元画像は 300×400 だが、タイルは正方形クリップ固定サイズで表示する
        self.assertIn('width="300"', mosaic_section)
        self.assertIn('height="300"', mosaic_section)

    def test_tiles_are_fixed_size_square_crop_not_a_stretchy_grid(self):
        design_path = _write_ndjson(self.directory, "design_manholes.ndjson", HERO_MOSAIC_RECORDS)
        html = generate_html(self.character_records, self.gundam_records, design_path)
        # 固定サイズタイル: グリッドを 1fr で伸び縮みさせるのではなく、
        # flex-wrap + 固定 width/height の正方形タイルで並べる
        self.assertIn(".lp-hero-mosaic-item {", html)
        self.assertIn("width: 96px; height: 96px;", html)
        self.assertNotIn("grid-template-columns: repeat(3, 1fr)", html)
        # object-fit: cover で中央クリップ（マンホールが切れないよう object-position も明示）
        self.assertIn("object-fit: cover;", html)
        self.assertIn("object-position: center;", html)

    def test_escapes_hero_mosaic_attributes(self):
        evil_title = 'テスト" onerror="alert(1)'
        malicious_records = [
            {
                "id": "hm-evil", "title": evil_title, "status": "active",
                "photo_url": "https://pokefuta.com/api/design-manholes/hm-evil/photo?size=small",
                "canonical_ref": "gundam:1", "nearby_refs": [],
                "prefecture": '商城"><script>alert(2)</script>', "city": "",
            },
        ]
        design_path = _write_ndjson(self.directory, "design_manholes_evil.ndjson", malicious_records)
        html = generate_html(self.character_records, self.gundam_records, design_path)
        self.assertNotIn('" onerror=', html)
        self.assertNotIn("<script>alert(2)</script>", html)
        self.assertIn("&quot;", html)

    def test_missing_design_manholes_file_falls_back_without_mosaic(self):
        # "lp-hero-mosaic-item" は <style> 内のCSSセレクタとして常に出現するため、
        # 実マークアップである <li class="lp-hero-mosaic-item"> の不在で判定する
        missing_path = self.directory / "does_not_exist.ndjson"
        html = generate_html(self.character_records, self.gundam_records, missing_path)
        self.assertNotIn('<li class="lp-hero-mosaic-item">', html)
        self.assertIn('<h1 class="top-h1">', html)  # ページ自体は正常にレンダリングされる

    def test_empty_design_manholes_file_falls_back_without_mosaic(self):
        empty_path = _write_ndjson(self.directory, "design_manholes_empty.ndjson", [])
        html = generate_html(self.character_records, self.gundam_records, empty_path)
        self.assertNotIn('<li class="lp-hero-mosaic-item">', html)
        self.assertIn('<h1 class="top-h1">', html)


class MiniMapPinsTest(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmpdir.cleanup)
        directory = Path(self.tmpdir.name)
        character_path = _write_ndjson(directory, "character_manholes.ndjson", CHARACTER_RECORDS)
        gundam_path = _write_ndjson(directory, "gmanhole.ndjson", GUNDAM_RECORDS)
        self.character_records = load_active_manholes(character_path)
        self.gundam_records = load_active_manholes(gundam_path)

    def test_skips_records_without_valid_latlng(self):
        # active: zls-1, zls-2, yp-1(lat/lng無し), yp-2 のキャラ蓋4件 + gundam 1,2 の2件 = 6件
        # うち yp-1 は lat/lng 無しなので座標配列には5件だけ入る
        pins = build_mini_map_pins(self.character_records, self.gundam_records)
        self.assertEqual(5, len(pins))

    def test_rounds_coordinates_to_5_decimals(self):
        pins = build_mini_map_pins(self.character_records, self.gundam_records)
        for lat, lng in pins:
            self.assertEqual(lat, round(lat, 5))
            self.assertEqual(lng, round(lng, 5))


# top-page.css が @media (min-width: 960px) 内で index.html 専用の重なりレイアウト
# （#sec-intro と #sec-map を同じグリッドエリアに重ね、pointer-events:none で下の
# 地図へクリックを透過させる設計）をID指定している要素。このLPには重なり構造が無いため、
# 同じIDを使うと「52%幅で左寄せ・クリック不能」という表示バグを引く（実際に発生した回帰）。
RESERVED_INDEX_PAGE_IDS = (
    "sec-intro", "sec-map", "sec-hero", "sec-hub", "sec-pref", "sec-events", "sec-newrelease",
)


class SharedCssIdSafetyTest(unittest.TestCase):
    """top-page.css は共有ファイル（index.html 用）なので編集しない。
    代わりにこのLP側が index.html 専用のID指定と衝突しないことを保証する。
    """

    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmpdir.cleanup)
        directory = Path(self.tmpdir.name)
        character_path = _write_ndjson(directory, "character_manholes.ndjson", CHARACTER_RECORDS)
        gundam_path = _write_ndjson(directory, "gmanhole.ndjson", GUNDAM_RECORDS)
        design_path = _write_ndjson(directory, "design_manholes.ndjson", DESIGN_MANHOLE_RECORDS)
        character_records = load_active_manholes(character_path)
        gundam_records = load_active_manholes(gundam_path)
        self.html = generate_html(character_records, gundam_records, design_path)

    def test_does_not_reuse_index_page_only_ids(self):
        for reserved_id in RESERVED_INDEX_PAGE_IDS:
            self.assertNotIn(
                f'id="{reserved_id}"', self.html,
                f'"{reserved_id}" is an index.html-only layout ID in top-page.css '
                "(52%-width overlay + pointer-events:none) — reusing it here breaks layout.",
            )

    def test_intro_section_uses_a_non_colliding_id(self):
        self.assertIn('id="lp-intro"', self.html)

    def test_neutralizes_desktop_class_overrides_meant_for_the_overlay_panel_pair(self):
        # top-page.css の @media (min-width: 960px) は、class（IDではない）レベルで
        # .top-intro-text/.top-stats-row の幅を狭め .map-gateway-title/.map-gateway-sub
        # を隠す。これは #sec-intro のオーバーレイパネルと対になっている前提の設計で、
        # このLPには対のパネルが無いため、そのままだとデスクトップ幅で説明文が消える。
        # .character-manhole-lp スコープで打ち消していることを確認する。
        self.assertIn(".character-manhole-lp .top-intro-text", self.html)
        self.assertIn(".character-manhole-lp .top-stats-row", self.html)
        self.assertIn(".character-manhole-lp .map-gateway-title", self.html)
        self.assertIn(".character-manhole-lp .map-gateway-sub", self.html)


class MapGatewayHtmlTest(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmpdir.cleanup)
        directory = Path(self.tmpdir.name)
        character_path = _write_ndjson(directory, "character_manholes.ndjson", CHARACTER_RECORDS)
        gundam_path = _write_ndjson(directory, "gmanhole.ndjson", GUNDAM_RECORDS)
        design_path = _write_ndjson(directory, "design_manholes.ndjson", DESIGN_MANHOLE_RECORDS)
        self.character_records = load_active_manholes(character_path)
        self.gundam_records = load_active_manholes(gundam_path)
        self.html = generate_html(self.character_records, self.gundam_records, design_path)

    def test_uses_map_gateway_classes_not_the_old_decorative_card(self):
        self.assertIn('class="map-gateway-card"', self.html)
        self.assertIn('class="map-gateway-minimap"', self.html)
        self.assertIn('class="map-gateway-overlay"', self.html)
        self.assertNotIn("lp-map-card", self.html)

    def test_includes_osm_attribution(self):
        # ライセンス上必須。attributionControl:false にする代わりに .map-gateway-attr で明示する
        self.assertIn("© OpenStreetMap contributors", self.html)
        self.assertIn('class="map-gateway-attr"', self.html)

    def test_map_interactions_are_all_disabled(self):
        # スマホでカードがスクロールを奪わないことの退行防止
        for option in (
            "zoomControl: false", "scrollWheelZoom: false", "dragging: false",
            "touchZoom: false", "doubleClickZoom: false", "boxZoom: false",
            "keyboard: false", "attributionControl: false",
        ):
            self.assertIn(option, self.html, f"missing disabled map option: {option}")

    def test_pin_json_embeds_all_valid_coordinates(self):
        match = re.search(r"var CM_MAP_PINS = (\[.*?\]);", self.html)
        self.assertIsNotNone(match, "CM_MAP_PINS array not found in output")
        pins = json.loads(match.group(1))
        expected = build_mini_map_pins(self.character_records, self.gundam_records)
        self.assertEqual(len(expected), len(pins))

    def test_leaflet_assets_loaded_with_integrity(self):
        self.assertIn("unpkg.com/leaflet@1.9.4/dist/leaflet.css", self.html)
        self.assertIn("unpkg.com/leaflet@1.9.4/dist/leaflet.js", self.html)
        self.assertIn('integrity="sha256-', self.html)


class PilgrimCopyTest(unittest.TestCase):
    """LPが「知らない人への説明」から「巡礼者への投稿依頼」に書き換わった後のコピー確認。
    SEO用の <title>/meta description/h2 は変更しない、という制約の確認も含む。
    """

    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmpdir.cleanup)
        directory = Path(self.tmpdir.name)
        character_path = _write_ndjson(directory, "character_manholes.ndjson", CHARACTER_RECORDS)
        gundam_path = _write_ndjson(directory, "gmanhole.ndjson", GUNDAM_RECORDS)
        design_path = _write_ndjson(directory, "design_manholes.ndjson", DESIGN_MANHOLE_RECORDS)
        self.character_records = load_active_manholes(character_path)
        self.gundam_records = load_active_manholes(gundam_path)
        self.total_count = len(self.character_records) + len(self.gundam_records)
        self.html = generate_html(self.character_records, self.gundam_records, design_path)

    def test_h1_is_the_pilgrim_request_copy(self):
        self.assertIn("ポケふた巡礼中に見つけた", self.html)
        self.assertIn("レアなマンホール、教えてくれませんか？", self.html)
        # 旧コピー（説明口調のH1）は残っていない
        self.assertNotIn("キャラクターマンホールって<br>知っていますか？", self.html)

    def test_title_and_meta_description_keep_seo_wording(self):
        # H1 を問いかけに変えても、検索語は <title>/meta description 側で保持する
        expected_title = f"キャラクターマンホールとは｜全国{self.total_count}枚"
        self.assertIn(f"<title>{expected_title}", self.html)
        self.assertIn(f'name="description" content="ガンダムやゾンビランドサガなど、全国{self.total_count}枚', self.html)

    def test_about_section_heading_is_unchanged_for_seo(self):
        self.assertIn('<h2 id="lp-about-heading"><span>WHAT IS IT</span>キャラクターマンホールとは</h2>', self.html)

    def test_stats_note_bakes_in_next_submission_number_with_no_placeholder(self):
        expected_next = self.total_count + 1
        self.assertIn(f"あなたの1枚が {expected_next} 枚目になります", self.html)
        # プレースホルダの取り残し（テンプレ文字列そのまま）が無いこと
        self.assertNotIn("{N+1}", self.html)
        self.assertNotIn("{next_submission_number}", self.html)

    def test_submit_section_uses_pilgrim_cta_copy(self):
        self.assertIn("その1枚、まだカメラロールにありますか？", self.html)
        self.assertIn("カメラロールの1枚を投稿する", self.html)
        self.assertIn("みんなの投稿を見る", self.html)

    def test_faq_matches_json_ld_faqpage(self):
        # 本文の <summary> と JSON-LD の FAQPage.mainEntity[].name が食い違っていないこと
        summary_questions = re.findall(r"<summary>(.*?)</summary>", self.html)
        self.assertEqual([q for q, _ in FAQ_ITEMS], summary_questions)

        ld_match = re.search(r'<script type="application/ld\+json">(.*?)</script>', self.html, re.S)
        self.assertIsNotNone(ld_match)
        graph = json.loads(ld_match.group(1))["@graph"]
        faq_node = next(node for node in graph if node.get("@type") == "FAQPage")
        ld_questions = [item["name"] for item in faq_node["mainEntity"]]
        self.assertEqual([q for q, _ in FAQ_ITEMS], ld_questions)

    def test_faq_answers_match_between_body_and_json_ld(self):
        ld_match = re.search(r'<script type="application/ld\+json">(.*?)</script>', self.html, re.S)
        graph = json.loads(ld_match.group(1))["@graph"]
        faq_node = next(node for node in graph if node.get("@type") == "FAQPage")
        for item, (_, expected_answer) in zip(faq_node["mainEntity"], FAQ_ITEMS):
            self.assertEqual(expected_answer, item["acceptedAnswer"]["text"])

    def test_uses_mai_counter_unit_only(self):
        # 助数詞は「枚」のみ。「基」「件」は使わない
        self.assertNotIn("基", self.html)
        self.assertNotIn(f"{self.total_count}件", self.html)


if __name__ == "__main__":
    unittest.main()
