import importlib.util
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
        "id": "273",
        "prefecture": "愛知県",
        "city": "豊橋",
        "address": "愛知県豊橋市東七根町一の沢113-2",
        "lat": 34.69,
        "lng": 137.41,
        "pokemons": ["スターミー", "デンヂムシ"],
        "titles": [],
        "tags": [],
    }
    base.update(overrides)
    return base


def _generate(manhole: dict) -> str:
    return pages.generate_html(
        manhole=manhole,
        photo=None,
        pokemon_meta={},
        nearby=[],
        same_pref=[],
        pref_total=0,
        same_pokemon=[],
        id_to_image_url={},
    )


def _h1(html: str) -> str:
    return re.search(r'<h1 class="hero-title">(.*?)</h1>', html).group(1)


class DetailH1Tests(unittest.TestCase):
    def test_h1_includes_building(self):
        # 地図の見出し（豊橋市 道の駅とよはし）と同じく施設名を出す
        html = _generate(_manhole(building="道の駅とよはし"))
        self.assertEqual(_h1(html), "愛知県豊橋 道の駅とよはしのポケふた（スターミー・デンヂムシ）")

    def test_h1_without_building_is_unchanged(self):
        html = _generate(_manhole())
        self.assertEqual(_h1(html), "愛知県豊橋のポケふた（スターミー・デンヂムシ）")

    def test_title_tag_keeps_search_form(self):
        # <title> は検索向けの「県市のポケふた」の形を保つ
        html = _generate(_manhole(building="道の駅とよはし"))
        self.assertIn("<title>愛知県豊橋のポケふた｜スターミー・デンヂムシ | data.pokefuta.com</title>", html)

    def test_building_is_normalized_like_map(self):
        # 全角スペースや先頭の自治体名は地図の place_label と同じ規則で整える
        html = _generate(_manhole(building="豊橋市　道の駅とよはし"))
        self.assertIn("愛知県豊橋 道の駅とよはしのポケふた", _h1(html))

    def test_location_row_is_normalized_like_h1(self):
        # 「施設・場所」欄も見出しと同じ書き方にする（全角スペース・先頭の自治体名を整える）
        html = _generate(_manhole(id="404", prefecture="愛知県", city="名古屋市中区",
                                  address="愛知県名古屋市中区二の丸1番2・3号",
                                  building="金シャチ横丁　宗春ゾーン（東門エリア）"))
        self.assertIn("<dd>金シャチ横丁 宗春ゾーン（東門エリア）</dd>", html)
        html = _generate(_manhole(id="9", prefecture="鹿児島県", city="指宿",
                                  address="鹿児島県指宿市十町1003", building="指宿市 指宿図書館"))
        self.assertIn("<dd>指宿図書館</dd>", html)


if __name__ == "__main__":
    unittest.main()
