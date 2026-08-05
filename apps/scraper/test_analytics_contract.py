import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class AnalyticsContractTest(unittest.TestCase):
    def test_shared_loader_is_production_only(self):
        analytics = (ROOT / "web/assets/analytics.js").read_text(encoding="utf-8")

        self.assertIn("PRODUCTION_HOSTS = ['data.pokefuta.com']", analytics)
        self.assertIn("window.location.hostname.toLowerCase()", analytics)
        self.assertIn("domains: ['data.pokefuta.com', 'pokefuta.com']", analytics)

    def test_ga_sources_use_shared_loader(self):
        sources = [
            ROOT / "web/index.template.html",
            ROOT / "web/map.template.html",
            ROOT / "web/index.html",
            ROOT / "web/map.html",
            ROOT / "web/gmanhole_map.html",
            ROOT / "web/design_manhole.html",
            ROOT / "web/nearby_manholes.html",
            ROOT / "scraper/generate_character_manhole_page.py",
            ROOT / "scraper/generate_summary_pages.py",
            ROOT / "scraper/generate_prefecture_pages.py",
            ROOT / "scraper/generate_pokemon_index_page.py",
            ROOT / "scraper/generate_pokemon_pages.py",
            ROOT / "scraper/generate_manhole_pages.py",
        ]

        for source in sources:
            with self.subTest(source=source.name):
                text = source.read_text(encoding="utf-8")
                self.assertIn("analytics.js", text)
                self.assertIn("PokefutaAnalytics.init", text)
                self.assertNotIn("googletagmanager.com/gtag", text)

    def test_event_location_uses_surface_not_reserved_source(self):
        generator = (ROOT / "scraper/generate_manhole_pages.py").read_text(encoding="utf-8")
        map_template = (ROOT / "web/map.template.html").read_text(encoding="utf-8")

        self.assertNotRegex(generator, r'\{[^\n]*["\']source["\']\s*:')
        self.assertIn("surface: 'top_feature_section'", map_template)


if __name__ == "__main__":
    unittest.main()
