import tempfile
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from generate_pokemon_index_page import _build_latest_photo_cards
from generate_pokemon_index_page import generate_html
from generate_pokemon_index_page import LP_INDEX_STRINGS
from generate_pokemon_pages import LANG_CONFIGS


class LatestPhotoCardsTest(unittest.TestCase):
    def test_uses_shared_manhole_path_and_localized_pokemon_names(self):
        manhole = {
            "id": "42",
            "title": "香川県/高松市",
            "prefecture": "香川県",
            "city": "高松市",
            "pokemons": ["ヤドン"],
        }
        pokemon_index = {
            "slowpoke": (
                {"names": {"ja": "ヤドン", "en": "Slowpoke"}},
                [manhole],
            ),
            "pikachu": (
                {"names": {"ja": "ピカチュウ", "en": "Pikachu"}},
                [manhole],
            ),
        }
        photos_data = {
            "photos": {
                "42": {
                    "manhole_id": 42,
                    "url": "https://example.com/slowpoke.jpg",
                    "created_at": "2026-06-13T00:00:00Z",
                    "display_name": "とても長い名前の投稿者さんイーブイ推し団長",
                    "public_user_id": "6096691c-eeda-4e73-8401-a11274868ede",
                },
            },
        }
        lang_config = {"name_key": "en", "pref_joiner": " / "}

        with tempfile.TemporaryDirectory() as tmpdir:
            cards = _build_latest_photo_cards(
                pokemon_index,
                photos_data,
                Path(tmpdir),
                lang_config,
                lambda pref: "Kagawa",
                "en",
            )

        self.assertEqual(len(cards), 1)
        self.assertEqual(cards[0]["href"], "/manholes/42/")
        self.assertEqual(cards[0]["title"], "Slowpoke / Pikachu")
        self.assertEqual(cards[0]["location"], "Kagawa 高松市")
        # 日付はロケール表記（UTC 00:00 → JST 同日）、投稿者名は 20 文字で省略
        self.assertEqual(cards[0]["date"], "Jun 13")
        self.assertEqual(cards[0]["poster"], "とても長い名前の投稿者さんイーブイ推し…")
        self.assertEqual(
            cards[0]["poster_profile_url"],
            "https://pokefuta.com/users/6096691c-eeda-4e73-8401-a11274868ede/visits",
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            html = generate_html(
                pokemon_index,
                "en",
                LANG_CONFIGS["en"],
                LP_INDEX_STRINGS["en"],
                lambda pref: "Kagawa",
                photos_data,
                Path(tmpdir),
            )
        self.assertIn('<article class="photo-card">', html)
        self.assertIn(
            'href="https://pokefuta.com/users/'
            '6096691c-eeda-4e73-8401-a11274868ede/visits"',
            html,
        )
        self.assertIn('class="poster-link"', html)
        self.assertNotIn("さんの公開スタンプ帳を開く", html)

    def test_pokemon_index_does_not_render_hero_summary_panel(self):
        pokemon_index = {
            "slowpoke": (
                {"names": {"ja": "ヤドン", "en": "Slowpoke"}, "generation": 1},
                [
                    {
                        "id": "42",
                        "title": "香川県/高松市",
                        "prefecture": "香川県",
                        "city": "高松市",
                        "pokemons": ["ヤドン"],
                    }
                ],
            ),
        }

        with tempfile.TemporaryDirectory() as tmpdir:
            html = generate_html(
                pokemon_index,
                "ja",
                LANG_CONFIGS["ja"],
                LP_INDEX_STRINGS["ja"],
                lambda pref: pref,
                {},
                Path(tmpdir),
            )

        self.assertNotIn('class="hero-summary"', html)


class SectionOrderAndCollapseTest(unittest.TestCase):
    """実機フィードバック: 今はSEO都合の並びなので、人気順(featured/ranking)を
    上に、離脱の原因になる全ポケモン一覧(549体)の巨大な写真カード羅列は
    折りたたみ式のテキストリンクに変えて下の方へ、という改修を固定する。"""

    @classmethod
    def setUpClass(cls) -> None:
        pokemon_index = {
            "pikachu": (
                {"names": {"ja": "ピカチュウ", "en": "Pikachu"}, "generation": 1},
                [
                    {
                        "id": "1",
                        "title": "京都府/宇治市",
                        "prefecture": "京都府",
                        "city": "宇治市",
                        "pokemons": ["ピカチュウ"],
                    }
                ],
            ),
            "eevee": (
                {"names": {"ja": "イーブイ", "en": "Eevee"}, "generation": 1},
                [
                    {
                        "id": "2",
                        "title": "鹿児島県/指宿市",
                        "prefecture": "鹿児島県",
                        "city": "指宿市",
                        "pokemons": ["イーブイ"],
                    }
                ]
                * 3,
            ),
        }
        with tempfile.TemporaryDirectory() as tmpdir:
            cls.html = generate_html(
                pokemon_index,
                "ja",
                LANG_CONFIGS["ja"],
                LP_INDEX_STRINGS["ja"],
                lambda pref: pref,
                {},
                Path(tmpdir),
            )

    def test_featured_and_ranking_come_before_the_seo_taxonomy_sections(self) -> None:
        html = self.html
        self.assertLess(
            html.index('id="featured-pokemon"'), html.index('id="pokemon-facts"')
        )
        self.assertLess(
            html.index('id="pokemon-ranking"'), html.index('id="pokemon-facts"')
        )
        self.assertLess(
            html.index('id="pokemon-facts"'), html.index('id="pokemon-types"')
        )
        self.assertLess(
            html.index('id="pokemon-types"'), html.index('id="pokemon-list"')
        )

    def test_full_pokemon_list_is_collapsed_compact_links_not_photo_cards(self) -> None:
        html = self.html
        list_section = html[html.index('id="pokemon-list"'):html.index('id="pokemon-faq"')]
        self.assertIn('<details class="content-collapse">', list_section)
        self.assertIn('<summary>すべて表示</summary>', list_section)
        self.assertNotIn('class="poke-card"', list_section)
        self.assertNotIn('<img', list_section)

    def test_card_links_carry_ga4_click_tracking(self) -> None:
        html = self.html
        self.assertIn(
            'data-track="pokemon_index_featured_click" data-destination="pikachu"', html
        )
        self.assertIn(
            'data-track="pokemon_index_ranking_click" data-destination="eevee"', html
        )
        self.assertIn('data-track="pokemon_index_all_click"', html)
        self.assertIn("window.PokefutaAnalytics.bindClickTracking({", html)


class RepresentativeImageTest(unittest.TestCase):
    """人が選んだ代表のマンホールが、カードの1枚に出ること。"""

    def _cards(self, representatives, drop_photo="", lid=()):
        from generate_pokemon_index_page import _build_pokemon_cards

        manholes = [
            {"id": "42", "prefecture": "香川県", "city": "高松市", "pokemons": ["ヤドン"]},
            {"id": "43", "prefecture": "香川県", "city": "坂出市", "pokemons": ["ヤドン"]},
        ]
        pokemon_index = {"slowpoke": ({"names": {"ja": "ヤドン", "en": "Slowpoke"}}, manholes)}
        # 43 のほうが新しい写真。代表が無ければこちらが出る
        photos_data = {"photos": {
            "42": {"manhole_id": 42, "url": "https://example.com/42.jpg", "created_at": "2026-01-01T00:00:00Z"},
            "43": {"manhole_id": 43, "url": "https://example.com/43.jpg", "created_at": "2026-06-01T00:00:00Z"},
        }}
        photos_data["photos"].pop(drop_photo, None)
        with tempfile.TemporaryDirectory() as tmpdir:
            for mid in ("42", "43"):
                (Path(tmpdir) / f"{mid}_latest.jpeg").write_bytes(b"")
            for mid in lid:
                (Path(tmpdir) / f"{mid}_lid.jpeg").write_bytes(b"")
            cards = _build_pokemon_cards(
                pokemon_index, "ja", LANG_CONFIGS["ja"], LP_INDEX_STRINGS["ja"],
                lambda pref: pref, photos_data, Path(tmpdir), representatives,
            )
        return cards[0]["latest_image"]

    def test_representative_wins_over_newest_photo(self):
        image = self._cards({"slowpoke": "42"})
        self.assertEqual(image["manhole_id"], "42")
        self.assertIn("42_latest.jpeg", image["url"])

    def test_falls_back_to_newest_photo_without_valid_representative(self):
        self.assertEqual(self._cards({})["manhole_id"], "43")
        # そのポケモンのいないマンホールが代表になっていたら使わない
        self.assertEqual(self._cards({"slowpoke": "99"})["manhole_id"], "43")

    def test_representative_without_current_public_photo_is_not_used(self):
        # 代表の写真が非公開・削除になって写真一覧から消えたら、_latest.jpeg が残っていても使わない
        self.assertEqual(self._cards({"slowpoke": "42"}, drop_photo="42")["manhole_id"], "43")

    def test_load_representatives_maps_japanese_names_to_slugs(self):
        from generate_pokemon_index_page import load_representatives

        metadata = {"ヤドン": {"slug": "slowpoke"}, "ラッキー": {"slug": "chansey"}}
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "reps.json"
            path.write_text('{"representatives": {"ヤドン": 42, "いないポケモン": 1}}', encoding="utf-8")
            self.assertEqual(load_representatives(path, metadata), {"slowpoke": "42"})
            self.assertEqual(load_representatives(Path(tmpdir) / "none.json", metadata), {})
            # 形が崩れていても例外にせず、代表なしにする
            for broken in ('{"representatives": []}', '{"representatives": "x"}', "[]", "{"):
                path.write_text(broken, encoding="utf-8")
                self.assertEqual(load_representatives(path, metadata), {}, broken)

    def test_card_uses_the_lid_crop_when_it_exists(self):
        # カードは小さいタイルなので、蓋の枠に合わせた _lid を使う（蓋のまわりまで写った写真でも蓋が大きく見える）
        image = self._cards({"slowpoke": "42"}, lid=("42",))
        self.assertEqual(image["manhole_id"], "42")
        self.assertTrue(image["url"].endswith("/manhole/image/42_lid.jpeg"), image["url"])
        # _lid が無ければ _latest のまま
        self.assertTrue(self._cards({"slowpoke": "42"}, lid=("43",))["url"].endswith("42_latest.jpeg"))


class RankingLimitTest(unittest.TestCase):
    def test_ranking_lists_thirty_pokemon(self):
        from generate_pokemon_index_page import RANKING_LIMIT

        self.assertEqual(30, RANKING_LIMIT)
        pokemon_index = {}
        for i in range(35):
            slug = f"poke{i:02d}"
            manholes = [{"id": str(i * 100 + j), "prefecture": "香川県", "city": "高松市", "pokemons": [slug]}
                        for j in range(40 - i)]
            pokemon_index[slug] = ({"slug": slug, "names": {"ja": slug, "en": slug}}, manholes)
        with tempfile.TemporaryDirectory() as tmpdir:
            html = generate_html(
                pokemon_index, "ja", LANG_CONFIGS["ja"], LP_INDEX_STRINGS["ja"],
                lambda pref: pref, {"photos": {}}, Path(tmpdir),
            )
        section = html[html.index('id="pokemon-ranking"'):]
        section = section[:section.index("</ol>")]
        self.assertEqual(30, section.count('class="ranking-item"'))
        self.assertIn('data-destination="poke29"', section)
        self.assertNotIn('data-destination="poke30"', section)


if __name__ == "__main__":
    unittest.main()
