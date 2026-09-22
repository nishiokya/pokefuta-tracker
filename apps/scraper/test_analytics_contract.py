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

    def test_mobile_bottom_navigation_uses_shared_analytics(self):
        analytics = (ROOT / "web/assets/site-header-analytics.js").read_text(encoding="utf-8")

        self.assertIn("window.trackEvent(name, params)", analytics)
        self.assertIn("track('view_navigation'", analytics)
        self.assertIn("track('click_nav'", analytics)
        self.assertIn("surface: SURFACE", analytics)
        self.assertIn("nav_variant: variant", analytics)
        self.assertIn("(max-width: 1023.98px)", analytics)
        self.assertNotIn("nav: tab.dataset.navItem", analytics)
        self.assertNotIn("gtag(", analytics)
        self.assertNotIn("source:", analytics)

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

    def test_custom_events_carry_a_surface(self):
        """カスタムイベントは必ず `surface`（発生箇所）を載せること。

        GA4 で登録済みのカスタムディメンションは4つしかなく、`surface` はその1つ。
        ここが欠けると「どの面のクリックか」が永久に分からない
        （実測: 直近28日で `surface=(not set)` が 227,767 件）。

        ソースを見る。生成後HTMLではなくソースで見るのは、生成器を通さずに
        HTML を直接書く面（トップ・地図・nearby など）も同じ規約に乗せるため。
        """
        standard = {
            # GA4 の自動収集イベント。こちらからパラメータを付けない
            "page_view", "session_start", "first_visit", "user_engagement",
            "scroll", "click", "search", "view_search_results", "js",
        }
        call = re.compile(
            r"(?:trackEvent|gtag)\(\s*(?:['\"]event['\"]\s*,\s*)?['\"]([a-z_0-9]+)['\"]"
        )
        # 第2引数が変数1つだけの呼び出し（JS の `_sp`、生成器の f-string の
        # `{_share_onclick}`）は、その変数の定義側で surface を持たせている。
        # 定義側は test_generated_event_params_carry_a_surface が見る。
        var_arg = re.compile(
            r"""^\(\s*['\"][a-z_0-9]+['\"]\s*,\s*\{?[A-Za-z_$][\w$]*\}?\s*\)$"""
        )

        sources = list((ROOT / "web").glob("*.html"))
        sources += list((ROOT / "scraper").glob("generate_*.py"))
        offenders = []
        for source in sources:
            text = source.read_text(encoding="utf-8")
            for match in call.finditer(text):
                name = match.group(1)
                if name in standard:
                    continue
                start = text.index("(", match.start())
                depth = 0
                for end in range(start, len(text)):
                    if text[end] == "(":
                        depth += 1
                    elif text[end] == ")":
                        depth -= 1
                        if depth == 0:
                            break
                args = text[start:end + 1]
                if "surface" in args or var_arg.match(args.strip()):
                    continue
                line = text[:match.start()].count("\n") + 1
                offenders.append(f"{source.name}:{line} {name}")
        self.assertEqual([], offenders, "surface の無いイベント送信: " + ", ".join(offenders))

    def test_generated_event_params_carry_a_surface(self):
        """生成器が onclick に埋める `_attr_json({...})` も surface を持つこと。

        呼び出し側は `{_share_onclick}` のように変数を挟むので、
        上のテストからは中身が見えない。定義側をここで押さえる。
        """
        source = (ROOT / "scraper/generate_manhole_pages.py").read_text(encoding="utf-8")
        offenders = []
        for match in re.finditer(r"_attr_json\(", source):
            line_start = source.rfind("\n", 0, match.start()) + 1
            prefix = source[line_start:match.start()]
            if prefix.lstrip().startswith(("def ", "#")) or "#" in prefix:
                continue  # ヘルパの定義そのもの・コメント中の言及
            start = match.end() - 1
            depth = 0
            for end in range(start, len(source)):
                if source[end] == "(":
                    depth += 1
                elif source[end] == ")":
                    depth -= 1
                    if depth == 0:
                        break
            args = source[start:end + 1]
            if "surface" not in args:
                line = source[:match.start()].count("\n") + 1
                offenders.append(f"generate_manhole_pages.py:{line}")
        self.assertEqual([], offenders, "surface の無い onclick パラメータ: " + ", ".join(offenders))

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
