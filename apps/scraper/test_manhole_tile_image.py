"""manhole_tile_image.tile_image_url のテスト（小さいタイルは _lid、無ければ _latest）。"""

import tempfile
import unittest
from pathlib import Path

try:
    from apps.scraper.manhole_tile_image import tile_image_url
except ModuleNotFoundError as exc:
    if exc.name != "apps":
        raise
    from manhole_tile_image import tile_image_url


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


if __name__ == "__main__":
    unittest.main()
