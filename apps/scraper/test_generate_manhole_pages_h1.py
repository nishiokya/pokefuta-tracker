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
        html = _generate(_manhole(
            building="道の駅とよはし",
            place_label="豊橋市 道の駅とよはし",
        ))
        self.assertEqual(_h1(html), "豊橋市 道の駅とよはしのポケふた（スターミー・デンヂムシ）")

    def test_h1_without_building_uses_title(self):
        # 施設名が無い一意な蓋は place_label が無く、正本の名前は title（地図の見出しと同じ）
        html = _generate(_manhole(title="愛知県/豊橋市"))
        self.assertEqual(_h1(html), "愛知県/豊橋市のポケふた（スターミー・デンヂムシ）")

    def test_title_tag_leads_with_building(self):
        # 検索結果の title にも施設名を出す（2026-10 の Search Console で詳細ページは CTR 1.8% と種類別で最低。
        # 「愛知県豊橋のポケふた」では h1 にある施設名が検索結果から見えなかった）
        html = _generate(_manhole(building="道の駅とよはし"))
        self.assertIn(
            "<title>道の駅とよはしのポケふた（スターミー・デンヂムシ）｜愛知県豊橋市の場所・写真・行き方｜ポケふた図鑑</title>",
            html,
        )
        # 説明文は定型文ではなく住所で書く。写真が無い蓋は募集中と書く
        self.assertIn(
            '<meta name="description" content="愛知県豊橋市の道の駅とよはしにあるポケふた（スターミー・デンヂムシ）。'
            "住所は愛知県豊橋市東七根町一の沢113-2。地図とGoogleマップの経路案内、周辺のポケふたを掲載。写真は募集中。\"",
            html,
        )
        # og:/twitter: は SNS 向けの短い形のまま
        self.assertIn('og:title" content="豊橋のポケふた｜スターミー・デンヂムシ｜ポケふた図鑑"', html)

    def test_title_tag_without_building_keeps_municipality_form(self):
        # 施設名が無い蓋（約170枚）は「県市のポケふた」の形。市区町村名は title/地図と同じ接尾辞つき
        html = _generate(_manhole(title="愛知県/豊橋市"))
        self.assertIn("<title>愛知県豊橋市のポケふた（スターミー・デンヂムシ）｜場所・写真・行き方｜ポケふた図鑑</title>", html)
        self.assertIn('content="愛知県豊橋市にあるポケふた（スターミー・デンヂムシ）。住所は', html)

    def test_title_tag_rounds_long_pokemon_lists(self):
        # 5匹の蓋は og: と同じ「3匹＋ほか」に丸めて title を伸ばさない。説明文は全部の名前を残す
        html = _generate(_manhole(
            building="道の駅とよはし",
            pokemons=["ピカチュウ", "イーブイ", "カビゴン", "ヤドン", "ラプラス"],
        ))
        self.assertIn("<title>道の駅とよはしのポケふた（ピカチュウ・イーブイ・カビゴン ほか）｜", html)
        self.assertIn("ポケふた（ピカチュウ・イーブイ・カビゴン・ヤドン・ラプラス）。住所は", html)

    def test_long_building_title_drops_prefecture_then_pokemon(self):
        # 施設名が長いときは県名→ポケモン名の順に削って収める。施設名と市区町村名は残す
        html = _generate(_manhole(
            building="刈谷ハイウェイオアシス内にある「オアシス館刈谷 INFOBOX」正面玄関前",
            city="刈谷", title="愛知県/刈谷市", pokemons=["キバゴ", "ジュカイン", "タツベイ"],
        ))
        title = re.search(r"<title>(.*?)</title>", html).group(1)
        self.assertTrue(title.startswith("刈谷ハイウェイオアシス内にある「オアシス館刈谷 INFOBOX」正面玄関前のポケふた"))
        self.assertRegex(title, r"｜刈谷市?の場所・写真・行き方｜ポケふた図鑑$")
        self.assertNotIn("愛知県", title)
        self.assertNotIn("キバゴ", title)
        # 少し長いだけなら県名を落とすだけで、ポケモン名は残る
        html = _generate(_manhole(building="下呂市観光交流センター「湯めぐり館」", prefecture="岐阜県", city="下呂市",
                                  title="岐阜県/下呂市", pokemons=["コイキング", "ヤドン"]))
        self.assertIn(
            "<title>下呂市観光交流センター「湯めぐり館」のポケふた（コイキング・ヤドン）｜下呂市の場所・写真・行き方｜ポケふた図鑑</title>",
            html,
        )

    def test_description_counts_public_photos(self):
        html = pages.generate_html(
            manhole=_manhole(building="道の駅とよはし"),
            photo={"url": "https://img.example/a.jpg", "public_photo_count": 24},
            pokemon_meta={}, nearby=[], same_pref=[], pref_total=0, same_pokemon=[], id_to_image_url={},
        )
        self.assertIn("訪れた人の現地写真24枚と地図、Googleマップの経路案内、周辺のポケふたを掲載。", html)
        self.assertNotIn("写真は募集中", html.split("</head>", 1)[0])

    def test_preinstall_title_says_planned_not_directions(self):
        # 設置前の蓋は「行き方」「写真」をうたわず、設置予定と公式の時期を書く
        html = _generate(_manhole(installed=False, installation_note="2026年11月15日(日) 午前10時ごろ設置予定。"))
        self.assertIn("<title>愛知県豊橋市のポケふた（スターミー・デンヂムシ）｜設置予定｜ポケふた図鑑</title>", html)
        self.assertIn(
            'content="愛知県豊橋市に設置予定のポケふた（スターミー・デンヂムシ）。2026年11月15日(日) 午前10時ごろ設置予定。'
            '設置場所の地図と、同じ県のポケふたを掲載。"',
            html,
        )

    def test_building_is_normalized_like_map(self):
        # 全角スペースや先頭の自治体名は地図の place_label と同じ規則で整える
        html = _generate(_manhole(
            building="豊橋市　道の駅とよはし",
            place_label="豊橋市 道の駅とよはし",
        ))
        self.assertIn("豊橋市 道の駅とよはしのポケふた", _h1(html))

    def test_location_row_is_normalized_like_h1(self):
        # 「施設・場所」欄も見出しと同じ書き方にする（全角スペース・先頭の自治体名を整える）
        html = _generate(_manhole(id="404", prefecture="愛知県", city="名古屋市中区",
                                  address="愛知県名古屋市中区二の丸1番2・3号",
                                  building="金シャチ横丁　宗春ゾーン（東門エリア）"))
        self.assertIn("<dd>金シャチ横丁 宗春ゾーン（東門エリア）</dd>", html)
        html = _generate(_manhole(id="9", prefecture="鹿児島県", city="指宿",
                                  address="鹿児島県指宿市十町1003", building="指宿市 指宿図書館"))
        self.assertIn("<dd>指宿図書館</dd>", html)

    def test_ambiguous_place_does_not_repeat_pokemon(self):
        # 場所で区別できない蓋は名前にポケモン名が入るので、h1 で二重に付けない
        html = _generate(_manhole(
            title="愛知県/豊橋市",
            place_label="豊橋市",
            place_ambiguous=True,
        ))
        self.assertEqual(_h1(html), "豊橋市（スターミー・デンヂムシ）のポケふた")


if __name__ == "__main__":
    unittest.main()
