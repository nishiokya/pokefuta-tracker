from __future__ import annotations

import importlib.util
import tempfile
import unittest
from pathlib import Path

MODULE_PATH = Path(__file__).with_name("generate_prefecture_pages.py")
SPEC = importlib.util.spec_from_file_location("generate_prefecture_pages", MODULE_PATH)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC and SPEC.loader
SPEC.loader.exec_module(MODULE)


class GeneratePrefecturePagesTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.records = MODULE.load_records(MODULE.DEFAULT_MANHOLES)
        cls.pokemon_slugs = MODULE.load_pokemon_slugs(MODULE.DEFAULT_POKEMON)
        cls.trivia = MODULE.load_trivia(MODULE.DEFAULT_TRIVIA)

    def test_generates_all_47_prefectures_including_empty(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory)
            count = MODULE.generate_all(
                self.records, self.pokemon_slugs, self.trivia, output
            )
            self.assertEqual(47, count)
            self.assertEqual(47, len(list(output.glob("*/index.html"))))
            gunma = (output / "gunma" / "index.html").read_text(encoding="utf-8")
            self.assertIn("現在未設置", gunma)
            self.assertIn("canonical", gunma)

    def test_fukui_page_has_required_sections_and_links(self) -> None:
        records = [r for r in self.records if r.get("prefecture") == "福井県"]
        html = MODULE.build_page(
            "福井県",
            "fukui",
            records,
            MODULE.build_rankings(self.records)["福井県"],
            self.pokemon_slugs,
            self.trivia["福井県"],
        )
        self.assertIn("福井県のポケふた17枚", html)
        self.assertIn("福井県の設置マップ", html)
        self.assertIn("福井県で会えるポケモン", html)
        self.assertIn("福井県のマンホール一覧", html)
        self.assertIn("福井県のポケふたトリビア", html)
        self.assertIn("/pokemon/dragonite/", html)
        self.assertIn("/manholes/", html)
        self.assertIn("prefecture_manhole_click", html)
        self.assertIn(
            "旅行やポケふた巡りの計画にご活用ください。",
            html,
        )
        self.assertLess(
            html.index('id="trivia-heading"'),
            html.index('id="map-heading"'),
        )
        self.assertIn("まず知りたい", html)
        self.assertIn(
            "福井県には17枚のポケふたがあります。県内16自治体に広がっています。",
            html,
        )
        self.assertIn("https://pokefuta.com/visits", html)
        self.assertIn('href="https://pokefuta.com/"', html)
        self.assertIn("prefecture_visit_cta_click", html)
        self.assertIn("prefecture_photo_cta_click", html)
        self.assertIn("'page_path': '/prefectures/' + \"fukui\" + '/'", html)
        self.assertIn("site_type: 'map'", html)
        self.assertLess(
            html.index('id="manhole-heading"'),
            html.index('id="pokemon-heading"'),
        )
        self.assertIn("ほか13種類のポケモンを見る", html)
        self.assertEqual(25, html.count('class="pokemon-card"'))
        first_pokemon_section = html[
            html.index('<div class="pokemon-grid">'):
            html.index('<details class="pokemon-more">')
        ]
        self.assertEqual(12, first_pokemon_section.count('class="pokemon-card"'))

    def test_empty_prefecture_meta_description_is_complete(self) -> None:
        html = MODULE.build_page(
            "群馬県",
            "gunma",
            [],
            None,
            self.pokemon_slugs,
            self.trivia["群馬県"],
        )
        self.assertIn(
            "現在の設置枚数や全国のポケモンマンホール情報を確認できます。",
            html,
        )
        self.assertLess(
            html.index('id="trivia-heading"'),
            html.index('id="map-heading"'),
        )
        self.assertIn(
            "群馬県では、現在ポケふたの設置を確認できていません。",
            html,
        )

    def test_tied_counts_share_rank(self) -> None:
        records = [
            {"id": "1", "status": "active", "prefecture": "青森県"},
            {"id": "2", "status": "active", "prefecture": "岩手県"},
            {"id": "3", "status": "active", "prefecture": "宮城県"},
            {"id": "4", "status": "active", "prefecture": "宮城県"},
        ]
        ranks = MODULE.build_rankings(records)
        self.assertEqual(1, ranks["宮城県"])
        self.assertEqual(2, ranks["青森県"])
        self.assertEqual(2, ranks["岩手県"])
        self.assertIsNone(ranks["秋田県"])


if __name__ == "__main__":
    unittest.main()
