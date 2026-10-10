"""404 ページ（apps/web/404.html）。ヤドン1体のポケふた（id 40）を固定で出す。

写真館（nishiokya/pokefuta の src/app/not-found.tsx）も同じ1枚・同じ見た目にしてある。
"""

from __future__ import annotations

import json
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PAGE = ROOT / "apps" / "web" / "404.html"
DATASET = ROOT / "docs" / "pokefuta.ndjson"
IMAGES = ROOT / "dataset" / "manhole" / "image"
SLOWPOKE_ID = "40"


class PageTest(unittest.TestCase):
    def setUp(self) -> None:
        self.html = PAGE.read_text(encoding="utf-8")

    def test_slowpoke_lid_still_exists(self) -> None:
        """出しているヤドンが設置済みのまま・ヤドン1体のまま・蓋の画像があること。"""
        record = next(
            json.loads(line) for line in DATASET.read_text(encoding="utf-8").splitlines()
            if line.strip() and str(json.loads(line)["id"]) == SLOWPOKE_ID
        )
        self.assertIsNot(record.get("installed"), False)
        self.assertEqual(["ヤドン"], record.get("pokemons"))
        self.assertIn(record["title"].replace("/", ""), self.html)
        self.assertTrue((IMAGES / f"{SLOWPOKE_ID}_lid.jpeg").exists())
        self.assertIn(f'src="./manhole/image/{SLOWPOKE_ID}_lid.jpeg"', self.html)
        self.assertIn(f'href="./manholes/{SLOWPOKE_ID}/"', self.html)

    def test_links_resolve_from_the_site_root_at_any_depth(self) -> None:
        """GitHub Pages はどの深さの URL にも 404.html を返すので base を固定する。"""
        self.assertIn('<base href="/">', self.html)
        self.assertIn('<meta name="robots" content="noindex">', self.html)

    def test_three_destinations_and_pokefuta_links_carry_from_data(self) -> None:
        links = re.findall(r'<a class="lost__link" href="([^"]+)"[^>]*data-destination="([^"]+)"', self.html)
        self.assertEqual([
            ("./", "dex"),
            ("https://pokefuta.com/?from=data", "album"),
            ("https://pokefuta.com/design-manholes?from=data", "design"),
        ], links)

    def test_lid_spin_is_wired_to_the_lid_and_its_link(self) -> None:
        """回す動きそのものは assets/lid-spin.test.js（node）が見る。ここは 404 との繋ぎだけ。"""
        self.assertIn('<script src="./assets/lid-spin.js?v=', self.html)
        self.assertIn("PokefutaLidSpin.bind(document.getElementById('lost-lid'), document.getElementById('lost-pick')", self.html)
        self.assertIn('id="lost-lid"', self.html)
        self.assertIn('id="lost-pick"', self.html)
        self.assertIn('draggable="false"', self.html)
        css = (ROOT / "apps" / "web" / "assets" / "not-found.css").read_text(encoding="utf-8")
        # スクロールは止めるがピンチでの拡大は止めない
        self.assertRegex(css, r"@media \(pointer: coarse\) \{\s*\.lost__lid \{[^}]*touch-action: pinch-zoom;")
        self.assertNotIn("touch-action: none", css)

if __name__ == "__main__":
    unittest.main()
