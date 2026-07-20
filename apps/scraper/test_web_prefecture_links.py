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
