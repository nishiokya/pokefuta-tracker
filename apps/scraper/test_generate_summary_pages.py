import importlib.util
import json
import unittest
from pathlib import Path

MODULE_PATH = Path(__file__).with_name("generate_summary_pages.py")
SPEC = importlib.util.spec_from_file_location("generate_summary_pages", MODULE_PATH)
summary = importlib.util.module_from_spec(SPEC)
assert SPEC and SPEC.loader
SPEC.loader.exec_module(summary)


class DiscoveryHubTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.records = [
            record
            for record in summary.load_records(summary.NDJSON)
            if record.get("status", "active") == "active"
        ]
        cls.records_by_id = {str(record["id"]): record for record in cls.records}
        cls.metadata = summary.load_pokemon_metadata_with_slugs(summary.POKEMON_METADATA_JSON)

    def test_summary_hubs_exist_in_every_language(self):
        for language, strings in summary.SUMMARY_STRINGS.items():
            with self.subTest(language=language):
                html = summary._build_discovery_hub_sections(
                    strings, self.records_by_id, self.metadata
                )
                self.assertIn('id="travel-discovery"', html)
                self.assertIn('id="rare-discovery"', html)
                self.assertGreaterEqual(html.count("discovery-hub-card"), 9)
                self.assertIn('data-destination-hub="manhole_detail"', html)

    def test_travel_counts_match_title_data(self):
        html = summary._build_discovery_hub_sections(
            summary.SUMMARY_STRINGS["ja"], self.records_by_id, self.metadata
        )
        for key in (
            "remote_island",
            "roadside",
            "station_front",
            "world_heritage",
            "near_gundam_manhole",
            "gundam_manhole_city",
        ):
            count = sum(summary._has_title(record, key) for record in self.records)
            self.assertIn(f">{count}枚</strong>", html)

    def test_gundam_hubs_use_title_data(self):
        records = {
            "66": {
                "id": "66",
                "prefecture": "北海道",
                "city": "天塩町",
                "pokemons": ["ロコン"],
                "titles": [
                    {"key": "near_gundam_manhole"},
                    {"key": "gundam_manhole_city"},
                ],
            },
            "67": {
                "id": "67",
                "prefecture": "北海道",
                "city": "稚内市",
                "pokemons": ["アローラロコン"],
                "titles": [{"key": "gundam_manhole_city"}],
            },
        }
        html = summary._build_discovery_hub_sections(
            summary.SUMMARY_STRINGS["ja"], records, self.metadata
        )
        self.assertIn("ガンダムマンホールまで約500m以内", html)
        self.assertIn("ガンダムマンホールのあるまち", html)
        self.assertIn('data-content-id="near_gundam_manhole"', html)
        self.assertIn('data-content-id="gundam_manhole_city"', html)
        self.assertIn(">1枚</strong>", html)
        self.assertIn(">2枚</strong>", html)

    def test_hero_uses_popup_and_summary_hubs(self):
        source = (summary.ROOT / "apps/web/index.html").read_text(encoding="utf-8")
        self.assertIn("click_hero_new_photo", source)
        self.assertIn("openManholePopup(recommendation.manhole.id)", source)
        self.assertIn("'travel-discovery'", source)
        self.assertIn("'rare-discovery'", source)
        self.assertIn("destination_hub: recommendation.destinationHub", source)
        self.assertIn("getDailyRotationIndex", source)
        self.assertIn("getHeroThemeCount(themeKey)", source)
        self.assertIn("getUniqueHeroPokemon(manhole)", source)
        self.assertIn("window.I18N?.intlLocale || 'ja-JP'", source)
        self.assertIn("const pokemonMetadataPromise = loadPokemonMetadata();", source)
        self.assertIn("marker.setPopupContent(buildPokefutaPopup(marker.pokefutaData))", source)
        self.assertNotIn("await loadPokemonMetadata();", source)
        self.assertNotIn("countTemplate.replace('{count}', candidates.length)", source)
        self.assertNotIn("pokemon: reason", source)

    def test_generated_template_keeps_popup_copy_localized(self):
        template = (summary.ROOT / "apps/web/index.template.html").read_text(
            encoding="utf-8"
        )
        self.assertIn("const UI_TEXT = window.I18N.UI;", template)
        self.assertIn("${I.photoWanted}", template)
        self.assertIn("${I.photoMissing}", template)
        self.assertIn("${I.photoViewCta}", template)
        self.assertIn("${I.firstPhotoUploadCta}", template)
        self.assertIn("${I.googleMapsCta}", template)
        self.assertIn("anchor.textContent = UI_TEXT.detailPageCta;", template)
        self.assertIn("getHeroPokemonDisplayName(pokemon)", template)
        self.assertNotIn("getPokemonDisplayName(pokemon)", template)
        self.assertNotIn("const UI_TEXT = {", template)

    def test_i18n_hero_strings_have_all_destinations(self):
        i18n_dir = summary.ROOT / "apps/web/i18n"
        for language in ("ja", "en", "zh-CN", "zh-TW", "ko"):
            with self.subTest(language=language):
                data = json.loads(
                    (i18n_dir / f"strings.{language}.json").read_text(encoding="utf-8")
                )
                hero = data["I18N_OBJECT"]["heroDiscovery"]
                self.assertEqual(set(hero["ctas"]), {"fresh", "travel", "rare"})
                self.assertEqual(
                    set(hero["travelThemes"]),
                    {"remote_island", "roadside", "station_front", "world_heritage"},
                )

    def test_japanese_prefecture_cards_link_to_static_pages(self):
        records = summary.load_records(summary.NDJSON)
        stats = summary.build_stats(records)
        html = summary._build_prefecture_info_section(
            summary.SUMMARY_STRINGS["ja"],
            stats,
            records,
            [],
            lambda value: value,
        )
        self.assertIn('href="/prefectures/fukui/"', html)
        self.assertIn('href="/prefectures/gunma/"', html)
        self.assertIn('data-summary-event="summary_prefecture_click"', html)

    def test_japanese_ranking_uses_landing_page_cta(self):
        records = summary.load_records(summary.NDJSON)
        stats = summary.build_stats(records)
        html = summary.render_page(
            summary.SUMMARY_STRINGS["ja"],
            stats,
            {},
            {},
            {},
            {},
            {},
        )
        self.assertIn('href="/prefectures/', html)
        self.assertIn(">詳しく見る</a>", html)


if __name__ == "__main__":
    unittest.main()
