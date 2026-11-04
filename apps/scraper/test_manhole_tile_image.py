"""manhole_tile_image のテスト（小さいタイルは _lid、無ければ _latest。小さい WebP の srcset）。"""

import re
import tempfile
import unittest
from pathlib import Path

from PIL import Image

try:
    from apps.scraper import build_small_images
    from apps.scraper.manhole_tile_image import SMALL_WIDTHS, responsive_attrs, small_image_url, srcset, tile_image_url
except ModuleNotFoundError as exc:
    if exc.name != "apps":
        raise
    import build_small_images
    from manhole_tile_image import SMALL_WIDTHS, responsive_attrs, small_image_url, srcset, tile_image_url


class TileImageUrlTest(unittest.TestCase):
    def test_prefers_lid_then_latest(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            self.assertEqual(tile_image_url("7", root), "")
            (root / "7_latest.jpeg").write_bytes(b"x")
            self.assertEqual(tile_image_url("7", root), "/manhole/image/7_latest.jpeg")
            (root / "7_lid.jpeg").write_bytes(b"x")
            self.assertEqual(tile_image_url("7", root), "/manhole/image/7_lid.jpeg")
            self.assertEqual(tile_image_url(" ", root), "")



class SmallImageTest(unittest.TestCase):
    def test_srcset_lists_small_webp_and_larger_original(self):
        self.assertEqual(small_image_url("/manhole/image/7_lid.jpeg", 180), "/manhole/image/7_lid_180.webp")
        self.assertEqual(
            srcset("manhole/image/7_latest.jpeg"),
            "manhole/image/7_latest_180.webp 180w, manhole/image/7_latest_360.webp 360w, "
            "manhole/image/7_latest_480.webp 480w, manhole/image/7_latest.jpeg 720w",
        )
        self.assertEqual(
            srcset("/manhole/image/7_latest.jpeg", max_width=480).split(", ")[-1],
            "/manhole/image/7_latest_480.webp 480w",
        )
        # _lid は 360px が元と同じ幅なので、元の JPEG は候補に入れない
        self.assertEqual(
            srcset("/manhole/image/7_lid.jpeg"),
            "/manhole/image/7_lid_180.webp 180w, /manhole/image/7_lid_360.webp 360w",
        )

    def test_other_images_are_left_alone(self):
        for url in ("https://pokefuta.com/api/design-manholes/x/photo", "/manhole/image/7_abcd.jpeg", ""):
            self.assertEqual(small_image_url(url, 180), url)
            self.assertEqual(srcset(url), "")
            self.assertNotIn("srcset", responsive_attrs(url, "80px"))
        self.assertEqual(small_image_url("/manhole/image/7_lid.jpeg", 480), "/manhole/image/7_lid.jpeg")

    def test_responsive_attrs_escape(self):
        attrs = responsive_attrs('/manhole/image/"7_lid.jpeg', "(min-width: 960px) 140px, 70px")
        self.assertIn('src="/manhole/image/&quot;7_lid.jpeg"', attrs)
        self.assertIn('sizes="(min-width: 960px) 140px, 70px"', attrs)

    def test_builder_writes_every_srcset_candidate(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            Image.new("RGB", (360, 360), "red").save(root / "7_lid.jpeg")
            Image.new("RGB", (720, 720), "blue").save(root / "7_latest.jpeg")
            Image.new("RGB", (720, 720), "green").save(root / "7_abcd.jpeg")  # 投稿写真そのものは対象外
            written = sum(build_small_images.build_one(p) for p in build_small_images.sources(root))
            self.assertEqual(written, 5)
            for name in ("7_lid.jpeg", "7_latest.jpeg"):
                for candidate in srcset(name).split(", "):
                    url, width = candidate.rsplit(" ", 1)
                    with Image.open(root / url) as image:
                        self.assertEqual(image.size, (int(width[:-1]),) * 2)
            self.assertFalse(list(root.glob("7_abcd_*")))
            # 2回目は作り直さない
            self.assertEqual(sum(build_small_images.build_one(p) for p in build_small_images.sources(root)), 0)



class MapPageSmallImageTest(unittest.TestCase):
    def test_map_pages_ask_only_for_widths_the_builder_writes(self):
        """地図の JS は画像の URL を自分で組み立てるので、指す幅がデプロイで作る WebP と食い違わないか。"""
        web = Path(__file__).parents[1] / "web"
        for name in ("map.html", "map.template.html"):
            with self.subTest(page=name):
                source = (web / name).read_text(encoding="utf-8")
                calls = re.findall(r"getLocalManholeImageUrl\(([^()]*)\)", source)
                widths = [c.split(",")[1].strip() for c in calls if "," in c and not c.startswith("id,")]
                self.assertTrue(widths)
                for width in widths:
                    self.assertIn(int(width), SMALL_WIDTHS["latest"])
                # 幅を付けずに 720px の JPEG を読む呼び出しを残さない（定義の行だけ）
                self.assertEqual([c for c in calls if "," not in c], [])

    def test_map_pages_read_photos_from_r2(self):
        """地図の写真は Pages ではなく R2（img.pokefuta.com）から読む。デプロイで同じパスに複写している。"""
        web = Path(__file__).parents[1] / "web"
        for name in ("map.html", "map.template.html"):
            with self.subTest(page=name):
                source = (web / name).read_text(encoding="utf-8")
                self.assertIn("const MANHOLE_IMAGE_BASE = 'https://img.pokefuta.com/manhole/image/';", source)
                self.assertIn("const base = `${MANHOLE_IMAGE_BASE}${encodeURIComponent(safeId)}_latest`;", source)


    def test_manhole_related_thumbnails_use_small_webp(self):
        from apps.scraper import generate_manhole_pages as ja  # noqa: PLC0415
        url = f"{ja.BASE_URL}manhole/image/7_latest.jpeg"
        html = ja._render_related_card({"id": "7", "prefecture": "東京都", "city": "町田市"}, {"7": url})
        self.assertIn("manhole/image/7_latest_180.webp", html)
        self.assertNotIn("7_latest.jpeg", html)


if __name__ == "__main__":
    unittest.main()
