"""日本語ポケモンページのタイトル・説明文・要約が、実際の設置場所から組み立てられることを固定する。"""

import json
import re
import unittest
from pathlib import Path

from apps.scraper.generate_pokemon_pages import (
    LANG_CONFIGS,
    LP_STRINGS,
    build_co_featured_map,
    generate_html,
    ja_page_title,
)


def _manhole(mid: str, prefecture: str, city: str, address: str, pokemons: list[str], **extra) -> dict:
    return {"id": mid, "prefecture": prefecture, "city": city, "address": address,
            "title": f"{prefecture}/{city}", "pokemons": pokemons, **extra}


YOKOHAMA = _manhole("314", "神奈川県", "横浜", "神奈川県横浜市西区みなとみらい2丁目1-1",
                    ["コダック", "ピカチュウ", "ワンリキー"],
                    building="日本丸メモリアルパーク", place_label="横浜市 日本丸メモリアルパーク")
SAKURAGICHO = _manhole("300", "神奈川県", "横浜", "神奈川県横浜市中区桜木町1丁目",
                       ["ピカチュウ"], building="桜木町駅前", place_label="横浜市 桜木町駅前")
UJI = _manhole("400", "京都府", "宇治", "京都府宇治市小倉町神楽田56",
               ["ピカチュウ"], building="ニンテンドーミュージアム", place_label="宇治市 ニンテンドーミュージアム")
NISHIGO = _manhole("120", "福島県", "西郷", "福島県西白河郡西郷村大字小田倉", ["ウパー"])

PSYDUCK = {"slug": "psyduck", "names": {"ja": "コダック", "en": "Psyduck"}}
PIKACHU = {"slug": "pikachu", "names": {"ja": "ピカチュウ", "en": "Pikachu"}}


def _html(pokemon: dict, manholes: list[dict], lang: str = "ja", co_featured=None) -> str:
    return generate_html(
        slug=pokemon["slug"],
        pokemon=pokemon,
        manholes=manholes,
        related=[],
        taxonomy_related={},
        image_dir=Path("/nonexistent"),
        lang=lang,
        lang_config=LANG_CONFIGS[lang],
        strings=LP_STRINGS[lang],
        translate_pref=lambda pref: pref,
        co_featured=co_featured,
    )


def _title(html: str) -> str:
    return re.search(r"<title>(.*?)</title>", html).group(1)


def _description(html: str) -> str:
    return re.search(r'<meta name="description" content="([^"]*)"', html).group(1)


class JaTitleTests(unittest.TestCase):
    def test_single_lid_names_the_municipality(self):
        self.assertEqual(ja_page_title("コダック", [YOKOHAMA]),
                         "コダックのポケふたは神奈川県横浜市に1枚｜場所・写真・地図")

    def test_one_prefecture_lists_municipalities(self):
        self.assertEqual(ja_page_title("ピカチュウ", [YOKOHAMA, SAKURAGICHO]),
                         "ピカチュウのポケふた2枚｜神奈川県横浜市の場所一覧・地図")

    def test_few_prefectures_are_listed_by_count(self):
        self.assertEqual(ja_page_title("ピカチュウ", [UJI, YOKOHAMA, SAKURAGICHO]),
                         "ピカチュウのポケふた3枚｜神奈川・京都の場所一覧・地図")

    def test_many_prefectures_are_summarized_north_first(self):
        lids = [_manhole(str(i), p, "", "", ["メタモン"]) for i, p in
                enumerate(["三重県", "香川県", "北海道", "宮城県"])]
        self.assertEqual(ja_page_title("メタモン", lids),
                         "メタモンのポケふた4枚｜北海道・宮城など4都道府県の場所一覧・地図")


class JaPageContentTests(unittest.TestCase):
    def test_description_and_summary_use_the_place_and_co_featured_pokemon(self):
        html = _html(PSYDUCK, [YOKOHAMA])
        self.assertEqual(
            _description(html),
            "コダックのポケふた（ポケモンマンホール）は神奈川県横浜市の日本丸メモリアルパークにあります。"
            "ピカチュウ・ワンリキーと一緒に描かれています。設置場所の地図と投稿写真を掲載しています。",
        )
        self.assertIn("コダックのポケふたは全国に1枚、横浜市 日本丸メモリアルパークにあります。"
                      "この蓋にはピカチュウ・ワンリキーも描かれています。", html)

    def test_lid_without_landmark_is_written_without_slash(self):
        html = _html({"slug": "wooper", "names": {"ja": "ウパー"}}, [NISHIGO])
        self.assertNotIn("/", _title(html) + _description(html))
        self.assertIn("福島県西郷村", _description(html))

    def test_item_list_links_every_lid(self):
        html = _html(PIKACHU, [UJI, YOKOHAMA])
        blocks = [json.loads(b) for b in
                  re.findall(r'<script type="application/ld\+json">(.*?)</script>', html, re.S)]
        items = blocks[0]["mainEntity"]["itemListElement"]
        self.assertEqual(blocks[0]["mainEntity"]["numberOfItems"], 2)
        self.assertEqual({i["url"] for i in items}, {"https://data.pokefuta.com/manholes/400/",
                                                     "https://data.pokefuta.com/manholes/314/"})
        self.assertIn({"@type": "ListItem", "position": 1, "name": "宇治市 ニンテンドーミュージアムのポケふた",
                       "url": "https://data.pokefuta.com/manholes/400/"}, items)

    def test_co_featured_replaces_same_generation(self):
        html = generate_html(
            slug="psyduck", pokemon=PSYDUCK, manholes=[YOKOHAMA], related=[],
            taxonomy_related={"same_generation": [("lapras", {"names": {"ja": "ラプラス"}})]},
            image_dir=Path("/nonexistent"), lang="ja", lang_config=LANG_CONFIGS["ja"],
            strings=LP_STRINGS["ja"], translate_pref=lambda p: p,
            co_featured=[("pikachu", PIKACHU)],
        )
        self.assertIn("<h2>コダックと一緒に描かれているポケモン</h2>", html)
        self.assertIn("href='/pokemon/pikachu/'", html)
        self.assertNotIn("同じ世代のポケモン", html)

    def test_other_languages_keep_their_templates(self):
        html = _html(PSYDUCK, [YOKOHAMA], lang="en")
        self.assertEqual(_title(html), "Psyduck Poké Lids | Pokémon Manhole Map of Japan")
        self.assertNotIn("mainEntity", html)


class CoFeaturedMapTests(unittest.TestCase):
    def test_pokemon_on_the_same_lid_link_each_other(self):
        index = {"psyduck": (PSYDUCK, [YOKOHAMA]), "pikachu": (PIKACHU, [YOKOHAMA, UJI])}
        result = build_co_featured_map(index)
        self.assertEqual([s for s, _ in result["psyduck"]], ["pikachu"])
        self.assertEqual([s for s, _ in result["pikachu"]], ["psyduck"])


if __name__ == "__main__":
    unittest.main()
