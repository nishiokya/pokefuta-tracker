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
        self.xml = MODULE.build_sitemap(["1", "2"], ["pikachu"])

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


if __name__ == "__main__":
    unittest.main()
