import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


class WebPrefectureLinksTest(unittest.TestCase):
    def test_top_prefecture_links_use_helper_relative_paths(self) -> None:
        for filename in ("index.html", "index.template.html"):
            with self.subTest(filename=filename):
                source = (ROOT / "apps/web" / filename).read_text(encoding="utf-8")
                self.assertIn("window.getPrefecturePageUrl = function(prefecture)", source)
                self.assertIn('" href="\' + window.getPrefecturePageUrl(pref) + \'"', source)
                self.assertNotIn('href="/prefectures/', source)

    def test_language_pages_are_linked_with_lang_path(self) -> None:
        """言語ごとに存在するページを BASE_PATH で参照しないこと。

        BASE_PATH は言語ディレクトリでは '../' になるため、map.html や pokemon/ を
        これで参照すると /en/ のリンクが日本語版へ飛ぶ（実際に起きていた）。
        言語別に存在するページは LANG_PATH（常に './'）で参照する。
        """
        source = (ROOT / "apps/web/index.template.html").read_text(encoding="utf-8")
        for page in ("map.html", "index.html", "pokemon/"):
            with self.subTest(page=page):
                self.assertNotIn(f"%%BASE_PATH%%{page}", source)
                self.assertIn(f"%%LANG_PATH%%{page}", source)
        # JS 側も同様。BASE_PATH + 'map.html' は日本語版へ飛ぶ
        self.assertNotIn("BASE_PATH + 'map.html", source)
        self.assertIn("LANG_PATH + 'map.html", source)
        self.assertIn("var LANG_PATH = '%%LANG_PATH%%';", source)

    def test_root_only_resources_keep_base_path(self) -> None:
        """ルート直下にしか無いものは BASE_PATH のままであること。"""
        source = (ROOT / "apps/web/index.template.html").read_text(encoding="utf-8")
        for resource in ("assets/theme.css", "prefectures/", "character_manholes.html"):
            with self.subTest(resource=resource):
                self.assertIn(f"%%BASE_PATH%%{resource}", source)
        for resource in ("pokefuta.ndjson", "manhole/image/", "api/top-feed.json"):
            with self.subTest(resource=resource):
                self.assertIn(f"BASE_PATH + '{resource}", source)

    def test_every_language_defines_both_paths(self) -> None:
        import json
        for path in sorted((ROOT / "apps/web/i18n").glob("strings.*.json")):
            with self.subTest(lang=path.name):
                data = json.loads(path.read_text(encoding="utf-8"))
                self.assertIn("BASE_PATH", data)
                self.assertEqual(data.get("LANG_PATH"), "./")

    def test_map_copy_has_prefecture_page_helper(self) -> None:
        source = (ROOT / "apps/web/map.html").read_text(encoding="utf-8")
        self.assertIn("function getPrefecturePageUrl(prefecture)", source)
        self.assertIn("return slug ? `prefectures/${encodeURIComponent(slug)}/` : '';", source)
        self.assertIn("anchor.textContent = UI_TEXT.prefectureSite;", source)

    def test_map_template_uses_localized_prefecture_paths(self) -> None:
        source = (ROOT / "apps/web/map.template.html").read_text(encoding="utf-8")
        self.assertIn("function getPrefecturePageUrl(prefecture)", source)
        self.assertIn("%%BASE_PATH%%prefectures/${encodeURIComponent(slug)}/", source)
        self.assertIn("anchor.textContent = UI_TEXT.prefectureSite;", source)

    def test_map_page_has_its_own_title_and_description(self) -> None:
        """地図ページはトップと別のメタを持つこと。

        map.template.html は index.template.html と同じ %%PAGE_TITLE%% /
        %%META_DESCRIPTION%% を使っており、他4言語では /xx/ と
        /xx/map.html の title・description が完全に同一だった。
        canonical を map.html 自身に向けた以上、同一メタの indexable な
        URL が2つできてしまう。
        """
        import json

        source = (ROOT / "apps/web/map.template.html").read_text(encoding="utf-8")
        self.assertIn("<title>%%MAP_PAGE_TITLE%%</title>", source)
        self.assertNotIn("%%PAGE_TITLE%%", source)
        self.assertNotIn("%%META_DESCRIPTION%%", source)

        # ja は build_i18n.LANGS に無く（map.html を手で保守している）、
        # strings.ja.json は他にも多数のキーを持たない。対象は実際に
        # ビルドされる4言語だけ。
        for lang in ("en", "zh-TW", "zh-CN", "ko"):
            path = ROOT / "apps/web/i18n" / f"strings.{lang}.json"
            with self.subTest(lang=lang):
                data = json.loads(path.read_text(encoding="utf-8"))
                for key in ("MAP_PAGE_TITLE", "MAP_META_DESCRIPTION"):
                    self.assertIn(key, data)
                self.assertNotEqual(data["MAP_PAGE_TITLE"], data["PAGE_TITLE"])
                self.assertNotEqual(
                    data["MAP_META_DESCRIPTION"], data["META_DESCRIPTION"]
                )

    def test_map_canonical_stays_on_the_map_page(self) -> None:
        """地図の canonical はトップではなく map.html 自身を基準にすること。

        map.html だけ `${window.SITE_BASE_URL}?manhole=` を使っており、
        ?manhole= を開いた瞬間に canonical と og:url がトップへ書き換わって
        いた（静的 canonical を map.html に向けた意味が消える）。
        手編集の map.html と、多言語のもとになる map.template.html の
        両方を見て、片方だけ直して食い違う事故を防ぐ。
        """
        for filename in ("map.html", "map.template.html"):
            with self.subTest(filename=filename):
                source = (ROOT / "apps/web" / filename).read_text(encoding="utf-8")
                self.assertIn(
                    "`${window.location.origin}${window.location.pathname}"
                    "?manhole=${encodeURIComponent(manhole.id)}`",
                    source,
                )
                self.assertNotIn(
                    "`${window.SITE_BASE_URL}?manhole=", source
                )

    def test_map_photo_authors_link_to_public_stamp_books(self) -> None:
        for filename in ("map.html", "map.template.html"):
            with self.subTest(filename=filename):
                source = (ROOT / "apps/web" / filename).read_text(encoding="utf-8")
                self.assertIn("function getPosterProfileUrl(publicUserId)", source)
                self.assertIn("photoMeta?.public_user_id", source)
                self.assertIn(
                    "https://pokefuta.com/users/${encodeURIComponent(id)}/visits",
                    source,
                )
                self.assertIn('<a class="travel-popup-photo-author"', source)
                self.assertNotIn(
                    'aria-label="${escapeHtml(displayName)}さんの公開スタンプ帳を開く"',
                    source,
                )


if __name__ == "__main__":
    unittest.main()
