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

        # 内部導線を外部キャンペーンとして扱わず、独自パラメータで識別する。
        self.assertIn("from=data", generator)
        self.assertNotIn("utm_source=data.pokefuta.com", generator)
        self.assertNotIn("utm_medium", generator)
        self.assertNotIn("utm_campaign", generator)


    def test_theme_tag_clicks_use_the_same_parameter_name_everywhere(self):
        """トップのタグチップと地図のタグ絞り込みで、パラメータ名を揃える。

        揃っていないと「トップでタグを押した人が地図でも絞り込んだか」を
        1つのディメンションで追えず、GA4 のカスタムディメンション枠も
        同じ概念に2つ食われる。
        """
        top = (ROOT / "web/index.html").read_text(encoding="utf-8")
        self.assertIn("click_hub_tag", top)
        self.assertIn("tag:", top)

        for name in ("map.html", "map.template.html"):
            with self.subTest(source=name):
                text = (ROOT / "web" / name).read_text(encoding="utf-8")
                self.assertIn("feature_filter_click", text)
                self.assertIn("tag: tag,", text)
                # 旧名が残っていると、登録すべき名前が分からなくなる
                self.assertNotIn("feature: tag,", text)
                self.assertNotIn("feature_label:", text)

    def test_top_page_and_its_template_track_the_same_events(self):
        """index.html（日本語の手編集版）と index.template.html（多言語の元）で
        計測イベントが揃っていること。片方だけ直すと言語によって欠測する。
        """
        def event_names(name):
            text = (ROOT / "web" / name).read_text(encoding="utf-8")
            return set(re.findall(r"trackEvent\(\s*'([a-z_]+)'", text))

        self.assertEqual(event_names("index.html"), event_names("index.template.html"))

    def test_top_prefecture_list_expansion_is_tracked(self):
        """「すべて見る（47都道府県）」の展開を計測する。

        トップで何人が47件すべてを必要としているかが、
        一覧の初期表示件数（デスクトップ12件・SP3件）を見直す根拠になる。
        """
        for name in ("index.html", "index.template.html"):
            with self.subTest(source=name):
                text = (ROOT / "web" / name).read_text(encoding="utf-8")
                self.assertIn("click_pref_show_all", text)


if __name__ == "__main__":
    unittest.main()
