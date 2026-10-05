import importlib.util
import json
import re
import unittest
from pathlib import Path

MODULE_PATH = Path(__file__).with_name("generate_manhole_pages.py")
SPEC = importlib.util.spec_from_file_location("generate_manhole_pages", MODULE_PATH)
pages = importlib.util.module_from_spec(SPEC)
assert SPEC and SPEC.loader
SPEC.loader.exec_module(pages)


def _manhole(**overrides) -> dict:
    base = {
        "id": "98",
        "prefecture": "東京都",
        "city": "町田",
        "address": "東京都町田市原町田6丁目",
        "lat": 35.54,
        "lng": 139.44,
        "pokemons": ["ピカチュウ"],
        "titles": [],
        "tags": [],
    }
    base.update(overrides)
    return base


def _generate(manhole: dict, municipality_path: str | None = None) -> str:
    return pages.generate_html(
        manhole=manhole,
        photo=None,
        pokemon_meta={},
        nearby=[],
        same_pref=[],
        pref_total=0,
        same_pokemon=[],
        id_to_image_url={},
        municipality_path=municipality_path,
    )


def _jsonld(html: str) -> list:
    block = re.search(r'<script type="application/ld\+json">(.*?)</script>', html, re.S).group(1)
    return json.loads(block)


def _breadcrumb(html: str) -> list[dict]:
    lists = [d for d in _jsonld(html) if d.get("@type") == "BreadcrumbList"]
    assert len(lists) == 1
    return lists[0]["itemListElement"]


def _nav(html: str) -> str:
    return re.search(r'<nav class="hero-region" aria-label="パンくず">(.*?)</nav>', html).group(1)


class DetailBreadcrumbTests(unittest.TestCase):
    def test_breadcrumb_goes_through_municipality_page(self):
        html = _generate(_manhole(), municipality_path="/municipalities/tokyo/machida/")
        items = _breadcrumb(html)
        self.assertEqual([i["position"] for i in items], [1, 2, 3, 4])
        self.assertEqual(items[0]["item"], "https://data.pokefuta.com/")
        self.assertEqual(items[1], {"@type": "ListItem", "position": 2, "name": "東京都",
                                    "item": "https://data.pokefuta.com/prefectures/tokyo/"})
        self.assertEqual(items[2]["item"], "https://data.pokefuta.com/municipalities/tokyo/machida/")
        self.assertNotIn("item", items[3])  # 最後（このページ自身）は URL を付けない
        self.assertEqual(items[3]["name"], re.search(r'<h1 class="hero-title">(.*?)</h1>', html).group(1))
        # 画面のパンくずも同じリンク先
        nav = _nav(html)
        self.assertIn('<a href="/prefectures/tokyo/">東京都</a>', nav)
        self.assertIn('<a href="/municipalities/tokyo/machida/">町田市</a>', nav)
        self.assertEqual(items[2]["name"], "町田市")

    def test_city_without_page_is_plain_text(self):
        html = _generate(_manhole(id="308", prefecture="三重県", city="名張",
                                  address="三重県名張市"))
        self.assertEqual([i["name"] for i in _breadcrumb(html)][:2], ["全国マップ", "三重県"])
        self.assertEqual(len(_breadcrumb(html)), 3)
        nav = _nav(html)
        self.assertIn("<span>名張</span>", nav)
        self.assertNotIn("municipalities", nav)

    def test_tourist_attraction_is_kept(self):
        types = [d["@type"] for d in _jsonld(_generate(_manhole()))]
        self.assertEqual(types, ["TouristAttraction", "BreadcrumbList"])


if __name__ == "__main__":
    unittest.main()
