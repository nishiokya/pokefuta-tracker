"""use_image_host のテスト（蓋の写真は img.pokefuta.com、og:image・JSON-LD は data のまま）。"""

import tempfile
import unittest
from pathlib import Path

try:
    from apps.scraper.use_image_host import IMAGE_BASE, rewrite_dist, use_image_host
except ModuleNotFoundError as exc:
    if exc.name != "apps":
        raise
    from use_image_host import IMAGE_BASE, rewrite_dist, use_image_host


class UseImageHostTest(unittest.TestCase):
    def test_every_relative_form_points_at_r2(self):
        html = (
            '<img src="/manhole/image/1_lid.jpeg" '
            'srcset="/manhole/image/1_lid_180.webp 180w, /manhole/image/1_lid.jpeg 360w">'
            '<img src="manhole/image/2_lid.jpeg" srcset="manhole/image/2_lid_180.webp 180w, manhole/image/2_lid.jpeg 360w">'
            '<img src="../manhole/image/3_lid.jpeg"><img src="./manhole/image/4_lid.jpeg">'
            '<script>var points = [{"photo_url": "/manhole/image/5_latest.jpeg"}];'
            "function u(id) { return './manhole/image/' + id + '_latest_180.webp'; }</script>"
        )
        out = use_image_host(html)
        self.assertEqual(out.count(IMAGE_BASE), 10)
        self.assertNotIn('"/manhole/image/', out)
        self.assertNotIn("../manhole/image/", out)
        self.assertNotIn("./manhole/image/", out)

    def test_absolute_data_url_is_rewritten_only_in_img_tags(self):
        html = (
            '<meta property="og:image" content="https://data.pokefuta.com/manhole/image/1_latest.jpeg">'
            '<link rel="preload" as="image" href="/manhole/image/1_latest.jpeg">'
            '<script type="application/ld+json">{"image": "https://data.pokefuta.com/manhole/image/1_latest.jpeg"}</script>'
            "<script>jsonLd.image = `https://data.pokefuta.com/manhole/image/${id}_latest.jpeg`;</script>"
            '<img src="https://data.pokefuta.com/manhole/image/1_latest.jpeg" '
            "onerror=\"this.src='https://data.pokefuta.com/manhole/image/1_lid.jpeg'\">"
        )
        out = use_image_host(html)
        self.assertIn('content="https://data.pokefuta.com/manhole/image/1_latest.jpeg"', out)
        self.assertIn('href="/manhole/image/1_latest.jpeg"', out)
        self.assertIn('{"image": "https://data.pokefuta.com/manhole/image/1_latest.jpeg"}', out)
        self.assertIn("`https://data.pokefuta.com/manhole/image/${id}_latest.jpeg`", out)
        self.assertIn(f'<img src="{IMAGE_BASE}1_latest.jpeg" onerror="this.src=\'{IMAGE_BASE}1_lid.jpeg\'">', out)

    def test_leaves_prefixed_concatenation_and_other_paths_alone(self):
        html = (
            "<script>img.src = BASE_PATH + 'manhole/image/' + id + '_latest.jpeg';</script>"
            '<img src="/assets/brand-mark.svg"><a href="/manhole/1/">1</a>'
            f'<img src="{IMAGE_BASE}1_lid.jpeg">'
        )
        self.assertEqual(use_image_host(html), html)

    def test_rewrite_dist_counts_changed_files(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            (root / "prefectures" / "hokkaido").mkdir(parents=True)
            (root / "prefectures" / "hokkaido" / "index.html").write_text('<img src="/manhole/image/1_lid.jpeg">', encoding="utf-8")
            (root / "about.html").write_text("<p>no photos</p>", encoding="utf-8")
            self.assertEqual(rewrite_dist(root), 1)
            self.assertEqual(
                (root / "prefectures" / "hokkaido" / "index.html").read_text(encoding="utf-8"),
                f'<img src="{IMAGE_BASE}1_lid.jpeg">',
            )
            self.assertEqual(rewrite_dist(root), 0)


if __name__ == "__main__":
    unittest.main()
