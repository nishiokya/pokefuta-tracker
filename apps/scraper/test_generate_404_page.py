"""404 ページの候補（有名なポケモンが1体だけのポケふた）と焼き込みのテスト。"""

from __future__ import annotations

import json
import re
import tempfile
import unittest
from pathlib import Path

from apps.scraper import generate_404_page as module

ROOT = Path(__file__).resolve().parents[2]
PAGE = ROOT / "apps" / "web" / "404.html"


class CandidateTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp())
        self.images = self.tmp / "image"
        self.images.mkdir()

    def _dataset(self, *records: dict) -> Path:
        path = self.tmp / "pokefuta.ndjson"
        path.write_text("\n".join(json.dumps(r, ensure_ascii=False) for r in records), encoding="utf-8")
        for r in records:
            (self.images / f"{r['id']}_lid.jpeg").write_bytes(b"x")
        return path

    def test_only_installed_single_famous_pokemon_with_a_lid_image(self) -> None:
        dataset = self._dataset(
            {"id": "40", "pokemons": ["ヤドン"], "title": "香川県/高松市", "installed": True},
            {"id": "41", "pokemons": ["ヤドン", "ヤドラン"], "title": "香川県/坂出市", "installed": True},
            {"id": "42", "pokemons": ["ツボツボ"], "title": "鹿児島県/指宿市", "installed": True},
            {"id": "43", "pokemons": ["ピカチュウ"], "title": "福島県/小野町", "installed": False},
            {"id": "44", "pokemons": ["ラプラス"], "title": "宮城県/石巻市", "installed": True},
        )
        (self.images / "44_lid.jpeg").unlink()
        items = module.load_candidates(dataset, self.images)
        self.assertEqual([{"id": "40", "pokemon": "ヤドン", "place": "香川県高松市"}], items)


class CommittedPageTest(unittest.TestCase):
    def setUp(self) -> None:
        self.html = PAGE.read_text(encoding="utf-8")

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

    def test_regenerating_keeps_markers_and_valid_json(self) -> None:
        block = module.render_block([{"id": "40", "pokemon": "ヤドン", "place": "香川県高松市"}])
        html = module.BLOCK_RE.sub(lambda _: block, self.html, count=1)
        self.assertIn("<!-- not-found:pick:start -->", html)
        data = re.search(r'<script type="application/json" id="lost-data">(.*?)</script>', html).group(1)
        self.assertEqual("ヤドン", json.loads(data)["items"][0]["pokemon"])

    def test_default_pick_is_a_current_candidate(self) -> None:
        """JS が動かないときの初期表示（ヤドン id 28）が、今の候補に入っていること。"""
        self.assertIn('href="./manholes/28/"', self.html)
        ids = {it["id"] for it in module.load_candidates()}
        self.assertIn("28", ids)


if __name__ == "__main__":
    unittest.main()
