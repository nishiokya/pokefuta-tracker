import re
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
        candidates = list((ROOT / "web").glob("*.html"))
        candidates += list((ROOT / "scraper").glob("generate_*.py"))
        sources = []
        for source in candidates:
            text = source.read_text(encoding="utf-8")
            if "gtag(" in text or "PokefutaAnalytics.init" in text:
                sources.append(source)

        for source in sources:
            with self.subTest(source=source.name):
                text = source.read_text(encoding="utf-8")
                self.assertIn("analytics.js", text)
                self.assertIn("PokefutaAnalytics.init", text)
                self.assertNotIn("googletagmanager.com/gtag", text)

    def test_event_location_uses_surface_not_reserved_source(self):
        candidates = list((ROOT / "web").glob("*.html"))
        candidates += list((ROOT / "scraper").glob("generate_*.py"))
        reserved_source = re.compile(
            r"(?:trackEvent|_attr_json)\s*\([^)]{0,800}?[\"']source[\"']\s*:",
            re.DOTALL,
        )

        for source in candidates:
            with self.subTest(source=source.name):
                text = source.read_text(encoding="utf-8")
                self.assertIsNone(reserved_source.search(text))

    def test_internal_app_links_do_not_use_utm(self):
        generator = (ROOT / "scraper/generate_prefecture_pages.py").read_text(encoding="utf-8")

        self.assertIn('return "from=data"', generator)
        self.assertNotIn("utm_source=data.pokefuta.com", generator)


if __name__ == "__main__":
    unittest.main()
