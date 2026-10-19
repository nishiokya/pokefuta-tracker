from __future__ import annotations

import unittest
from pathlib import Path

from apps.scraper import generate_manhole_pages as ja

ROOT = Path(__file__).resolve().parents[2]


class RegionalFormMetadataTest(unittest.TestCase):
    """詳細ページの「登場ポケモン」のタイプ・世代で、通常種とリージョンフォームを取り違えない。

    メタデータの日本語名は通常種もリージョンフォームも同じ（ロコン）。日本語名だけで
    索引を作ると後から来たアローラ・ガラル・ヒスイが通常種を上書きしていた。
    """

    @classmethod
    def setUpClass(cls) -> None:
        cls.meta = ja.load_pokemon_metadata(ROOT / "docs" / "pokemon_metadata.json")

    def types(self, name: str) -> list[str]:
        return [t["ja"] for t in self.meta[name]["types"]]

    def test_base_forms_keep_their_own_type_and_generation(self) -> None:
        self.assertEqual(["ほのお"], self.types("ロコン"))
        self.assertEqual(1, self.meta["ロコン"]["generation"])
        self.assertEqual(["みず", "エスパー"], self.types("ヤドン"))
        self.assertEqual(1, self.meta["ピカチュウ"]["generation"])

    def test_regional_forms_are_found_by_their_prefixed_name(self) -> None:
        self.assertEqual(["こおり"], self.types("アローラロコン"))
        self.assertEqual(7, self.meta["アローラロコン"]["generation"])
        self.assertEqual(["エスパー"], self.types("ガラルヤドン"))
        self.assertIn("ヒスイガーディ", self.meta)


if __name__ == "__main__":
    unittest.main()
