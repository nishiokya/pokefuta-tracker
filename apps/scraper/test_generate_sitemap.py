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
