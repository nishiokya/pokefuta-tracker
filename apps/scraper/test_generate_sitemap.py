#!/usr/bin/env python3
"""sitemap.xml 生成の固定条件。

/prefectures/ 一覧ページ追加時（PR #425）、生成ロジック自体には
トップレベル `/prefectures/` の url_entry が入っていたが、それを
検証するテストが無かったため、リポジトリに残る生成済み sitemap.xml
が古いままでも誰も気づけない状態だった。同種の抜けが再発しないよう、
主要な静的URLと都道府県47件が確実に含まれることを固定する。
"""

from __future__ import annotations

import importlib.util
import unittest
from pathlib import Path

MODULE_PATH = Path(__file__).with_name("generate_sitemap.py")
SPEC = importlib.util.spec_from_file_location("generate_sitemap", MODULE_PATH)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC and SPEC.loader
SPEC.loader.exec_module(MODULE)


class BuildSitemapTest(unittest.TestCase):
    def setUp(self) -> None:
        self.xml = MODULE.build_sitemap(
            ["1", "2"], ["pikachu"], character_work_pages=list(MODULE.read_character_work_pages(
                Path(__file__).resolve().parents[2] / "docs" / "character_manholes.ndjson"
            ))
        )

    def test_includes_the_prefecture_index_page(self) -> None:
        self.assertIn(
            "<loc>https://data.pokefuta.com/prefectures/</loc>", self.xml
        )

    def test_includes_every_prefecture_detail_page(self) -> None:
        for prefecture in MODULE.PREFECTURE_ORDER:
            slug = MODULE.PREFECTURE_SLUGS[prefecture]
            with self.subTest(prefecture=prefecture):
                self.assertIn(
                    f"<loc>https://data.pokefuta.com/prefectures/{slug}/</loc>",
                    self.xml,
                )

    def test_includes_other_static_hub_pages(self) -> None:
        for path in ("summary/", "pokemon/"):
            with self.subTest(path=path):
                self.assertIn(
                    f"<loc>https://data.pokefuta.com/{path}</loc>", self.xml
                )

    def test_includes_every_character_work_page(self) -> None:
        for page in MODULE.read_character_work_pages(
            Path(__file__).resolve().parents[2] / "docs" / "character_manholes.ndjson"
        ):
            with self.subTest(page=page.slug):
                self.assertIn(
                    f"<loc>https://data.pokefuta.com/{page.path}</loc>", self.xml
                )
        # /characters/ 自体は noindex のUIハブなので sitemap には出さない
        self.assertNotIn("<loc>https://data.pokefuta.com/characters/</loc>", self.xml)

    def test_includes_the_gundam_guide_from_its_own_dataset(self) -> None:
        docs = Path(__file__).resolve().parents[2] / "docs"
        pages = MODULE.read_character_work_pages(docs / "character_manholes.ndjson", docs / "gmanhole.ndjson")
        self.assertIn("gundam", [page.slug for page in pages])
        # ガンダムのデータを渡さなければ、ガンダムのガイドは出ない（空ページをsitemapに載せない）
        self.assertNotIn("gundam", [page.slug for page in MODULE.read_character_work_pages(docs / "character_manholes.ndjson")])

    def test_omits_character_work_page_without_active_records(self) -> None:
        xml = MODULE.build_sitemap(["1"], [], character_work_pages=[])
        self.assertNotIn("<loc>https://data.pokefuta.com/characters/</loc>", xml)
        self.assertNotIn("<loc>https://data.pokefuta.com/characters/idolmaster/</loc>", xml)

    def test_includes_the_map_page_in_every_language(self) -> None:
        """map.html は自分自身を canonical にしているので sitemap に載っていること。

        canonical をトップから map.html 自身へ直したとき（PR #452）、
        sitemap には gmanhole_map.html しか無く、本体の地図ページが
        どの言語でも1件も載っていなかった。
        """
        self.assertIn("<loc>https://data.pokefuta.com/map.html</loc>", self.xml)
        for lang in MODULE.I18N_LANGS:
            with self.subTest(lang=lang):
                self.assertIn(
                    f"<loc>https://data.pokefuta.com/{lang}/map.html</loc>", self.xml
                )

    def test_includes_manhole_and_pokemon_detail_urls(self) -> None:
        self.assertIn(
            "<loc>https://data.pokefuta.com/manholes/1/</loc>", self.xml
        )
        self.assertIn(
            "<loc>https://data.pokefuta.com/pokemon/pikachu/</loc>", self.xml
        )


class TagPageUrlTest(unittest.TestCase):
    """テーマページは生成された分だけ載せる。

    生成側（generate_tag_pages.available_tag_slugs）と同じ判定を使うので、
    レコードが無くて生成されなかったテーマの URL が sitemap に残ることはない。
    """

    def test_lists_only_the_tags_passed_in(self) -> None:
        xml = MODULE.build_sitemap(["1"], [], ["roadside", "world_heritage"])
        self.assertIn("<loc>https://data.pokefuta.com/tags/roadside/</loc>", xml)
        self.assertIn("<loc>https://data.pokefuta.com/tags/world_heritage/</loc>", xml)
        self.assertNotIn("/tags/remote_island/", xml)

    def test_omits_the_section_entirely_without_tags(self) -> None:
        self.assertNotIn("/tags/", MODULE.build_sitemap(["1"], []))

    def test_reads_tags_from_the_real_dataset(self) -> None:
        dataset = Path(__file__).resolve().parents[2] / "docs" / "pokefuta.ndjson"
        if not dataset.exists():
            self.skipTest(f"dataset not available: {dataset}")
        self.assertEqual(
            ["remote_island", "roadside", "world_heritage"],
            sorted(MODULE.read_tag_slugs(dataset)),
        )


if __name__ == "__main__":
    unittest.main()


class LastmodTest(unittest.TestCase):
    """<lastmod> はデータ（蓋の追加日・写真の投稿日）から決まるページだけに書く。

    全ページの日付が毎デプロイ進むと Google は lastmod を無視する（2026-10-24 の SERP 対策ノートの「残り」）。
    last_updated は使わず、蓋ごとに added_at と公開写真の created_at の新しい方を取る。
    """

    RECORDS = [
        {"id": "1", "prefecture": "鹿児島県", "pokemons": ["イーブイ"], "added_at": "2025-07-01T00:00:00Z",
         "last_updated": "2026-11-13T12:00:00Z", "status": "active"},
        {"id": "2", "prefecture": "鹿児島県", "pokemons": ["ピカチュウ"], "added_at": "2026-02-10T00:00:00Z",
         "last_updated": "2026-11-13T12:00:00Z", "status": "active"},
        {"id": "3", "prefecture": "宮城県", "pokemons": ["ラプラス"], "first_seen": "2026-10-20T23:30:00Z",
         "status": "active"},
        {"id": "4", "prefecture": "群馬県", "pokemons": [], "status": "active"},
    ]
    PHOTOS = {
        "1": {"created_at": "2026-09-08T01:24:20+00:00",
              "gallery": [{"created_at": "2026-10-30T20:00:00+00:00"}, {"created_at": "2026-05-01T00:00:00+00:00"}]},
    }
    JA_TO_SLUG = {"イーブイ": "eevee", "ピカチュウ": "pikachu", "ラプラス": "lapras"}

    def setUp(self) -> None:
        self.lastmods = MODULE.build_lastmods(self.RECORDS, self.PHOTOS, self.JA_TO_SLUG)
        self.xml = MODULE.build_sitemap(["1", "2", "3", "4"], ["eevee", "pikachu", "lapras"], lastmods=self.lastmods)

    def _lastmod(self, loc: str) -> str | None:
        import re
        m = re.search(r"<loc>" + re.escape(loc) + r"</loc>\n(?:    <lastmod>(.*?)</lastmod>\n)?", self.xml)
        assert m, loc
        return m.group(1)

    def test_manhole_takes_newest_of_added_at_and_representative_photo(self) -> None:
        # 代表写真（9/8）が added_at（2025-07）より新しい。ギャラリーの新しい写真（10/30）は数えない
        self.assertEqual(self._lastmod("https://data.pokefuta.com/manholes/1/"), "2026-09-08")
        self.assertNotIn("2026-10-31", self.xml)
        # 写真が無い蓋は added_at
        self.assertEqual(self._lastmod("https://data.pokefuta.com/manholes/2/"), "2026-02-10")
        # added_at が無ければ first_seen。UTC 23:30 は JST の翌日
        self.assertEqual(self._lastmod("https://data.pokefuta.com/manholes/3/"), "2026-10-21")

    def test_last_updated_is_ignored_and_dateless_pages_have_no_lastmod(self) -> None:
        self.assertNotIn("2026-11-13", self.xml)
        self.assertIsNone(self._lastmod("https://data.pokefuta.com/manholes/4/"))
        self.assertIsNone(self._lastmod("https://data.pokefuta.com/prefectures/gunma/"))
        self.assertIsNone(self._lastmod("https://data.pokefuta.com/privacy.html"))

    def test_prefecture_and_top_take_the_newest_lid_in_scope(self) -> None:
        self.assertEqual(self._lastmod("https://data.pokefuta.com/prefectures/kagoshima/"), "2026-09-08")
        self.assertEqual(self._lastmod("https://data.pokefuta.com/prefectures/miyagi/"), "2026-10-21")
        self.assertEqual(self._lastmod("https://data.pokefuta.com/"), "2026-10-21")
        self.assertEqual(self._lastmod("https://data.pokefuta.com/prefectures/"), "2026-10-21")

    def test_pokemon_and_translated_pages_follow_the_japanese_page(self) -> None:
        self.assertEqual(self._lastmod("https://data.pokefuta.com/pokemon/pikachu/"), "2026-02-10")
        self.assertEqual(self._lastmod("https://data.pokefuta.com/en/pokemon/eevee/"), "2026-09-08")
        self.assertEqual(self._lastmod("https://data.pokefuta.com/en/manholes/1/"), "2026-09-08")
        self.assertEqual(self._lastmod("https://data.pokefuta.com/zh-TW/prefectures/kagoshima/"), "2026-09-08")

    def test_summary_ignores_provisional_lids(self) -> None:
        # /summary/ は公式の docs/pokefuta.ndjson だけから作る。仮番号（provisional）の蓋が増えても中身は変わらないので、
        # トップ・県・一覧は進んでも /summary/ の lastmod は公式の最新のまま（Copilot の指摘、PR #864）
        records = self.RECORDS + [{"id": "9001", "prefecture": "宮城県", "pokemons": [], "provisional": True,
                                   "added_at": "2026-11-12T00:00:00Z", "status": "active"}]
        xml = MODULE.build_sitemap(["1", "2", "3", "4", "9001"], [], lastmods=MODULE.build_lastmods(records, self.PHOTOS, self.JA_TO_SLUG))
        import re
        get = lambda loc: re.search(r"<loc>" + re.escape(loc) + r"</loc>\n    <lastmod>(.*?)</lastmod>", xml).group(1)
        self.assertEqual(get("https://data.pokefuta.com/"), "2026-11-12")
        self.assertEqual(get("https://data.pokefuta.com/prefectures/miyagi/"), "2026-11-12")
        self.assertEqual(get("https://data.pokefuta.com/summary/"), "2026-10-21")

    def test_without_lastmods_nothing_changes(self) -> None:
        self.assertNotIn("<lastmod>", MODULE.build_sitemap(["1"], ["pikachu"]))

    def test_load_photos_accepts_the_import_output_shape(self) -> None:
        import json, tempfile
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "p.json"
            path.write_text(json.dumps({"photos": {"7": {"created_at": "2026-01-01T00:00:00Z"}}}), encoding="utf-8")
            self.assertEqual(list(MODULE.load_photos(path)), ["7"])
            self.assertEqual(MODULE.load_photos(Path(tmp) / "missing.json"), {})

